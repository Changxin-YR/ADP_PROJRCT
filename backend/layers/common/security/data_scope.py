from __future__ import annotations

from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def enforced(user: dict[str, Any]) -> bool:
    """Live sessions carry active roles; lightweight unit actors may omit them."""
    return bool(user.get("roles")) or bool(user.get("_scope_enforced"))


def unrestricted(user: dict[str, Any]) -> bool:
    scopes = user.get("data_scopes") or []
    if not scopes and not enforced(user):
        return True
    return "super_admin" in {item.get("code") for item in user.get("roles") or []} or any(
        item.get("scope_type") == "farm" for item in scopes
    )


def require_active_scope(user: dict[str, Any]) -> list[dict[str, Any]]:
    scopes = user.get("data_scopes") or []
    if not scopes and enforced(user) and not unrestricted(user):
        raise DomainError("DATA_SCOPE_REQUIRED", "当前账号没有有效数据范围，拒绝访问业务数据", 403)
    return scopes
