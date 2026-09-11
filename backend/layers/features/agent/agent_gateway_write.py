"""直连写模式的执行体：权限通过后立即落地，失败按人工确认路径同等收口。

从 ``agent_gateway_service`` 拆出，既让网关保持在 300 行预算内，也把「写操作怎么落地、
怎么写审计、失败怎么翻译成人话」集中在一处。
"""

from __future__ import annotations

from typing import Any

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.agent.agent_errors import AgentGatewayError
from backend.layers.features.agent.agent_humanize import action_title, resource_code
from backend.layers.features.agent.agent_write_execution import describe_success, execution_payload


class DirectWriteMixin:
    """由 :class:`AgentGatewayService` 混入；依赖网关的 ``_idempotent`` / ``_audit`` / ``_context``。"""

    def _execute_write(
        self,
        user: dict[str, Any],
        tool: Any,
        arguments: dict[str, Any],
        *,
        conversation_id: str,
        request_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """直接执行写操作并返回人话结果；失败与人工确认路径同口径收口。"""
        if tool.execute is None:
            raise AgentGatewayError("TOOL_UNAVAILABLE", "该写操作尚未连接业务服务", 503)
        try:
            body, status = self._idempotent(
                self.settings,
                user_id=int(user["id"]),
                action_code=f"agent:{tool.name}",
                key=idempotency_key,
                payload=arguments,
                operation=lambda: (
                    tool.execute(
                        arguments,
                        # 幂等只在网关这一层预留（键 = agent-direct:<工具>:<请求ID>）：同一个键
                        # 不再转发给内层业务路由，避免「一个请求在两套账本里各占一行」的自锁风险。
                        # 重放由网关直接回放首次响应，业务 executor 不会被调用第二次。
                        self._context(user, request_id, session_token=user.get("_session_token")),
                    ),
                    200,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - 统一翻译成业务话术后重抛
            reason = exc.code if isinstance(exc, (AgentGatewayError, DomainError)) else "业务执行失败"
            self._audit(
                user, tool, arguments,
                result="failure",
                request_id=request_id,
                conversation_id=conversation_id,
                reason=reason,
            )
            if isinstance(exc, AgentGatewayError):
                raise AgentGatewayError(exc.code, self._failure_message(tool, arguments, exc.message), exc.status, exc.data) from exc
            if isinstance(exc, DomainError):
                # 幂等冲突/进行中这类治理错误必须原样透出，否则运营无法判断该重试还是不该重试。
                raise AgentGatewayError(
                    exc.code,
                    self._failure_message(tool, arguments, exc.message),
                    exc.status,
                    getattr(exc, "data", None),
                ) from exc
            raise AgentGatewayError(
                "BUSINESS_ERROR",
                self._failure_message(tool, arguments, "业务操作未完成，请在页面核对状态"),
                400,
            ) from exc

        self._audit(
            user, tool, arguments,
            result="success",
            request_id=request_id,
            conversation_id=conversation_id,
            before=body.get("before") if isinstance(body, dict) else None,
            after=body.get("after") if isinstance(body, dict) else None,
        )
        return self._executed_payload(tool, arguments, body, status=status, request_id=request_id)

    def _executed_payload(
        self,
        tool: Any,
        arguments: dict[str, Any],
        body: Any,
        *,
        status: int,
        request_id: str,
    ) -> dict[str, Any]:
        """统一的「已执行」返回结构，人工确认与直连写共用。"""
        return {
            "kind": "executed",
            "status": status,
            "request_id": request_id,
            "message": describe_success(tool, arguments, body),
            "execution": execution_payload(tool, arguments, body),
            "data": body,
        }

    @staticmethod
    def _failure_message(tool: Any, arguments: dict[str, Any], reason: str) -> str:
        action = action_title(tool.method, tool.path_template, resource=resource_code(tool.path_template, arguments))
        return f"{action}没做成。{reason}"
