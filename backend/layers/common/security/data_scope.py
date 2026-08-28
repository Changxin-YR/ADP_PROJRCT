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
    roles = {item.get("code") for item in user.get("roles") or []}
    if "super_admin" in roles:
        return True
    # Farm scopes have no tenant key in the current schema; live non-admin users must fail closed.
    return not enforced(user) and any(item.get("scope_type") == "farm" for item in scopes)


def require_active_scope(user: dict[str, Any]) -> list[dict[str, Any]]:
    scopes = user.get("data_scopes") or []
    if not scopes and enforced(user) and not unrestricted(user):
        raise DomainError("DATA_SCOPE_REQUIRED", "当前账号没有有效数据范围，拒绝访问业务数据", 403)
    return scopes


def scope_predicate(user: dict[str, Any], alias: str = "") -> tuple[str, list[int]]:
    """Build a tenant-safe SQL predicate for area and bound farm scopes."""
    scopes = require_active_scope(user)
    if unrestricted(user):
        return "", []
    prefix = f"{alias}." if alias else ""
    terms: list[str] = []
    values: list[int] = []
    area_ids = sorted({int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")})
    farm_ids = sorted({int(item["farm_id"]) for item in scopes if item.get("scope_type") == "farm" and item.get("farm_id")})
    organization_ids = sorted({int(item["organization_id"]) for item in scopes if item.get("scope_type") == "farm" and item.get("organization_id") and not item.get("farm_id")})
    if area_ids:
        terms.append(f"{prefix}area_id IN ({','.join(['%s'] * len(area_ids))})")
        values.extend(area_ids)
    if farm_ids:
        terms.append(f"{prefix}farm_id IN ({','.join(['%s'] * len(farm_ids))})")
        values.extend(farm_ids)
    if organization_ids:
        terms.append(f"{prefix}organization_id IN ({','.join(['%s'] * len(organization_ids))})")
        values.extend(organization_ids)
    if terms:
        predicate = " OR ".join(terms)
        if any(item.get("scope_type") == "personal" for item in scopes):
            return f"({predicate}) AND {prefix}created_by=%s", [*values, int(user["id"])]
        return predicate, values
    if any(item.get("scope_type") == "personal" for item in scopes):
        return f"{prefix}created_by=%s", [int(user["id"])]
    return "1=0", []


def row_in_scope(user: dict[str, Any], row: dict[str, Any]) -> bool:
    scopes = require_active_scope(user)
    if unrestricted(user):
        return True
    area_ids = {int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")}
    farm_ids = {int(item["farm_id"]) for item in scopes if item.get("scope_type") == "farm" and item.get("farm_id")}
    organization_ids = {int(item["organization_id"]) for item in scopes if item.get("scope_type") == "farm" and item.get("organization_id") and not item.get("farm_id")}
    tenant_allowed = int(row.get("area_id") or 0) in area_ids or int(row.get("farm_id") or 0) in farm_ids or int(row.get("organization_id") or 0) in organization_ids
    personal = any(item.get("scope_type") == "personal" for item in scopes)
    if tenant_allowed:
        return not personal or int(row.get("created_by") or 0) == int(user["id"])
    return personal and not (area_ids or farm_ids or organization_ids) and int(row.get("created_by") or 0) == int(user["id"])
