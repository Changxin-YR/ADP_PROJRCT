from __future__ import annotations

import base64
import hashlib
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, Response, current_app, g, jsonify, request

from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.http.request_helpers import json_object, require_csrf
from backend.layers.common.http.response import fail, ok
from backend.layers.common.security.csrf import CsrfError
from backend.layers.common.security.session import hash_session_token, request_session_token
from backend.layers.features.auth.auth_contracts import AuthServiceError
from backend.layers.features.auth.auth_service import AuthService
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError
from backend.layers.features.agent.agent_confirmation_store import MySqlAgentConfirmationStore
from backend.layers.features.agent import agent_stream
from backend.layers.features.agent.agent_gateway_service import AgentGatewayService
from backend.layers.product.agent.agent_dispatch import _dispatch_fixed_tool, dispatch_fixed_tool  # noqa: F401
from backend.layers.features.agent.agent_prompt import build_user_brief, turn_prompt_context
from backend.layers.features.agent.agent_tool_registry import AgentTool, build_registry
from backend.layers.features.agent.harness_sidecar import HarnessSidecar


_AGENT_CONTEXT_TTL_SECONDS = 180


def _context_cipher(settings: Settings) -> Fernet:
    """Derive an authenticated-encryption key dedicated to Agent delegation.

    The delegated context carries the existing web session token only in
    encrypted form. Because it is self-contained, any Gunicorn worker can
    validate it without a process-local cache.
    """
    material = f"adp-agent-context-v1:{settings.flask_secret_key}".encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


def _issue_context(settings: Settings, session_token: str) -> str:
    if not session_token:
        raise AgentGatewayError("UNAUTHENTICATED", "当前会话不能委托给智能体", 401)
    return _context_cipher(settings).encrypt(session_token.encode("utf-8")).decode("ascii")


def _decode_context_token(settings: Settings, token: str) -> str | None:
    if not token:
        return None
    try:
        value = _context_cipher(settings).decrypt(
            token.encode("ascii"),
            ttl=_AGENT_CONTEXT_TTL_SECONDS,
        )
        return value.decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError):
        return None


def _context_session_token(settings: Settings) -> str | None:
    token = request.headers.get("X-Agent-Context", "").strip()
    return _decode_context_token(settings, token)


