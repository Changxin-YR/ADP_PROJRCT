from __future__ import annotations

import json
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
        session_id = safe_context.get("conversation_id")
        if not session_id:
            raise AgentGatewayError("VALIDATION_ERROR", "缺少对话标识", 400)
        try:
            from deepseek_harness import DeepSeekHarness
        except ImportError as exc:
            raise AgentGatewayError("AGENT_UNAVAILABLE", "智能体运行时未安装", 503) from exc
        try:
            with DeepSeekHarness(
                dsh_home=self.settings.agent_sidecar_home,
                cwd=self.settings.agent_sidecar_cwd,
                dsh_bin=self.settings.agent_sidecar_command or None,
                profile="sdk",
                request_timeout_seconds=float(self.settings.agent_request_timeout_seconds),
            ) as harness:
                result = harness.run(
                    json.dumps({"prompt": prompt, "context": safe_context}, ensure_ascii=False),
                    session_id=session_id,
                )
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
