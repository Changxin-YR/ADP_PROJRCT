"""网关的会话/权限/数据范围策略与审计留痕。

从 ``agent_gateway_service`` 拆出，让网关文件保持在 300 行预算内；行为与拆分前完全一致：

* 权限与数据范围检查合并为 :meth:`AgentGatewayPolicyMixin._authorize`，被拒时统一留失败审计；
* :meth:`AgentGatewayPolicyMixin._audit` 是所有审计事件唯一的出口，敏感字段在这里脱敏。
"""

from __future__ import annotations

from typing import Any, Callable

from backend.layers.common.security.data_scope import require_active_scope
from backend.layers.features.agent.agent_errors import AgentGatewayError
from backend.layers.features.agent.agent_tool_registry import AgentTool, permission_options


AuditWriter = Callable[[dict[str, Any]], None]

_SENSITIVE_KEYS = {
    "password", "password_hash", "token", "cookie", "authorization", "attachment",
    "session_hash", "session_token", "api_key", "secret", "credential", "csrf",
}

def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if any(marker in str(key).lower() for marker in _SENSITIVE_KEYS) else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


_UNKNOWN_TOOL = AgentTool(
    name="unknown",
    description="未登记的智能体操作",
    method="POST",
    path_template="/unknown",
    parameters={},
    required_permission=None,
    risk="write",
)


class AgentGatewayPolicyMixin:
    @staticmethod
    def session_hash(user: dict[str, Any]) -> str:
        value = str(user.get("_session_hash") or user.get("session_hash") or f"user:{user.get('id')}")
        return value

    @staticmethod
    def _require_session(user: dict[str, Any]) -> None:
        if not user or user.get("status") != "active":
            raise AgentGatewayError("UNAUTHENTICATED", "登录状态已失效，请重新登录", 401)

    @staticmethod
    def _require_authorization(user: dict[str, Any], tool: AgentTool, arguments: dict[str, Any]) -> None:
        permissions = set(user.get("permissions") or [])
        candidates = permission_options(tool, arguments)
        if candidates and not permissions.intersection(candidates):
            raise AgentGatewayError(
                "FORBIDDEN",
                "当前账号没有权限执行该操作",
                403,
                {"required_permissions_any": list(candidates)},
            )
        if tool.required_role:
            roles = {str(role.get("code")) for role in user.get("roles") or [] if isinstance(role, dict)}
            if tool.required_role not in roles:
                raise AgentGatewayError("FORBIDDEN", "当前账号角色无权执行该操作", 403)

    @staticmethod
    def _validate_arguments(tool: AgentTool, arguments: Any) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise AgentGatewayError("VALIDATION_ERROR", "工具参数必须是对象", 400)
        if tool.parameters.get("payload", {}).get("required") and not arguments:
            raise AgentGatewayError("VALIDATION_ERROR", "工具参数不能为空", 400)
        return dict(arguments)

    def _require_data_scope(self, user: dict[str, Any], tool: AgentTool) -> None:
        if not tool.requires_data_scope:
            return
        try:
            require_active_scope(user)
        except Exception as exc:
            raise AgentGatewayError("DATA_SCOPE_REQUIRED", "当前账号没有有效数据范围，拒绝访问业务数据", 403) from exc

    def _audit(
        self,
        user: dict[str, Any],
        tool: AgentTool,
        arguments: dict[str, Any],
        *,
        result: str,
        request_id: str,
        conversation_id: str | None = None,
        reason: str | None = None,
        confirmation_id: int | None = None,
        before: Any = None,
        after: Any = None,
    ) -> None:
        if self.audit is None:
            return
        self.audit({
            "user_id": user.get("id"),
            "authenticated_user_id": user.get("id"),
            "session_hash": "[REDACTED]" if user.get("_session_hash") else None,
            "raw_instruction": arguments.get("raw_instruction"),
            "intent": tool.name,
            "tool_name": tool.name,
            "method": tool.method,
            "path_template": tool.path_template,
            "arguments": _redact(arguments),
            "tool_arguments": _redact(arguments),
            "required_permission": tool.required_permission,
            "data_scope": _redact(user.get("data_scopes") or []),
            "confirmation_id": confirmation_id,
            "before": _redact(before),
            "after": _redact(after),
            "risk": tool.risk,
            "result": result,
            "request_id": request_id,
            "conversation_id": conversation_id,
            "reason": reason,
            "error": reason if result == "failure" else None,
            "source": "agent",
        })

    def _audit_session_denied(
        self,
        user: dict[str, Any],
        tool_name: str,
        arguments: dict[str, Any],
        *,
        request_id: str,
        conversation_id: str | None,
        reason: str,
    ) -> None:
        """会话失效也是被拒的写尝试，同样要留痕，否则滥用探针看不到这一类。"""
        try:
            tool = self.registry.require(tool_name)
        except Exception:  # noqa: BLE001 - 审计不能因为查不到工具而失败
            tool = _UNKNOWN_TOOL
        self._audit(
            user if isinstance(user, dict) else {},
            tool,
            arguments if isinstance(arguments, dict) else {},
            result="failure",
            request_id=request_id,
            conversation_id=conversation_id,
            reason=reason,
        )

    def _authorize(self, user: dict[str, Any], tool: AgentTool, arguments: dict[str, Any], *, request_id: str, conversation_id: str | None) -> None:
        """权限与数据范围检查合并在一处：被拒时统一留失败审计，规则只有一份。"""
        try:
            self._require_authorization(user, tool, arguments)
            self._require_data_scope(user, tool)
        except AgentGatewayError as error:
            self._audit(user, tool, arguments, result="failure", request_id=request_id, conversation_id=conversation_id, reason=error.code)
            raise

    def _context(self, user: dict[str, Any], request_id: str, **extra: Any) -> dict[str, Any]:
        context = {"user": user, "request_id": request_id}
        context.update(extra)
        return context
