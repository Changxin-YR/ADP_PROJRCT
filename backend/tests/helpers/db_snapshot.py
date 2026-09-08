from __future__ import annotations

import re
from typing import Any, Iterable

from backend.layers.common.db.connection import get_connection


_TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def snapshot_tables(settings: Any, tables: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    with get_connection(settings) as connection, connection.cursor() as cursor:
        for table in tables:
            if not _TABLE.fullmatch(table):
                raise ValueError("invalid snapshot table")
            cursor.execute(f"SELECT * FROM `{table}` ORDER BY id")
            result[table] = [dict(row) for row in cursor.fetchall()]
    return result


def normalize_snapshot(snapshot: dict[str, list[dict[str, Any]]], *, ignore_fields: dict[str, set[str]] | None = None) -> dict[str, list[dict[str, Any]]]:
    ignored = ignore_fields or {}
    return {
        table: [{key: value for key, value in row.items() if key not in ignored.get(table, set())} for row in rows]
        for table, rows in snapshot.items()
    }


def compare_snapshots(left: dict[str, list[dict[str, Any]]], right: dict[str, list[dict[str, Any]]], *, ignore_fields: dict[str, set[str]] | None = None) -> bool:
    return normalize_snapshot(left, ignore_fields=ignore_fields) == normalize_snapshot(right, ignore_fields=ignore_fields)
