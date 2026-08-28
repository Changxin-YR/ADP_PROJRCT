from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Blueprint, Response, g, jsonify, request, session

from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.http.request_helpers import json_object, require_csrf
from backend.layers.common.http.response import fail, ok
from backend.layers.common.security.csrf import CsrfError, generate_csrf_token
from backend.layers.common.security.password import hash_password
from backend.layers.common.security.session import hash_session_token, new_session_token, request_session_token
from backend.layers.common.validation.auth_validation import ValidationError, validate_password
from backend.layers.features.auth.auth_service import AuthService, AuthServiceError
from backend.layers.features.registration.registration_service import RegistrationService, RegistrationServiceError


def create_auth_blueprint(settings: Settings, store: Any) -> Blueprint:
    blueprint = Blueprint("auth", __name__, url_prefix="/api/v1/auth")
    auth_service = AuthService(store, settings)
    registration_service = RegistrationService(store, settings)

    def error_response(error: Exception, fallback_code: str, fallback_status: int) -> tuple[Response, int]:
        code = getattr(error, "code", fallback_code)
        status = int(getattr(error, "status", fallback_status))
        data = getattr(error, "data", None)
        response = jsonify(fail(code, getattr(error, "message", str(error)), status, data=data))
        retry_after = getattr(error, "retry_after", None)
        if retry_after is None and isinstance(data, dict):
            retry_after = data.get("retry_after")
        if retry_after is not None:
            response.headers["Retry-After"] = str(int(retry_after))
        return response, status

    def csrf_required() -> None:
        require_csrf()

    def session_token() -> str | None:
        return request_session_token(request)

    def set_session_cookie(response: Response, token: str) -> Response:
        response.set_cookie(
            "adp_session",
            token,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="Lax",
            max_age=12 * 60 * 60,
            path="/",
        )
        return response

    def issue_session(user_id: int, *, ip: str, user_agent: str, max_sessions: int = 2) -> tuple[str, datetime]:
        token = new_session_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
        store.create_session(
            user_id,
            token_hash=hash_session_token(token),
            ip=ip,
            user_agent=user_agent[:255],
            expires_at=expires_at,
            max_sessions=max_sessions,
        )
        return token, expires_at

    @blueprint.get("/csrf")
    def csrf() -> Response:
        token = generate_csrf_token(settings.csrf_secret_key)
        session["csrf_token"] = token
        return jsonify(ok({"csrf_token": token}))

    @blueprint.post("/login")
    def login() -> tuple[Response, int] | Response:
        try:
            csrf_required()
            payload = json_object()
            identifier = str(payload.get("identifier", "")).strip()
            password = str(payload.get("password", ""))
            if not identifier or not password:
                raise AuthServiceError("VALIDATION_ERROR", "请输入登录标识和密码", 400)
            result = auth_service.login(
                identifier,
                password,
                ip=request.remote_addr or "unknown",
                user_agent=request.user_agent.string,
                request_id=getattr(g, "request_id", None),
            )
            session_data = {"expires_at": result["expires_at"].isoformat()}
            if request.headers.get("X-ADP-Client") == "mobile":
                session_data["token"] = result["session_token"]
            response = jsonify(ok({"user": result["user"], "next_path": result["next_path"], "session": session_data}))
            return set_session_cookie(response, result["session_token"])
        except (CsrfError, AuthServiceError, DomainError) as error:
            return error_response(error, "LOGIN_FAILED", 400)

    @blueprint.post("/logout")
    def logout() -> tuple[Response, int] | Response:
        try:
            csrf_required()
            auth_service.logout(session_token(), request_id=getattr(g, "request_id", None), ip=request.remote_addr or "unknown")
            response = jsonify(ok(message="已退出登录"))
            response.delete_cookie("adp_session", path="/")
            return response
        except (CsrfError, AuthServiceError) as error:
            return error_response(error, "LOGOUT_FAILED", 400)

    @blueprint.get("/me")
    def me() -> tuple[Response, int] | Response:
        try:
            user, auth_session = auth_service.current_session(session_token(), request_id=getattr(g, "request_id", None))
            expires_at = auth_session["expires_at"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            return jsonify(ok({"user": user, "next_path": auth_service.next_path(user["status"]), "session": {"expires_at": expires_at.astimezone(timezone.utc).isoformat()}}))
        except AuthServiceError as error:
            return error_response(error, "UNAUTHENTICATED", 401)

    @blueprint.post("/password/change")
    def change_password() -> tuple[Response, int] | Response:
        try:
            csrf_required()
            user = auth_service.current_user(
                session_token(),
                request_id=getattr(g, "request_id", None),
                allow_password_change=True,
            )
            payload = json_object()
            validate_password(payload.get("new_password", ""), payload.get("confirm_password"))
            auth_service.change_password(
                user["id"],
                payload.get("current_password"),
                payload.get("new_password", ""),
                hash_password(payload["new_password"]),
                current_user=user,
                request_id=getattr(g, "request_id", None),
                ip=request.remote_addr or "unknown",
            )
            return jsonify(ok({"next_path": "/workbench"}, message="密码修改成功"))
        except (CsrfError, AuthServiceError, ValidationError, DomainError) as error:
            return error_response(error, "PASSWORD_CHANGE_FAILED", 400)

    @blueprint.get("/register/options")
    def register_options() -> Response:
        """公开字典：7 种在用角色 + 基地 + 三级数据范围（farm/area/personal），供注册页使用。"""
        options = store.list_registration_options()
        return jsonify(ok(options))

    @blueprint.post("/register")
    def register() -> tuple[Response, int] | Response:
        try:
            csrf_required()
            result = registration_service.register(
                json_object(),
                ip=request.remote_addr or "unknown",
            )
            token, expires_at = issue_session(
                result["user"]["id"],
                ip=request.remote_addr or "unknown",
                user_agent=request.user_agent.string,
                max_sessions=settings.session_pending_limit,
            )
            session_data = {"expires_at": expires_at.isoformat()}
            if request.headers.get("X-ADP-Client") == "mobile":
                session_data["token"] = token
            response = jsonify(ok({**result, "status": "pending", "next_path": "/auth/pending", "session": session_data}, message="注册申请已提交"))
            response.status_code = 201
            return set_session_cookie(response, token)
        except (CsrfError, RegistrationServiceError, DomainError) as error:
            return error_response(error, "REGISTRATION_FAILED", 400)

    @blueprint.get("/application")
    def application() -> tuple[Response, int] | Response:
        try:
            user = auth_service.current_user(session_token(), request_id=getattr(g, "request_id", None))
            return jsonify(ok({"application": registration_service.get_application(user["id"])}))
        except AuthServiceError as error:
            return error_response(error, "UNAUTHENTICATED", 401)

    @blueprint.patch("/application")
    def resubmit_application() -> tuple[Response, int] | Response:
        try:
            csrf_required()
            user = auth_service.current_user(session_token(), request_id=getattr(g, "request_id", None))
            result = registration_service.resubmit(user["id"], json_object())
            return jsonify(ok({"application": result, "status": "pending"}, message="申请已重新提交"))
        except (CsrfError, AuthServiceError, RegistrationServiceError, DomainError) as error:
            return error_response(error, "REGISTRATION_FAILED", 400)

    @blueprint.get("/workbench")
    def workbench() -> tuple[Response, int] | Response:
        try:
            user = auth_service.current_user(session_token(), request_id=getattr(g, "request_id", None))
            if user["status"] != "active":
                return jsonify(fail("FORBIDDEN", "当前账号尚未获得业务访问权限", 403)), 403
            return jsonify(ok({"user": user, "placeholder": True}, message="欢迎进入工作区"))
        except AuthServiceError as error:
            return error_response(error, "UNAUTHENTICATED", 401)

    return blueprint
