from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from backend.config.settings import Settings
from backend.layers.common.governance.idempotency import execute_idempotent
from backend.layers.common.security.data_scope import require_active_scope
from backend.layers.features.agent.agent_confirmation_store import _hash_token
from backend.layers.features.agent.agent_confirmation_work_item import (
    cancel_confirmation_work_item,
    complete_confirmation_work_item,
    open_confirmation_work_item,
)
from backend.layers.features.agent.agent_errors import AgentGatewayError
from backend.layers.features.agent.agent_gateway_policy import (
    AgentGatewayPolicyMixin,
    _redact,  # re-exported for callers that build confirmation cards here
)
from backend.layers.features.agent.agent_gateway_write import DirectWriteMixin
from backend.layers.features.agent.agent_humanize import action_title, change_rows, resource_code, target_label
from backend.layers.features.agent.agent_labels import RISK_ADMIN, RISK_NORMAL
from backend.layers.features.agent.agent_contracts import AgentConfirmation, AgentConfirmationStore
from backend.layers.features.agent.agent_tool_registry import AgentTool, AgentToolRegistry, permission_options


class AgentGatewayService(DirectWriteMixin, AgentGatewayPolicyMixin):
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

    def prepare_tool(self, user: dict[str, Any], tool_name: str, arguments: dict[str, Any], *, conversation_id: str, request_id: str) -> dict[str, Any]:
        try:
            self._require_session(user)
        except AgentGatewayError as error:
            # 会话失效也是被拒的写尝试，同样要留痕，否则滥用探针看不到这一类。
            self._audit_session_denied(user, tool_name, arguments, request_id=request_id, conversation_id=conversation_id, reason=error.code)
            raise
        try:
            tool = self.registry.require(tool_name)
        except KeyError as exc:
            raise AgentGatewayError("TOOL_NOT_FOUND", "智能体操作不在允许范围内", 404) from exc

        arguments = self._validate_arguments(tool, arguments)
        self._authorize(user, tool, arguments, request_id=request_id, conversation_id=conversation_id)

        if tool.risk == "human_only":
            self._audit(user, tool, arguments, result="human_only", request_id=request_id, conversation_id=conversation_id, reason="身份/会话生命周期操作不允许委托")
            return {"kind": "human_only", "code": "HUMAN_REQUIRED", "message": "该操作会改变登录身份或会话，请由本人在系统页面完成"}

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

        if tool.execute is None:
            raise AgentGatewayError("TOOL_UNAVAILABLE", "该写操作尚未连接业务服务", 503)
        if self.write_mode == "direct":
            # 已确认放开：权限与数据范围通过后直接落地，审计留痕与人工确认路径一致。
            return self._execute_write(
                user, tool, arguments,
                conversation_id=conversation_id,
                request_id=request_id,
                idempotency_key=f"agent-direct:{tool.name}:{request_id}",
            )

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
        # 统一待办：写操作待确认时为发起人建待办，与业务核验待办同队列。
        self.open_confirmation_work_item(saved, tool, user)
        self._audit(user, tool, arguments, result="pending", request_id=request_id, conversation_id=conversation_id)

        admin_risk = tool.path_template.startswith("/api/v1/admin")
        risk_message = RISK_ADMIN if admin_risk else RISK_NORMAL
        action = action_title(tool.method, tool.path_template, resource=resource_code(tool.path_template, arguments))
        target = target_label(tool.path_template, arguments)
        return {
            "kind": "confirmation_required",
            "message": f"即将{action}，确认后立即生效。",
            "confirmation": {
                "id": saved.id,
                "token": token,
                "tool_name": tool.name,
                "summary": action,
                "target": target,
                "changes": change_rows(arguments),
                "arguments": _redact(arguments),
                "risk": risk_message,
                "risk_level": "high" if admin_risk else "normal",
                "expires_at": saved.expires_at.isoformat(),
                "conversation_id": saved.conversation_id,
                "request_id": saved.request_id,
            },
        }

    # ===== 统一待办的接缝（seam）=====
    # 刻意做成实例方法而不是在调用点直接引用模块函数：模块级导入会在调用点绑定，
    # 测试替身无法拦截。做成接缝后，测试可覆写实例或子类，也让"待办只是增强能力、
    # 失败必须降级"这一契约有唯一的覆写点。
    def open_confirmation_work_item(self, confirmation: Any, tool: Any, user: dict[str, Any]) -> int | None:
        return open_confirmation_work_item(self.settings, confirmation=confirmation, tool=tool, user=user)

    def complete_confirmation_work_item(self, confirmation_id: int, user: dict[str, Any]) -> None:
        complete_confirmation_work_item(self.settings, confirmation_id=confirmation_id, user_id=int(user["id"]))

    def cancel_confirmation_work_item(self, confirmation_id: int, user: dict[str, Any]) -> None:
        cancel_confirmation_work_item(self.settings, confirmation_id=confirmation_id, user_id=int(user["id"]))

    @property
    def write_mode(self) -> str:
        """写操作策略：``direct`` 立即落地，``confirm`` 先出确认卡片。"""
        mode = str(getattr(self.settings, "agent_write_mode", "direct") or "direct").strip().lower()
        return mode if mode in {"direct", "confirm"} else "direct"

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
        try:
            self._require_authorization(user, tool, arguments)
        except AgentGatewayError as error:
            self._audit(user, tool, arguments, result="failure", request_id=request_id, conversation_id=pending.conversation_id, reason=error.code)
            raise
        try:
            self._require_data_scope(user, tool)
        except AgentGatewayError as error:
            self._audit(user, tool, arguments, result="failure", request_id=request_id, conversation_id=pending.conversation_id, reason=error.code)
            raise

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
        except Exception as exc:
            self.confirmations.mark_failed(pending.id, user_id=int(user["id"]))
            self.cancel_confirmation_work_item(pending.id, user)
            reason = exc.code if isinstance(exc, AgentGatewayError) else "业务执行失败"
            self._audit(user, tool, arguments, result="failure", request_id=request_id, conversation_id=pending.conversation_id, confirmation_id=pending.id, reason=reason)
            if isinstance(exc, AgentGatewayError):
                raise
            raise AgentGatewayError("BUSINESS_ERROR", "业务操作未完成，请在页面核对状态", 400) from exc

        before = body.get("before") if isinstance(body, dict) else None
        after = body.get("after") if isinstance(body, dict) else None
        self._audit(
            user,
            tool,
            arguments,
            result="success",
            request_id=request_id,
            conversation_id=pending.conversation_id,
            confirmation_id=pending.id,
            before=before,
            after=after,
        )
        self.complete_confirmation_work_item(pending.id, user)
        return self._executed_payload(tool, arguments, body, status=status, request_id=request_id)
