from __future__ import annotations

from typing import Any, Protocol

from backend.config.settings import Settings
from backend.layers.common.security.password import hash_password
from backend.layers.common.validation.auth_validation import (
    ValidationError,
    validate_application_note,
    validate_name,
    validate_password,
    validate_phone,
)


class RegistrationStore(Protocol):
    def consume_rate_limit(self, limit_type: str, subject_key: str, *, limit: int, window_seconds: int) -> bool: ...
    def register_pending(self, payload: dict[str, Any], *, password_hash: str) -> dict[str, Any]: ...
    def get_application(self, user_id: int) -> dict[str, Any] | None: ...
    def resubmit_application(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]: ...
    def list_registration_options(self) -> dict[str, Any]: ...


class RegistrationServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400, *, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retry_after = retry_after


SCOPE_TYPES = ("farm", "area", "personal")
SCOPE_TYPE_LABELS = {"farm": "全场数据", "area": "区域数据", "personal": "仅本人数据"}


class RegistrationService:
    def __init__(self, store: RegistrationStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    def register(self, payload: dict[str, Any], *, ip: str) -> dict[str, Any]:
        if not self.store.consume_rate_limit("register_ip", ip, limit=5, window_seconds=3600):
            raise RegistrationServiceError("RATE_LIMITED", "注册请求过于频繁，请稍后再试", 429, retry_after=3600)
        try:
            normalized = {
                **payload,
                "phone": validate_phone(payload.get("phone", "")),
                "name": validate_name(payload.get("name", "")),
                "application_note": validate_application_note(payload.get("application_note")),
            }
            validate_password(payload.get("password", ""), payload.get("confirm_password"))
            normalized["desired_role_id"] = int(payload.get("desired_role_id"))
            desired_scope_type = str(payload.get("desired_scope_type") or "area").strip().lower()
            if desired_scope_type not in SCOPE_TYPES:
                raise RegistrationServiceError("VALIDATION_ERROR", "数据范围只能是 farm、area 或 personal", 400)
            normalized["desired_scope_type"] = desired_scope_type
            try:
                normalized["area_id"] = int(payload.get("area_id"))
            except (TypeError, ValueError):
                normalized["area_id"] = 0
            if desired_scope_type != "area" and normalized["area_id"] <= 0:
                # 全场/个人范围不绑定区域：回退到第一个启用基地以满足申请表的归属字段
                areas = self.store.list_registration_options().get("areas") or []
                if not areas:
                    raise RegistrationServiceError("VALIDATION_ERROR", "暂无可用基地，请联系管理员", 400)
                normalized["area_id"] = int(areas[0]["id"])
        except (ValidationError, TypeError, ValueError) as exc:
            code = getattr(exc, "code", "VALIDATION_ERROR")
            raise RegistrationServiceError(code, str(exc), 400) from exc

        normalized["ip_address"] = ip
        try:
            result = self.store.register_pending(normalized, password_hash=hash_password(normalized["password"]))
        except ValueError as exc:
            raise RegistrationServiceError(
                getattr(exc, "code", "REGISTRATION_FAILED"),
                str(exc),
                getattr(exc, "status", 400),
            ) from exc
        return {
            "user": {"id": result["user"]["id"], "name": result["user"]["name"], "status": "pending"},
            "application": result["application"],
        }

    def get_application(self, user_id: int) -> dict[str, Any] | None:
        return self.store.get_application(user_id)

    def resubmit(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            normalized = {
                **payload,
                "name": validate_name(payload.get("name", "")),
                "application_note": validate_application_note(payload.get("application_note")),
                "desired_role_id": int(payload.get("desired_role_id")),
                "area_id": int(payload.get("area_id")),
                "desired_scope_type": str(payload.get("desired_scope_type") or "area").strip().lower(),
            }
            if normalized["desired_scope_type"] not in SCOPE_TYPES:
                raise RegistrationServiceError("VALIDATION_ERROR", "数据范围只能是 farm、area 或 personal", 400)
            return self.store.resubmit_application(user_id, normalized)
        except (ValidationError, TypeError, ValueError) as exc:
            raise RegistrationServiceError(
                getattr(exc, "code", "VALIDATION_ERROR"),
                str(exc),
                getattr(exc, "status", 400),
            ) from exc
