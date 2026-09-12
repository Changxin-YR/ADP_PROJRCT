from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from collections.abc import Callable
from typing import Any

from backend.config.settings import Settings
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError
from backend.layers.features.agent.agent_prompt import (
    ensure_instructions,
    render_prompt,
)
from backend.layers.features.agent.agent_tool_registry import build_agent_tool_catalog
from backend.layers.features.agent.harness_cache import DEFAULT_LIMIT, HarnessCache


class HarnessSidecar:
    """Small synchronous adapter around the optional DeepSeek Harness Python SDK."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache = HarnessCache(DEFAULT_LIMIT)
        self._lock = threading.RLock()

    def _new_harness(self, runtime_env: dict[str, str], safe_context: dict[str, str]) -> Any:
        # The harness loads $DSH_HOME/AGENTS.md on every baseline; keep it in sync
        # with the release so the behaviour contract ships with the code.
        ensure_instructions(self.settings.agent_sidecar_home, self.settings.agent_write_mode)
        from deepseek_harness import DeepSeekHarness

        patch = self.settings.agent_sidecar_patch.strip()
        patches = (patch,) if patch else ()
        command = self.settings.agent_sidecar_command.strip()
        # Node mode is an explicit development carrier selected by the SDK;
        # passing the installed Windows wrapper would bypass that selection.
        dsh_bin = None if runtime_env.get("DSH_RUNTIME_MODE") == "node" else (shutil.which(command) or command or None)
        # HarnessClient snapshots os.environ while spawning the child. Keep the
        # temporary setup isolated so unrelated requests cannot leak secrets.
        with _HARNESS_ENV_LOCK:
            previous = dict(os.environ)
            try:
                os.environ.clear()
                os.environ.update(runtime_env)
                harness = DeepSeekHarness(
                    dsh_home=self.settings.agent_sidecar_home,
                    cwd=self.settings.agent_sidecar_cwd,
                    dsh_bin=dsh_bin,
                    profile="sdk",
                    provider=self.settings.agent_model_provider,
                    model=self.settings.agent_model,
                    max_tokens=self.settings.agent_model_max_tokens,
                    patches=patches,
                    request_timeout_seconds=float(self.settings.agent_request_timeout_seconds),
                    env={
                        "ADP_AGENT_GATEWAY_URL": safe_context.get("gateway_url", ""),
                        "ADP_AGENT_CONTEXT_TOKEN": safe_context.get("context_token", ""),
                        "ADP_AGENT_TOOL_CATALOG": build_agent_tool_catalog(),
                    },
                )
                enter = getattr(harness, "__enter__", None)
                return enter() if callable(enter) else harness
            finally:
                os.environ.clear()
                os.environ.update(previous)

    def close(self) -> None:
        """Stop cached runtimes; useful for orderly application shutdown."""
        with self._lock:
            self._cache.clear()

    def _drop(self, namespace: str) -> None:
        with self._lock:
            self._cache.drop(namespace)

    def run(
        self,
        prompt: str,
        *,
        context: dict[str, str],
        on_notification: Callable[[Any], None] | None = None,
    ) -> dict[str, Any]:
        request_started = time.perf_counter()
        safe_context = {
            key: str(value)
            for key, value in context.items()
            if key in {"conversation_id", "request_id", "gateway_url", "context_token", "user_namespace", "user_brief", "page_context", "history_text"}
            and value is not None
        }
        if not safe_context.get("conversation_id"):
            raise AgentGatewayError("VALIDATION_ERROR", "缺少对话标识", 400)
        # A conversation must remain stable across turns. request_id changes on
        # every HTTP request and therefore must never be used as Harness session id.
        namespace = safe_context.get("user_namespace", "").strip()
        conversation_id = safe_context["conversation_id"]
        session_id = conversation_id
        try:
            import deepseek_harness  # noqa: F401
        except ImportError as exc:
            raise AgentGatewayError("AGENT_UNAVAILABLE", "智能体运行时未安装", 503) from exc
        runtime_env = _runtime_environment(self.settings, safe_context)
        namespace = safe_context.get("user_namespace", "").strip() or "__default__"
        try:
            with self._lock:
                harness = self._cache.get(namespace)
                if harness is None:
                    harness = self._new_harness(runtime_env, safe_context)
                    self._cache.put(namespace, harness)
                else:
                    self._cache.touch(namespace)
                # 必须在缓存定代之后算 session id：同一个子进程内保持不变，换新子进程才换代次。
                generation = self._cache.generation(namespace)
                session_id = f"{namespace}:{conversation_id}:{generation}" if namespace else conversation_id
                harness_started = time.perf_counter()
                prompt_text = render_prompt(
                    _bounded_query_prompt(prompt),
                    safe_context.get("user_brief", ""),
                    safe_context.get("page_context", ""),
                    safe_context.get("history_text", ""),
                    write_mode=self.settings.agent_write_mode,
                )
                result = harness.run(prompt_text, session_id=session_id, on_notification=on_notification)
                harness_finished = time.perf_counter()
        except TimeoutError as exc:
            raise AgentGatewayError("AGENT_TIMEOUT", "智能助手响应超时，请稍后重试", 504) from exc
        except AgentGatewayError:
            raise
        except Exception as exc:
            name = type(exc).__name__.lower()
            message = str(exc).lower()
            if "timeout" in name:
                raise AgentGatewayError("AGENT_TIMEOUT", "智能助手响应超时，请稍后重试", 504) from exc
            self._drop(namespace)  # 坏掉/卡住的子进程不复用，下一轮自动换新的
            if "deepseek-harness-runtime-bin" in message or "runtime executable" in message:
                raise AgentGatewayError("AGENT_UNAVAILABLE", "智能助手服务暂时不可用，请稍后重试", 503) from exc
            if any(marker in name for marker in ("protocol", "jsonrpc", "transport")):
                raise AgentGatewayError("AGENT_PROTOCOL_ERROR", "智能助手通信协议异常", 502) from exc
            raise AgentGatewayError("AGENT_UNAVAILABLE", "智能助手服务暂时不可用，请稍后重试", 503) from exc
        def diagnostics() -> dict[str, Any]:
            # Keep diagnostics numeric and payload-free so live latency can be
            # investigated without copying prompts, tool arguments, or keys.
            return {
                "request_received_ms": 0,
                "harness_request_start_ms": round((harness_started - request_started) * 1000, 1),
                "harness_response_ms": round((harness_finished - harness_started) * 1000, 1),
                "total_ms": round((harness_finished - request_started) * 1000, 1),
            }

        final_response = str(getattr(result, "final_response", "") or "")
        session = str(getattr(result, "session_id", session_id))
        confirmation = _confirmation_from_result(result)
        if confirmation is not None:
            return {
                "kind": "confirmation_required",
                "confirmation": confirmation,
                "message": final_response,
                "session_id": session,
                "diagnostics": diagnostics(),
            }
        clarification = _clarification_from_result(result)
        if clarification is not None:
            return {
                "kind": "clarification",
                "clarification": clarification,
                "message": final_response,
                "session_id": session,
                "diagnostics": diagnostics(),
            }
        if isinstance(result, dict):
            result.setdefault("diagnostics", diagnostics())
            return result
        if final_response:
            return {"kind": "assistant", "message": final_response, "session_id": session, "diagnostics": diagnostics()}
        self._drop(namespace)
        raise AgentGatewayError("AGENT_PROTOCOL_ERROR", "智能助手返回格式无效", 502)


def _tool_payloads(result: Any) -> list[dict[str, Any]]:
    """Collect the JSON payloads ADP tools returned during the turn, newest first."""
    events = getattr(result, "events", None)
    payloads: list[dict[str, Any]] = []
    if not isinstance(events, list):
        return payloads
    for event in reversed(events):
        if not isinstance(event, dict) or event.get("type") != "tool/result":
            continue
        data = event.get("data")
        message = data.get("message") if isinstance(data, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        blocks = [item for block in content for item in (block.get("content") if isinstance(block, dict) and isinstance(block.get("content"), list) else [block])]
        for block in reversed(blocks):
            text = block.get("text") if isinstance(block, dict) else None
            if not isinstance(text, str):
                continue
            try:
                payload = json.loads(text)
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
    return payloads


def _confirmation_from_result(result: Any) -> dict[str, Any] | None:
    """Expose a pending mutation returned by the ADP tool to the HTTP client."""
    for payload in _tool_payloads(result):
        confirmation = payload.get("confirmation")
        if payload.get("kind") == "confirmation_required" and isinstance(confirmation, dict) and confirmation.get("token"):
            return confirmation
    return None


def _clarification_from_result(result: Any) -> dict[str, Any] | None:
    """Expose an adp_ask_user question so the panel can prompt the user for guidance."""
    for payload in _tool_payloads(result):
        question = payload.get("question")
        if payload.get("kind") != "clarification" or not isinstance(question, str) or not question.strip():
            continue
        options = [str(item) for item in payload.get("options") or [] if str(item).strip()][:5]
        return {
            "question": question.strip(),
            "options": options,
            "allow_free_text": payload.get("allow_free_text") is not False,
        }
    return None


_HARNESS_ENV_LOCK = threading.Lock()
_ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "APPDATA", "LOCALAPPDATA",
    "HOME", "LANG", "LC_ALL", "TZ", "NODE_PATH", "DSH_RUNTIME_MODE",
}


def _bounded_query_prompt(prompt: str) -> str:
    """Add domain hints for two frequent intents without restricting the model."""
    normalized = prompt.replace(" ", "")
    write_match = re.search(
        r"喂养.*?pond_id\s*=\s*(\d+).*?batch_id\s*=\s*(\d+).*?material_id\s*=\s*(\d+).*?数量\s*(\d+(?:\.\d+)?)\s*kg",
        normalized,
        re.IGNORECASE,
    )
    if write_match:
        pond_id, batch_id, material_id, quantity = write_match.groups()
        code_match = re.search(r"(?:code|单号)\s*[=:：]?\s*([A-Za-z0-9._-]+)", normalized, re.IGNORECASE)
        name_match = re.search(r"(?:name|名称)\s*[=:：为]\s*([^，。；;]+)", normalized, re.IGNORECASE)
        arguments = {
            "resource": "feeding",
            "payload": {
                **({"code": code_match.group(1)} if code_match else {}),
                **({"name": name_match.group(1)} if name_match else {}),
                "pond_id": int(pond_id),
                "batch_id": int(batch_id),
                "material_id": int(material_id),
                "quantity": float(quantity) if "." in quantity else int(quantity),
                "happened_at": time.strftime("%Y-%m-%d"),
            },
        }
        return (
            f"{prompt}\n\n"
            "ADP 提示：这条指令的字段已经齐全，可以用 adp_mutation 写入；普通可恢复写入会按当前登录者权限执行，高风险写入会返回 confirmation_required，必须等待用户确认；"
            "operation 建议使用 api.production_create_post_api_v1_production_resource，"
            f"arguments 可用 {json.dumps(arguments, ensure_ascii=False, separators=(',', ':'))}。"
            "若字段或口径不放心，也可以先用 adp_query 核对或 adp_ask_user 与用户确认。"
        )
    if "未巡检" not in normalized and "没有巡检" not in normalized:
        return prompt
    return (
        f"{prompt}\n\n"
        "ADP 提示：这类问题通常一次只读查询就够——operation 用 production.list_records，"
        "arguments 用 {resource: 'daily-operations', uninspected_on: 'today', page: 1, page_size: 20}。"
        "若结果为空或口径不符，可以换 resource 再查一次，或直接问用户。"
    )


def _runtime_environment(settings: Settings, context: dict[str, str]) -> dict[str, str]:
    """Build the only environment visible to the Harness child process."""
    source = os.environ
    environment = {
        key: value
        for key, value in source.items()
        if key.upper() in _ENV_ALLOWLIST
    }
    for key in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"):
        if source.get(key):
            environment[key] = source[key]
    environment["DSH_HOME"] = str(settings.agent_sidecar_home)
    environment["ADP_AGENT_GATEWAY_URL"] = context.get("gateway_url", "")
    environment["ADP_AGENT_CONTEXT_TOKEN"] = context.get("context_token", "")
    return environment
