"""网关的会话/权限/数据范围策略与审计留痕。

从 ``agent_gateway_service`` 拆出，让网关文件保持在 300 行预算内；行为与拆分前完全一致：

* 权限与数据范围检查合并为 :meth:`AgentGatewayPolicyMixin._authorize`，被拒时统一留失败审计；
* :meth:`AgentGatewayPolicyMixin._audit` 是所有审计事件唯一的出口，敏感字段在这里脱敏。
"""

from __future__ import annotations

import re
from typing import Any, Callable

from backend.layers.common.security.data_scope import require_active_scope
from backend.layers.features.agent.agent_errors import AgentGatewayError
from backend.layers.features.agent.agent_tool_registry import AgentTool, permission_options
from backend.layers.features.agent.agent_field_guide import resources_for


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

_PATH_PARAMETER = re.compile(r"\{([^}]+)\}")
_ID_PARAMETER = re.compile(r"(?:^|_)id$", re.IGNORECASE)
_HIGH_RISK_MARKERS = {
    "all", "batch", "bulk",
    "approve", "archive", "cancel", "confirm", "convert", "correct", "corrections",
    "depreciate", "dispatch", "exports", "grants", "imports", "receive", "reject",
    "reverse", "retire", "revoke", "roles", "status", "submit", "verify",
}


def _value(arguments: dict[str, Any], name: str, payload: dict[str, Any]) -> Any:
    value = arguments.get(name)
    if value is None:
        value = payload.get(name)
    if value is None and name == "resource":
        value = arguments.get("resource_type", payload.get("resource_type"))
    return value


def _require_integer(name: str, value: Any, *, minimum: int | None = None, maximum: int | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgentGatewayError("VALIDATION_ERROR", f"{name} 必须是整数", 400)
    if minimum is not None and value < minimum:
        raise AgentGatewayError("VALIDATION_ERROR", f"{name} 不能小于 {minimum}", 400)
    if maximum is not None and value > maximum:
        raise AgentGatewayError("VALIDATION_ERROR", f"{name} 不能大于 {maximum}", 400)


def requires_confirmation(tool: AgentTool) -> bool:
    """Keep destructive, financial, administrative and irreversible writes human-gated."""
    if tool.risk != "write":
        return False
    path = str(tool.path_template or "").lower()
    if tool.method == "DELETE" or path.startswith("/api/v1/admin"):
        return True
    segments = [part for segment in path.strip("/").split("/") for part in re.split(r"[-_]", segment)]
    if any(segment in _HIGH_RISK_MARKERS for segment in segments):
        return True
    if any(path.startswith(prefix) for prefix in ("/api/v1/cost/", "/api/v1/purchase/", "/api/v1/sales/")):
        return True
    return False


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
        normalized = dict(arguments)
        payload = normalized.get("payload")
        if payload is not None and not isinstance(payload, dict):
            raise AgentGatewayError("VALIDATION_ERROR", "payload 必须是对象", 400)
        payload = payload if isinstance(payload, dict) else {}

        for name in _PATH_PARAMETER.findall(tool.path_template):
            value = _value(normalized, name, payload)
            if value in (None, ""):
                raise AgentGatewayError("VALIDATION_ERROR", f"缺少路径参数 {name}", 400)
            if _ID_PARAMETER.search(name):
                _require_integer(name, value, minimum=1)

        resource_values = resources_for(tool.path_template)
        if resource_values:
            resource = _value(normalized, "resource", payload)
            if resource not in resource_values:
                raise AgentGatewayError("VALIDATION_ERROR", "resource 不是已登记的业务类型", 400)

        for name, schema in tool.parameters.items():
            value = normalized.get(name)
            if value is None:
                value = payload.get(name)
            if value is None:
                continue
            if name in {"page", "page_size"}:
                _require_integer(name, value, minimum=int(schema.get("minimum", 1)), maximum=schema.get("maximum"))
            elif name == "expected_version":
                _require_integer(name, value, minimum=1)
            elif name in {"keyword", "status", "uninspected_on"} and not isinstance(value, str):
                raise AgentGatewayError("VALIDATION_ERROR", f"{name} 必须是字符串", 400)
        return normalized

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
        permission_codes = {"FORBIDDEN", "PERMISSION_DENIED", "AUTHORIZATION_REQUIRED"}
        scope_codes = {"DATA_SCOPE_REQUIRED", "DATA_SCOPE_FORBIDDEN", "SCOPE_FORBIDDEN"}
        permission_result = not (result == "failure" and reason in permission_codes)
        datascope_result = not (result == "failure" and reason in scope_codes)
        payload = arguments.get("payload") if isinstance(arguments.get("payload"), dict) else {}
        target_resource = arguments.get("resource") or arguments.get("resource_type") or payload.get("resource")
        self.audit({
            "user_id": user.get("id"),
            "authenticated_user_id": user.get("id"),
            "session_hash": "[REDACTED]" if user.get("_session_hash") else None,
            "raw_instruction": arguments.get("raw_instruction"),
            "original_prompt": arguments.get("raw_instruction"),
            "intent": tool.name,
            "tool_name": tool.name,
            "method": tool.method,
            "path_template": tool.path_template,
            "arguments": _redact(arguments),
            "tool_arguments": _redact(arguments),
            "required_permission": tool.required_permission,
            "data_scope": _redact(user.get("data_scopes") or []),
            "roles": _redact(user.get("roles") or []),
            "target_resource": target_resource,
            "permission_result": permission_result,
            "datascope_result": datascope_result,
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
