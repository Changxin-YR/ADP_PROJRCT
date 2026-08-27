from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from backend.layers.common.governance.lifecycle import DomainError


KEY_PATTERN = re.compile(r"[A-Za-z0-9._:-]{8,128}")


def request_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_key(value: str) -> str:
    if not KEY_PATTERN.fullmatch(value.strip()):
        raise DomainError("INVALID_IDEMPOTENCY_KEY", "幂等键格式无效", 400)
    return value.strip()


def key_hash(value: str) -> str:
    return hashlib.sha256(validate_key(value).encode("utf-8")).hexdigest()


def validate_replay(*, stored_request_hash: str, incoming_request_hash: str) -> None:
    if stored_request_hash != incoming_request_hash:
        raise DomainError("IDEMPOTENCY_CONFLICT", "相同幂等键不能用于不同请求", 409)


def execute_idempotent(
    settings: Any,
    *,
    user_id: int,
    action_code: str,
    key: str | None,
    payload: Any,
    operation: Callable[[], tuple[dict[str, Any], int]],
) -> tuple[dict[str, Any], int]:
    """Reserve a database key, execute once, and replay the stored response."""
    if not key:
        return operation()
    from backend.layers.common.db.connection import get_connection
    from pymysql.err import IntegrityError

    normalized = validate_key(key)
    action_code = action_code if len(action_code) <= 64 else f"{action_code[:15]}:{hashlib.sha256(action_code.encode()).hexdigest()[:48]}"
    digest = request_hash(payload)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now + timedelta(minutes=10)
    with get_connection(settings) as connection, connection.cursor() as cursor:
        try:
            cursor.execute(
                "SELECT request_hash,response_json,response_status,status,expires_at FROM idempotency_keys WHERE user_id=%s AND action_code=%s AND key_hash=%s FOR UPDATE",
                (user_id, action_code, key_hash(normalized)),
            )
            row = cursor.fetchone()
            if row:
                validate_replay(stored_request_hash=row["request_hash"], incoming_request_hash=digest)
                if row["status"] == "completed":
                    return json.loads(row["response_json"]), int(row["response_status"] or 200)
                if row["status"] == "processing" and row["expires_at"] > now:
                    raise DomainError("IDEMPOTENCY_IN_PROGRESS", "相同请求正在处理中，请稍后重试", 409)
                cursor.execute(
                    "UPDATE idempotency_keys SET status='processing',response_json=NULL,response_status=NULL,expires_at=%s WHERE user_id=%s AND action_code=%s AND key_hash=%s",
                    (expires_at, user_id, action_code, key_hash(normalized)),
                )
            else:
                cursor.execute(
                    "INSERT INTO idempotency_keys (user_id,action_code,key_hash,request_hash,status,expires_at) VALUES (%s,%s,%s,%s,'processing',%s)",
                    (user_id, action_code, key_hash(normalized), digest, expires_at),
                )
        except IntegrityError:
            raise DomainError("IDEMPOTENCY_IN_PROGRESS", "相同请求正在处理中，请稍后重试", 409)
    try:
        body, status = operation()
    except Exception:
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE idempotency_keys SET status='failed',expires_at=%s WHERE user_id=%s AND action_code=%s AND key_hash=%s",
                (now, user_id, action_code, key_hash(normalized)),
            )
        raise
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            "UPDATE idempotency_keys SET status='completed',response_json=%s,response_status=%s,expires_at=%s WHERE user_id=%s AND action_code=%s AND key_hash=%s",
            (json.dumps(body, ensure_ascii=False, default=str), status, expires_at, user_id, action_code, key_hash(normalized)),
        )
    return body, status
