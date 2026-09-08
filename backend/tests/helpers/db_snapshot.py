from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from backend.layers.common.db.connection import get_connection


_TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Scenario:
    """One manual/Agent comparison without prescribing either execution path."""

    name: str
    setup: Callable[[Any], Any]
    manual_operation: Callable[[Any], Any]
    agent_operation: Callable[[Any], Any]
    snapshot_tables: tuple[str, ...]
    ignored_fields: dict[str, set[str]] = field(default_factory=dict)
    business_keys: dict[str, tuple[str, ...]] = field(default_factory=dict)


def snapshot_tables(settings: Any, tables: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    with get_connection(settings) as connection, connection.cursor() as cursor:
        for table in tables:
            if not _TABLE.fullmatch(table):
                raise ValueError("invalid snapshot table")
            cursor.execute(f"SELECT * FROM `{table}` ORDER BY id")
            result[table] = [dict(row) for row in cursor.fetchall()]
    return result


def normalize_snapshot(
    snapshot: dict[str, list[dict[str, Any]]],
    *,
    ignore_fields: dict[str, set[str]] | None = None,
    business_keys: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    ignored = ignore_fields or {}
    keys = business_keys or {}
    result: dict[str, list[dict[str, Any]]] = {}
    for table, rows in snapshot.items():
        normalized = [{key: value for key, value in row.items() if key not in ignored.get(table, set())} for row in rows]
        if keys.get(table):
            normalized.sort(key=lambda row: tuple(str(row.get(key, "")) for key in keys[table]))
        result[table] = normalized
    return result


def compare_snapshots(
    left: dict[str, list[dict[str, Any]]],
    right: dict[str, list[dict[str, Any]]],
    *,
    ignore_fields: dict[str, set[str]] | None = None,
    business_keys: dict[str, tuple[str, ...]] | None = None,
) -> bool:
    return normalize_snapshot(left, ignore_fields=ignore_fields, business_keys=business_keys) == normalize_snapshot(right, ignore_fields=ignore_fields, business_keys=business_keys)


def restore_fixture(settings: Any, snapshot: dict[str, list[dict[str, Any]]]) -> None:
    """Restore a captured disposable-DB fixture using explicit table names."""
    tables = tuple(snapshot)
    if any(not _TABLE.fullmatch(table) for table in tables):
        raise ValueError("invalid fixture table")
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        try:
            for table in reversed(tables):
                cursor.execute(f"TRUNCATE TABLE `{table}`")
            for table, rows in snapshot.items():
                if not rows:
                    continue
                columns = tuple(rows[0])
                if any(not _TABLE.fullmatch(column) for column in columns):
                    raise ValueError("invalid fixture column")
                names = ",".join(f"`{column}`" for column in columns)
                placeholders = ",".join(["%s"] * len(columns))
                cursor.executemany(
                    f"INSERT INTO `{table}` ({names}) VALUES ({placeholders})",
                    [tuple(row.get(column) for column in columns) for row in rows],
                )
        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")
