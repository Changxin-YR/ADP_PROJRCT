from __future__ import annotations

import json
import os
import threading
from typing import Any

from backend.config.settings import Settings
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError


class HarnessSidecar:
    """Small synchronous adapter around the optional DeepSeek Harness Python SDK."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self, prompt: str, *, context: dict[str, str]) -> dict[str, Any]:
        safe_context = {
            key: str(value)
            for key, value in context.items()
            if key in {"conversation_id", "request_id", "gateway_url", "context_token"}
            and value is not None
        }
        if not safe_context.get("conversation_id"):
            raise AgentGatewayError("VALIDATION_ERROR", "缺少对话标识", 400)
        session_id = safe_context.get("request_id") or safe_context["conversation_id"]
        try:
            from deepseek_harness import DeepSeekHarness
        except ImportError as exc:
            raise AgentGatewayError("AGENT_UNAVAILABLE", "智能体运行时未安装", 503) from exc
        runtime_env = _runtime_environment(self.settings, safe_context)
        patch = self.settings.agent_sidecar_patch.strip()
        patches = (patch,) if patch else ()
        try:
            # HarnessClient snapshots os.environ when starting its child process.
            # Serialize that short setup window so concurrent web requests cannot
            # observe the restricted environment.
            with _HARNESS_ENV_LOCK:
                previous = dict(os.environ)
                try:
                    os.environ.clear()
                    os.environ.update(runtime_env)
                    with DeepSeekHarness(
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
                        },
                    ) as harness:
                        result = harness.run(prompt, session_id=session_id)
                finally:
                    os.environ.clear()
                    os.environ.update(previous)
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
            return result
        final_response = getattr(result, "final_response", None)
        if isinstance(final_response, str):
            return {
                "kind": "assistant",
                "message": final_response,
                "session_id": str(getattr(result, "session_id", session_id)),
            }
        raise AgentGatewayError("AGENT_PROTOCOL_ERROR", "智能助手返回格式无效", 502)


_HARNESS_ENV_LOCK = threading.Lock()
_ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "APPDATA", "LOCALAPPDATA",
    "HOME", "LANG", "LC_ALL", "TZ", "NODE_PATH",
}


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
