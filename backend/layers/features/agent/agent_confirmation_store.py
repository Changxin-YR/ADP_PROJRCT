from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from backend.config.settings import Settings
from backend.layers.common.db.connection import get_connection
from backend.layers.features.agent.agent_contracts import AgentConfirmation, AgentConfirmationError, AgentConfirmationStore


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class MySqlAgentConfirmationStore(AgentConfirmationStore):
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings

    def _connection(self):
        return get_connection(self.settings) if self.settings is not None else get_connection()

    def create(self, confirmation: AgentConfirmation, token: str) -> AgentConfirmation:
        if confirmation.status != "pending":
            raise AgentConfirmationError("INVALID_STATUS", "新建确认必须是 pending 状态")
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO agent_confirmations (token_hash,user_id,session_hash,conversation_id,request_id,tool_name,payload_json,status,expires_at,used_at,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP))",
                    (_hash_token(token), confirmation.user_id, confirmation.session_hash, confirmation.conversation_id, confirmation.request_id, confirmation.tool_name, json.dumps(dict(confirmation.payload)), confirmation.status, confirmation.expires_at, confirmation.used_at, confirmation.created_at),
                )
                confirmation_id = int(cursor.lastrowid)
        return AgentConfirmation(**{**confirmation.__dict__, "id": confirmation_id, "token_hash": _hash_token(token)})

    @staticmethod
    def _from_row(row: dict[str, Any]) -> AgentConfirmation:
        return AgentConfirmation(
            id=int(row["id"]),
            idempotency_key=f"agent-confirmation:{row['id']}",
            token_hash=row["token_hash"],
            user_id=int(row["user_id"]),
            session_hash=row["session_hash"],
            conversation_id=row["conversation_id"],
            request_id=row["request_id"],
            tool_name=row["tool_name"],
            payload=json.loads(row["payload_json"] or "{}"),
            status=row["status"],
            expires_at=row["expires_at"],
            used_at=row.get("used_at"),
            created_at=row.get("created_at"),
        )

    def find(self, *, token: str, user_id: int, session_hash: str) -> AgentConfirmation | None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM agent_confirmations WHERE token_hash=%s AND user_id=%s AND session_hash=%s",
                    (_hash_token(token), user_id, session_hash),
                )
                row = cursor.fetchone()
        return self._from_row(row) if row else None

    def claim(self, *, token: str, user_id: int, session_hash: str, now: datetime | None = None) -> AgentConfirmation | None:
        at = now or datetime.now(timezone.utc).replace(tzinfo=None)
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM agent_confirmations WHERE token_hash=%s AND user_id=%s AND session_hash=%s FOR UPDATE", (_hash_token(token), user_id, session_hash))
                row = cursor.fetchone()
                if not row or row["status"] != "pending" or row["expires_at"] <= at:
                    return None
                cursor.execute("UPDATE agent_confirmations SET status='confirmed',used_at=%s WHERE id=%s AND status='pending'", (at, row["id"]))
                if cursor.rowcount != 1:
                    return None
                row.update(status="confirmed", used_at=at)
        return self._from_row(row)

    def mark_cancelled(self, confirmation_id: int, *, user_id: int) -> bool:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE agent_confirmations SET status='cancelled' WHERE id=%s AND user_id=%s AND status='pending'", (confirmation_id, user_id))
                return cursor.rowcount == 1

    def mark_failed(self, confirmation_id: int, *, user_id: int) -> bool:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE agent_confirmations SET status='failed' WHERE id=%s AND user_id=%s AND status='confirmed'", (confirmation_id, user_id))
                return cursor.rowcount == 1

    def mark_expired(self, *, now: datetime | None = None, user_id: int | None = None) -> list[int]:
        """把到期的 pending 置为 expired 并**返回被处理的确认 ID**，供调用方级联收口待办。

        只改状态而不返回 ID 的话，对应 work_items 会永远停在 claimed —— 这正是之前留下的尾巴。
        user_id 可选：惰性清理按当前用户收窄，后台任务可全量清扫；结果有上限，避免长事务。
        """
        with self._connection() as connection, connection.cursor() as cursor:
            conditions = "status='pending' AND expires_at<=COALESCE(%s,CURRENT_TIMESTAMP)"
            params: list[Any] = [now]
            if user_id is not None:
                conditions += " AND user_id=%s"
                params.append(int(user_id))
            cursor.execute(f"SELECT id FROM agent_confirmations WHERE {conditions} ORDER BY expires_at LIMIT 200", tuple(params))
            ids = [int(row["id"]) for row in cursor.fetchall()]
            if ids:
                placeholders = ",".join(["%s"] * len(ids))
                cursor.execute(f"UPDATE agent_confirmations SET status='expired' WHERE id IN ({placeholders}) AND status='pending'", tuple(ids))
            return ids
