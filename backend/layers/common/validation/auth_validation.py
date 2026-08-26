from __future__ import annotations

import re

from backend.layers.common.security.password import weak_password_reason


class ValidationError(ValueError):
    def __init__(self, message: str, *, field: str | None = None, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")


def validate_phone(phone: str) -> str:
    normalized = re.sub(r"[\s-]", "", str(phone or ""))
    if normalized.startswith("+86"):
        normalized = normalized[3:]
    if not PHONE_PATTERN.fullmatch(normalized):
        raise ValidationError("请输入有效的大陆手机号", field="phone")
    return normalized


def validate_name(name: str) -> str:
    normalized = str(name or "").strip()
    if not 2 <= len(normalized) <= 40:
        raise ValidationError("姓名长度必须为 2-40 个字符", field="name")
    return normalized


def validate_application_note(note: str | None) -> str:
    normalized = str(note or "").strip()
    if len(normalized) > 500:
        raise ValidationError("申请说明不能超过 500 个字符", field="application_note")
    return normalized


def validate_password(password: str, confirmation: str | None = None) -> str:
    if not isinstance(password, str) or (confirmation is not None and not isinstance(confirmation, str)):
        raise ValidationError("密码必须是字符串", field="password")
    if len(password) < 8:
        raise ValidationError("密码至少需要 8 个字符", field="password")
    if len(password) > 128:
        raise ValidationError("密码不能超过 128 个字符", field="password")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValidationError("密码必须同时包含字母和数字", field="password")
    if confirmation is not None and password != confirmation:
        raise ValidationError("两次输入的密码不一致", field="confirm_password")
    reason = weak_password_reason(password)
    if reason:
        raise ValidationError(f"密码过于简单：{reason}，请更换更复杂的密码", field="password", code="WEAK_PASSWORD")
    return password
