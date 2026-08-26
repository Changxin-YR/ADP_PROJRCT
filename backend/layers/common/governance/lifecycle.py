from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


class DomainError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status


def parse_positive_integer(
    value: Any,
    *,
    code: str = "VALIDATION_ERROR",
    message: str = "必须提供正整数",
) -> int:
    """Parse an integer identifier/version without accepting booleans or fractions."""
    if isinstance(value, bool):
        raise DomainError(code, message, 400)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DomainError(code, message, 400) from exc
    if not number.is_finite() or number < 1 or number != number.to_integral_value():
        raise DomainError(code, message, 400)
    return int(number)


def parse_expected_version(payload: Any, field: str = "expected_version") -> int:
    if not isinstance(payload, dict):
        raise DomainError("EXPECTED_VERSION_REQUIRED", "必须提供 expected_version", 400)
    message = "必须提供塘口版本" if field == "expected_pond_version" else "必须提供 expected_version"
    return parse_positive_integer(payload.get(field), code="EXPECTED_VERSION_REQUIRED", message=message)


@dataclass(frozen=True)
class LifecyclePolicy:
    can_edit: bool
    can_delete: bool
    allowed_actions: tuple[str, ...]


POLICIES = {
    "draft": LifecyclePolicy(True, True, ("view", "edit", "delete", "submit")),
    "submitted": LifecyclePolicy(True, False, ("view", "edit", "verify")),
    "verified": LifecyclePolicy(False, False, ("view", "correct", "reverse")),
    "confirmed": LifecyclePolicy(False, False, ("view", "correct", "reverse")),
    "cancelled": LifecyclePolicy(False, False, ("view",)),
    "reversed": LifecyclePolicy(False, False, ("view",)),
    "archived": LifecyclePolicy(False, False, ("view",)),
    "approved": LifecyclePolicy(False, False, ("view",)),
    "partially_received": LifecyclePolicy(False, False, ("view",)),
    "fully_received": LifecyclePolicy(False, False, ("view",)),
    "closed": LifecyclePolicy(False, False, ("view",)),
    "disputed": LifecyclePolicy(False, False, ("view",)),
}


def policy(status: str) -> LifecyclePolicy:
    try:
        return POLICIES[status]
    except KeyError as exc:
        raise DomainError("INVALID_STATUS", "不支持的业务状态") from exc


def verify_version(*, expected_version: int, current_version: int) -> None:
    if expected_version != current_version:
        raise DomainError("VERSION_CONFLICT", "数据已被修改，请刷新后重新核验", 409)


def require_editable(status: str) -> None:
    if not policy(status).can_edit:
        raise DomainError("RECORD_READ_ONLY", "核验完成的数据只允许查看或更正", 409)


def require_deletable(status: str, *, has_references: bool = False) -> None:
    if not policy(status).can_delete or has_references:
        raise DomainError("DELETE_NOT_ALLOWED", "仅无业务引用的未提交草稿可以删除", 409)
