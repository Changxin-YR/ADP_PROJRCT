from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from backend.config.settings import Settings
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError
from backend.layers.features.agent.agent_tool_registry import build_registry


class HarnessSidecar:
    """Small synchronous adapter around the optional DeepSeek Harness Python SDK."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._harnesses: dict[str, Any] = {}
        self._lock = threading.RLock()

    def _new_harness(self, runtime_env: dict[str, str], safe_context: dict[str, str]) -> Any:
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
                        "ADP_AGENT_TOOL_CATALOG": ", ".join(sorted(tool.name for tool in build_registry().tools)),
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
            if key in {"conversation_id", "request_id", "gateway_url", "context_token", "user_namespace"}
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
                result = harness.run(_bounded_query_prompt(prompt), session_id=session_id)
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
        if isinstance(result, dict):
            # Keep diagnostics numeric and payload-free so live latency can be
            # investigated without copying prompts, tool arguments, or keys.
            result.setdefault(
                "diagnostics",
                {
                    "request_received_ms": 0,
                    "harness_request_start_ms": round((harness_started - request_started) * 1000, 1),
                    "harness_response_ms": round((harness_finished - harness_started) * 1000, 1),
                    "total_ms": round((harness_finished - request_started) * 1000, 1),
                },
            )
            return result
        final_response = getattr(result, "final_response", None)
        if isinstance(final_response, str):
            return {
                "kind": "assistant",
                "message": final_response,
                "session_id": str(getattr(result, "session_id", session_id)),
                "diagnostics": {
                    "request_received_ms": 0,
                    "harness_request_start_ms": round((harness_started - request_started) * 1000, 1),
                    "harness_response_ms": round((harness_finished - harness_started) * 1000, 1),
                    "total_ms": round((harness_finished - request_started) * 1000, 1),
                },
            }
        raise AgentGatewayError("AGENT_PROTOCOL_ERROR", "智能助手返回格式无效", 502)


_HARNESS_ENV_LOCK = threading.Lock()
_ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "APPDATA", "LOCALAPPDATA",
    "HOME", "LANG", "LC_ALL", "TZ", "NODE_PATH",
}


def _bounded_query_prompt(prompt: str) -> str:
    """Keep the common uninspected-pond query on one bounded read path."""
    normalized = prompt.replace(" ", "")
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
