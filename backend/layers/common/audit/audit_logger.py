from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from flask import g, has_request_context


SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "session_token",
    "csrf",
    "csrf_token",
    "secret",
    "private_key",
    "temporary_password",
}
SENSITIVE_KEY_FRAGMENTS = ("password", "token", "secret", "private_key", "api_key", "credential", "csrf")


def _request_id() -> str | None:
    if has_request_context():
        value = getattr(g, "request_id", None)
        return str(value) if value else None
    return None


def _redact(value: Any, *, key: str | None = None) -> Any:
    normalized = key.lower() if key else ""
    if normalized and (normalized in SENSITIVE_KEYS or any(fragment in normalized for fragment in SENSITIVE_KEY_FRAGMENTS)):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(item_key): _redact(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redact(item) for item in value]
    return value


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(_redact(value), ensure_ascii=False, default=str)


def _changed_fields(before: Any, after: Any) -> dict[str, dict[str, Any]] | None:
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return None
    fields: dict[str, dict[str, Any]] = {}
    for key in sorted(set(before) | set(after)):
        previous = before.get(key)
        current = after.get(key)
        if previous != current:
            fields[str(key)] = {"before": _redact(previous, key=str(key)), "after": _redact(current, key=str(key))}
    return fields or None


class AuditLogger:
    def write(
        self,
        connection: Any,
        *,
        user_id: int | None,
        action: str,
        object_type: str,
        object_id: int | None,
        result: str,
        ip_address: str | None,
        detail_json: str | None = None,
        request_id: str | None = None,
        module_code: str | None = None,
        action_code: str | None = None,
        object_ref: str | None = None,
        actor_name_snapshot: str | None = None,
        actor_role_snapshot: str | None = None,
        reason: str | None = None,
        before: Any = None,
        after: Any = None,
        changed_fields: Any = None,
        related_work_item_id: int | None = None,
        correlation_id: str | None = None,
        retention_class: str = "business",
    ) -> None:
        if user_id is not None and (actor_name_snapshot is None or actor_role_snapshot is None):
            try:
                with connection.cursor() as context_cursor:
                    context_cursor.execute(
                        "SELECT u.name, COALESCE(GROUP_CONCAT(DISTINCT r.code ORDER BY r.code SEPARATOR ','),'') AS role_codes "
                        "FROM users u LEFT JOIN user_roles ur ON ur.user_id=u.id LEFT JOIN roles r ON r.id=ur.role_id "
                        "WHERE u.id=%s GROUP BY u.id,u.name",
                        (user_id,),
                    )
                    actor = context_cursor.fetchone()
                if actor:
                    actor_name_snapshot = actor_name_snapshot or actor.get("name")
                    actor_role_snapshot = actor_role_snapshot or actor.get("role_codes")
            except (AttributeError, TypeError):
                # Lightweight unit-test cursors may only capture the INSERT statement.
                pass
        if detail_json is not None:
            try:
                detail_value: Any = json.loads(detail_json)
            except (TypeError, ValueError):
                detail_value = detail_json
            detail_json = _json(detail_value)
        changed_fields = changed_fields if changed_fields is not None else _changed_fields(before, after)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_logs
                    (user_id, action, object_type, object_id, result, detail_json, ip_address,
                     request_id, module_code, action_code, object_ref, actor_name_snapshot,
                     actor_role_snapshot, reason, before_json, after_json, changed_fields_json,
                     related_work_item_id, correlation_id, retention_class)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    action,
                    object_type,
                    object_id,
                    result,
                    detail_json,
                    ip_address,
                    request_id or _request_id() or uuid4().hex,
                    module_code,
                    action_code or action,
                    object_ref,
                    actor_name_snapshot,
                    actor_role_snapshot,
                    reason,
                    _json(before),
                    _json(after),
                    _json(changed_fields),
                    related_work_item_id,
                    correlation_id,
                    retention_class,
                ),
            )
