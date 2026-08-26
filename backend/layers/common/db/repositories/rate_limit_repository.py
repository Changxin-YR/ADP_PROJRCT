from __future__ import annotations

from datetime import datetime
from typing import Any


class RateLimitRepository:
    def consume(
        self,
        connection: Any,
        *,
        limit_type: str,
        subject_key: str,
        window_started_at: datetime,
        limit: int,
    ) -> bool:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, request_count
                FROM rate_limits
                WHERE limit_type = %s AND subject_key = %s AND window_started_at = %s
                FOR UPDATE
                """,
                (limit_type, subject_key, window_started_at),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """
                    INSERT INTO rate_limits (limit_type, subject_key, window_started_at, request_count)
                    VALUES (%s, %s, %s, 1)
                    """,
                    (limit_type, subject_key, window_started_at),
                )
                return True
            next_count = int(row["request_count"]) + 1
            cursor.execute("UPDATE rate_limits SET request_count = %s WHERE id = %s", (next_count, row["id"]))
            return next_count <= limit

