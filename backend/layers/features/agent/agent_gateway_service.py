from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from backend.config.settings import Settings
from backend.layers.common.governance.idempotency import execute_idempotent
from backend.layers.common.security.data_scope import require_active_scope
from backend.layers.features.agent.agent_confirmation_store import _hash_token
from backend.layers.features.agent.agent_contracts import AgentConfirmation, AgentConfirmationStore
from backend.layers.features.agent.agent_tool_registry import AgentTool, AgentToolRegistry, permission_options


class AgentGatewayError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.data = data


AuditWriter = Callable[[dict[str, Any]], None]

_SENSITIVE_KEYS = {"password", "password_hash", "token", "cookie", "authorization", "attachment"}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if any(marker in str(key).lower() for marker in _SENSITIVE_KEYS) else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class AgentGatewayService:
    def __init__(
        self,
        settings: Settings,
        *,
        registry: AgentToolRegistry,
        confirmations: AgentConfirmationStore,
        audit: AuditWriter | None = None,
        idempotent: Callable[..., tuple[dict[str, Any], int]] | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.confirmations = confirmations
        self.audit = audit
        self._idempotent = idempotent or execute_idempotent

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

    def _audit(self, user: dict[str, Any], tool: AgentTool, arguments: dict[str, Any], *, result: str, request_id: str, conversation_id: str | None = None, reason: str | None = None) -> None:
        if self.audit is None:
            return
        self.audit({
            "user_id": user.get("id"),
            "session_hash": user.get("_session_hash"),
            "tool_name": tool.name,
            "method": tool.method,
            "path_template": tool.path_template,
            "arguments": _redact(arguments),
            "risk": tool.risk,
            "result": result,
            "request_id": request_id,
            "conversation_id": conversation_id,
            "reason": reason,
            "source": "agent",
        })

    def _context(self, user: dict[str, Any], request_id: str, **extra: Any) -> dict[str, Any]:
        context = {"user": user, "request_id": request_id}
        context.update(extra)
        return context

    def prepare_tool(self, user: dict[str, Any], tool_name: str, arguments: dict[str, Any], *, conversation_id: str, request_id: str) -> dict[str, Any]:
        self._require_session(user)
        try:
            tool = self.registry.require(tool_name)
        except KeyError as exc:
            raise AgentGatewayError("TOOL_NOT_FOUND", "智能体操作不在允许范围内", 404) from exc

        arguments = self._validate_arguments(tool, arguments)
        self._require_authorization(user, tool, arguments)

        if tool.risk == "human_only":
            self._audit(user, tool, arguments, result="human_only", request_id=request_id, conversation_id=conversation_id, reason="身份/会话生命周期操作不允许委托")
            return {"kind": "human_only", "code": "HUMAN_REQUIRED", "message": "该操作会改变登录身份或会话，请由本人在系统页面完成"}

        self._require_data_scope(user, tool)

        if tool.risk == "read":
            if tool.execute is None:
                raise AgentGatewayError("TOOL_UNAVAILABLE", "该查询工具尚未连接业务服务", 503)
            try:
                data = tool.execute(arguments, self._context(user, request_id, session_token=user.get("_session_token")))
            except AgentGatewayError:
                raise
            except Exception as exc:
                raise AgentGatewayError("BUSINESS_ERROR", "业务查询未完成，请稍后重试", 400) from exc
            self._audit(user, tool, arguments, result="success", request_id=request_id, conversation_id=conversation_id)
            return {"kind": "success", "data": data, "request_id": request_id}

        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        confirmation = AgentConfirmation(
            id=0,
            idempotency_key=f"agent-confirmation:{request_id}",
            token_hash=_hash_token(token),
            user_id=int(user["id"]),
            session_hash=self.session_hash(user),
            conversation_id=conversation_id,
            request_id=request_id,
            tool_name=tool.name,
            payload=arguments,
            status="pending",
            expires_at=now + timedelta(seconds=self.settings.agent_confirmation_ttl_seconds),
        )
        saved = self.confirmations.create(confirmation, token)
        self._audit(user, tool, arguments, result="pending", request_id=request_id, conversation_id=conversation_id)

        admin_risk = tool.path_template.startswith("/api/v1/admin")
        risk_message = (
            "该操作会修改账号、角色或权限等高风险管理数据。请核对目标、参数和影响范围，确认后才会执行"
            if admin_risk
            else "该操作会修改业务数据，确认后才会执行"
        )
        return {
            "kind": "confirmation_required",
            "confirmation": {
                "id": saved.id,
                "token": token,
                "tool_name": tool.name,
                "summary": tool.description,
                "arguments": _redact(arguments),
                "risk": risk_message,
                "risk_level": "high" if admin_risk else "normal",
                "expires_at": saved.expires_at.isoformat(),
                "conversation_id": saved.conversation_id,
                "request_id": saved.request_id,
            },
        }

    def confirm(self, user: dict[str, Any], token: str, *, request_id: str) -> dict[str, Any]:
        self._require_session(user)
        if not token.strip():
            raise AgentGatewayError("CONFIRMATION_INVALID", "确认令牌无效", 409)

        session_hash = self.session_hash(user)
        pending = self.confirmations.find(token=token, user_id=int(user["id"]), session_hash=session_hash)
        if pending is None:
            raise AgentGatewayError("CONFIRMATION_INVALID", "确认令牌无效、已过期或已使用", 409)
        try:
            tool = self.registry.require(pending.tool_name)
        except KeyError as exc:
            raise AgentGatewayError("TOOL_NOT_FOUND", "该确认操作已失效，请重新发起", 409) from exc

        arguments = self._validate_arguments(tool, dict(pending.payload))
        # Authorization and data scope are deliberately re-evaluated at confirm
        # time so a permission/role/scope change invalidates an older pending action.
        self._require_authorization(user, tool, arguments)
        self._require_data_scope(user, tool)

        if tool.risk != "write" or tool.execute is None:
            raise AgentGatewayError("TOOL_UNAVAILABLE", "该写操作尚未连接业务服务", 503)

        pending = self.confirmations.claim(token=token, user_id=int(user["id"]), session_hash=session_hash)
        if pending is None:
            raise AgentGatewayError("CONFIRMATION_INVALID", "确认令牌无效、已过期或已使用", 409)

        try:
            body, status = self._idempotent(
                self.settings,
                user_id=int(user["id"]),
                action_code=f"agent:{tool.name}",
                key=pending.idempotency_key,
                payload=arguments,
                operation=lambda: (
                    tool.execute(
                        arguments,
                        self._context(
                            user,
                            request_id,
                            session_token=user.get("_session_token"),
                            idempotency_key=pending.idempotency_key,
                        ),
                    ),
                    200,
                ),
            )
        except AgentGatewayError:
            raise
        except Exception as exc:
            self._audit(user, tool, arguments, result="failure", request_id=request_id, conversation_id=pending.conversation_id, reason="业务执行失败")
            raise AgentGatewayError("BUSINESS_ERROR", "业务操作未完成，请在页面核对状态", 400) from exc

        self._audit(user, tool, arguments, result="success", request_id=request_id, conversation_id=pending.conversation_id)
        return {"kind": "success", "data": body, "status": status, "request_id": request_id}
