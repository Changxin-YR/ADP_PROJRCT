from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any

from backend.config.settings import Settings
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError
from backend.layers.features.agent.agent_prompt import ensure_instructions, render_prompt
from backend.layers.features.agent.agent_tool_registry import build_agent_tool_catalog


class HarnessSidecar:
    """Small synchronous adapter around the optional DeepSeek Harness Python SDK."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._harnesses: dict[str, Any] = {}
        self._lock = threading.RLock()

    def _new_harness(self, runtime_env: dict[str, str], safe_context: dict[str, str]) -> Any:
        # The harness loads $DSH_HOME/AGENTS.md on every baseline; keep it in sync
        # with the release so the behaviour contract ships with the code.
        ensure_instructions(self.settings.agent_sidecar_home)
        from deepseek_harness import DeepSeekHarness

        patch = self.settings.agent_sidecar_patch.strip()
        patches = (patch,) if patch else ()
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
                    dsh_bin=self.settings.agent_sidecar_command or None,
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
            harnesses, self._harnesses = self._harnesses, {}
        for harness in harnesses.values():
            close = getattr(harness, "__exit__", None)
            if callable(close):
                try:
                    close(None, None, None)
                except Exception:
                    pass
            else:
                close = getattr(harness, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass

    def run(self, prompt: str, *, context: dict[str, str]) -> dict[str, Any]:
        request_started = time.perf_counter()
        safe_context = {
            key: str(value)
            for key, value in context.items()
            if key in {"conversation_id", "request_id", "gateway_url", "context_token", "user_namespace", "user_brief"}
            and value is not None
        }
        if not safe_context.get("conversation_id"):
            raise AgentGatewayError("VALIDATION_ERROR", "缺少对话标识", 400)
        # A conversation must remain stable across turns. request_id changes on
        # every HTTP request and therefore must never be used as Harness session id.
        namespace = safe_context.get("user_namespace", "").strip()
        conversation_id = safe_context["conversation_id"]
        session_id = f"{namespace}:{conversation_id}" if namespace else conversation_id
        try:
            import deepseek_harness  # noqa: F401
        except ImportError as exc:
            raise AgentGatewayError("AGENT_UNAVAILABLE", "智能体运行时未安装", 503) from exc
        runtime_env = _runtime_environment(self.settings, safe_context)
        namespace = safe_context.get("user_namespace", "").strip() or "__default__"
        try:
            with self._lock:
                harness = self._harnesses.get(namespace)
                if harness is None:
                    harness = self._new_harness(runtime_env, safe_context)
                    self._harnesses[namespace] = harness
                harness_started = time.perf_counter()
                prompt_text = render_prompt(_bounded_query_prompt(prompt), safe_context.get("user_brief", ""))
                result = harness.run(prompt_text, session_id=session_id)
                harness_finished = time.perf_counter()
        except TimeoutError as exc:
            raise AgentGatewayError("AGENT_TIMEOUT", "智能助手响应超时，请稍后重试", 504) from exc
        except AgentGatewayError:
            raise
        except Exception as exc:
            name = type(exc).__name__.lower()
            if "timeout" in name:
                raise AgentGatewayError("AGENT_TIMEOUT", "智能助手响应超时，请稍后重试", 504) from exc
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
    "HOME", "LANG", "LC_ALL", "TZ", "NODE_PATH",
}


def _bounded_query_prompt(prompt: str) -> str:
    """Keep the common uninspected-pond query on one bounded read path."""
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
            "ADP 写入约束：字段已完整。不要调用 adp_query、工作台、认证、管理或其它工具；"
            "只调用一次 adp_mutation，operation 必须使用 "
            "api.production_create_post_api_v1_production_resource，arguments 使用 "
            f"{json.dumps(arguments, ensure_ascii=False, separators=(',', ':'))}。"
            "只准备确认，不要调用确认接口；得到 confirmation_required 后立即停止。"
        )
    if "未巡检" not in normalized and "没有巡检" not in normalized:
        return prompt
    return (
        f"{prompt}\n\n"
        "ADP 查询约束：这是一个只读的未巡检塘口问题。只调用一次 adp_query，"
        "operation 使用 production.list_records，arguments 使用 "
        "{resource: 'daily-operations', uninspected_on: 'today', page: 1, page_size: 20}。"
        "不要调用工作台、管理员、仓库或其它查询工具，也不要重复调用；"
        "根据这一次结果直接回答，若没有匹配记录就明确说明。"
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
