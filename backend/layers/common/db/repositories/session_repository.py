from __future__ import annotations

from datetime import datetime
from typing import Any


class SessionRepository:
    def create(
        self,
        connection: Any,
        *,
        user_id: int,
        session_token_hash: str,
        ip_address: str,
        user_agent: str,
        last_active_at: datetime,
        expires_at: datetime,
    ) -> int:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sessions
                    (user_id, session_token_hash, status, ip_address, user_agent, last_active_at, expires_at)
                VALUES (%s, %s, 'active', %s, %s, %s, %s)
                """,
                (user_id, session_token_hash, ip_address, user_agent, last_active_at, expires_at),
            )
            return int(cursor.lastrowid)

    def revoke_oldest_excess(self, connection: Any, *, user_id: int, max_sessions: int) -> None:
        limit = max(1, int(max_sessions))
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM sessions
                WHERE user_id = %s AND status = 'active'
                ORDER BY created_at ASC, id ASC
                FOR UPDATE
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
            active_ids = [int(row["id"] if isinstance(row, dict) else row[0]) for row in rows]
            excess = max(0, len(active_ids) - limit + 1)
            for session_id in active_ids[:excess]:
                cursor.execute(
                    """
                    UPDATE sessions
                    SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP, revoke_reason = 'session_replaced'
                    WHERE id = %s
                    """,
                    (session_id,),
                )

    def find_by_token(self, connection: Any, *, session_token_hash: str) -> dict[str, Any] | None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.*, u.phone, u.login_name, u.name, u.status AS user_status
                FROM sessions AS s
                INNER JOIN users AS u ON u.id = s.user_id
                WHERE s.session_token_hash = %s
                LIMIT 1
                """,
                (session_token_hash,),
            )
            return cursor.fetchone()

    def touch(self, connection: Any, *, session_id: int, last_active_at: datetime) -> None:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE sessions SET last_active_at = %s WHERE id = %s", (last_active_at, session_id))

    def revoke(self, connection: Any, *, session_id: int, reason: str) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE sessions SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP, revoke_reason = %s WHERE id = %s",
                (reason, session_id),
            )