def create_agent_blueprint(settings: Settings, auth_store: Any, gateway: Any | None = None, sidecar: Any | None = None) -> Blueprint:
    """Expose the authenticated boundary used by the Harness sidecar and Vue panel."""
    blueprint = Blueprint("agent", __name__, url_prefix="/api/v1/agent")
    auth = AuthService(auth_store, settings)
    if gateway is None:
        def audit(event: dict[str, Any]) -> None:
            writer = getattr(auth_store, "audit_event", None)
            if callable(writer):
                writer(
                    action="agent_tool",
                    object_type="agent_tool",
                    object_ref=str(event.get("tool_name") or "agent"),
                    user_id=event.get("user_id"),
                    result=str(event.get("result") or "failure"),
                    request_id=event.get("request_id"),
                    reason=event.get("reason"),
                    before=event.get("before"),
                    after=event.get("after"),
                    detail=event,
                )
        gateway = AgentGatewayService(
            settings,
            registry=build_registry(lambda tool: lambda arguments, context: dispatch_fixed_tool(tool, arguments, context, settings)),
            confirmations=MySqlAgentConfirmationStore(settings),
            audit=audit,
        )
    sidecar = sidecar or HarnessSidecar(settings)

    def current_user() -> dict[str, Any]:
        session_token = request_session_token(request) or _context_session_token(settings)
        user = auth.current_user(session_token, request_id=getattr(g, "request_id", None))
        if session_token:
            # Keep the confirmation bound to this session without exposing the raw token.
            user["_session_hash"] = hash_session_token(session_token)
            user["_session_token"] = session_token
        return user

    def error_response(error: Exception, fallback: str = "AGENT_REQUEST_FAILED") -> tuple[Response, int]:
        status = 403 if isinstance(error, CsrfError) else int(getattr(error, "status", 400))
        message = getattr(error, "message", str(error))
        return jsonify(fail(getattr(error, "code", fallback), message, status, data=getattr(error, "data", None))), status

    def conversation_id(payload: dict[str, Any]) -> str:
        value = payload.get("conversation_id")
        if value is None:
            return uuid4().hex
        if not isinstance(value, str) or not value.strip() or len(value) > 64:
            raise AgentGatewayError("VALIDATION_ERROR", "conversation_id 必须是 1-64 个字符", 400)
        return value.strip()

    @blueprint.post("/turn")
    def turn() -> tuple[Response, int] | Response:
        try:
            user = current_user()
            require_csrf()
            payload = json_object()
            message = payload.get("message")
            if not isinstance(message, str) or not message.strip():
                raise AgentGatewayError("VALIDATION_ERROR", "请输入要执行的指令", 400)
            if len(message.strip()) > 4000:
                raise AgentGatewayError("VALIDATION_ERROR", "指令长度不能超过 4000 个字符", 400)
            runner = getattr(gateway, "run_turn", None)
            conversation = conversation_id(payload)
            if callable(runner):
                safe_user = {key: value for key, value in user.items() if key != "_session_token"}
                result = runner(safe_user, message.strip(), conversation_id=conversation, request_id=str(getattr(g, "request_id", "")))
            elif sidecar is not None:
                session_token = str(request_session_token(request) or "")
                result = sidecar.run(
                    message.strip(),
                    context={
                        "conversation_id": conversation,
                        "request_id": str(getattr(g, "request_id", "")),
                        "gateway_url": settings.agent_gateway_url or request.host_url.rstrip("/") + "/api/v1/agent",
                        "context_token": _issue_context(settings, session_token),
                        # Namespace Harness sessions by the authenticated web
                        # session so two users choosing the same conversation_id
                        # can never share model history.
                        "user_namespace": hash_session_token(session_token)[:16],
                        "user_brief": build_user_brief(user),  # 让模型自己回答"我有哪些权限"
                        **turn_prompt_context(payload),  # 当前页面 + 最近对话（客户端携带）
                    },
                )
            else:
                operation = str(payload.get("operation") or payload.get("tool_name") or "").strip()
                arguments = payload.get("arguments")
                if not operation or not isinstance(arguments, dict):
                    raise AgentGatewayError("AGENT_UNAVAILABLE", "智能体服务暂时不可用，请稍后重试", 503)
                result = gateway.prepare_tool(user, operation, arguments, conversation_id=conversation_id(payload), request_id=str(getattr(g, "request_id", "")))
            if isinstance(result, dict):
                result.setdefault("conversation_id", conversation)
            return jsonify(ok(result))
        except (CsrfError, AuthServiceError, AgentGatewayError, DomainError) as error:
            return error_response(error)
        except (TypeError, ValueError):
            return error_response(AgentGatewayError("VALIDATION_ERROR", "请求参数无效", 400))

    @blueprint.post("/turn/stream")
    def turn_stream() -> Response:
        """Same turn as /turn, but streamed as NDJSON so the panel can render tokens."""
        try:
            user = current_user()
            require_csrf()
            payload = json_object()
            message = payload.get("message")
            if not isinstance(message, str) or not message.strip():
                raise AgentGatewayError("VALIDATION_ERROR", "请输入要执行的指令", 400)
            if len(message.strip()) > 4000:
                raise AgentGatewayError("VALIDATION_ERROR", "指令长度不能超过 4000 个字符", 400)
            conversation = conversation_id(payload)
        except (CsrfError, AuthServiceError, AgentGatewayError, DomainError) as error:
            return error_response(error)
        except (TypeError, ValueError):
            return error_response(AgentGatewayError("VALIDATION_ERROR", "请求参数无效", 400))
        if sidecar is None:
            return error_response(AgentGatewayError("AGENT_UNAVAILABLE", "智能体服务暂时不可用，请稍后重试", 503))
        session_token = str(request_session_token(request) or "")
        context = {
            "conversation_id": conversation,
            "request_id": str(getattr(g, "request_id", "")),
            "gateway_url": settings.agent_gateway_url or request.host_url.rstrip("/") + "/api/v1/agent",
            "context_token": _issue_context(settings, session_token),
            "user_namespace": hash_session_token(session_token)[:16],
            "user_brief": build_user_brief(user),
            **turn_prompt_context(payload),
        }
        stream = agent_stream.stream_turn(
            sidecar.run,
            message.strip(),
            context=context,
            timeout_seconds=float(settings.agent_request_timeout_seconds),
        )
        response = Response(stream, mimetype="application/x-ndjson")
        response.headers["Cache-Control"] = "no-cache, no-transform"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    @blueprint.post("/confirm")
    def confirm() -> tuple[Response, int] | Response:
        try:
            user = current_user()
            require_csrf()
            payload = json_object()
            token = payload.get("token", "")
            if not isinstance(token, str):
                raise AgentGatewayError("VALIDATION_ERROR", "确认令牌必须是字符串", 400)
            result = gateway.confirm(user, token, request_id=str(getattr(g, "request_id", "")))
            return jsonify(ok(result))
        except (CsrfError, AuthServiceError, AgentGatewayError, DomainError) as error:
            return error_response(error)
        except (TypeError, ValueError):
            return error_response(AgentGatewayError("VALIDATION_ERROR", "请求参数无效", 400))

    def operation_request(payload: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
        operation = str(payload.get("operation") or payload.get("tool_name") or "").strip()
        arguments = payload.get("arguments")
        if not operation or not isinstance(arguments, dict):
            raise AgentGatewayError("VALIDATION_ERROR", "请提供 operation 和对象类型 arguments", 400)
        return arguments, operation, conversation_id(payload)

    @blueprint.post("/query")
    def query() -> tuple[Response, int] | Response:
        try:
            if request.headers.get("X-Agent-Context"):
                if _context_session_token(settings) is None or request.cookies.get("adp_session"):
                    raise AgentGatewayError("AGENT_CONTEXT_INVALID", "智能体上下文无效", 401)
            else:
                require_csrf()
            user = current_user(); arguments, operation, conversation = operation_request(json_object())
            result = gateway.prepare_tool(user, operation, arguments, conversation_id=conversation, request_id=str(getattr(g, "request_id", "")))
            if result.get("kind") != "success":
                raise AgentGatewayError("TOOL_RISK_INVALID", "查询工具未按只读策略注册", 409)
            return jsonify(ok(result))
        except (CsrfError, AuthServiceError, AgentGatewayError, TypeError, ValueError) as error:
            return error_response(error)

    @blueprint.post("/prepare")
    def prepare() -> tuple[Response, int] | Response:
        try:
            if request.headers.get("X-Agent-Context"):
                if _context_session_token(settings) is None or request.cookies.get("adp_session"):
                    raise AgentGatewayError("AGENT_CONTEXT_INVALID", "智能体上下文无效", 401)
            else:
                require_csrf()
            user = current_user(); arguments, operation, conversation = operation_request(json_object())
            return jsonify(ok(gateway.prepare_tool(user, operation, arguments, conversation_id=conversation, request_id=str(getattr(g, "request_id", "")))))
        except (CsrfError, AuthServiceError, AgentGatewayError, TypeError, ValueError) as error:
            return error_response(error)

    @blueprint.post("/cancel")
    def cancel() -> tuple[Response, int] | Response:
        try:
            require_csrf(); user = current_user(); payload = json_object()
            confirmation_id = int(payload.get("confirmation_id") or 0)
            if confirmation_id <= 0 or not gateway.confirmations.mark_cancelled(confirmation_id, user_id=int(user["id"])):
                raise AgentGatewayError("CONFIRMATION_INVALID", "确认操作不存在或已处理", 409)
            return jsonify(ok({"cancelled": True}))
        except (CsrfError, AuthServiceError, AgentGatewayError, TypeError, ValueError) as error:
            return error_response(error)

    return blueprint
