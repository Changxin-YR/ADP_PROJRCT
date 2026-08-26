from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.layers.common.db.repositories.cost_repository import CostRepository


class Cursor:
    def __init__(self, responses: list[list[dict]]) -> None:
        self.responses = responses
        self.executed: list[tuple[str, object]] = []
        self.lastrowid = 7
        self.response_index = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), params))

    def executemany(self, sql, params):
        self.executed.append((" ".join(sql.split()), list(params)))

    def _next_response(self) -> list[dict]:
        if not self.responses:
            return []
        index = min(self.response_index, len(self.responses) - 1)
        self.response_index += 1
        return self.responses[index]

    def fetchall(self):
        return self._next_response()

    def fetchone(self):
        rows = self._next_response()
        return rows[0] if rows else None


class Connection:
    def __init__(self, responses: list[list[dict]]) -> None:
        self.cursor_instance = Cursor(responses)

    def cursor(self):
        return self.cursor_instance


def test_migration_contains_versioned_cost_contract() -> None:
    registry = Path("database/migrations/000_schema_migrations.sql").read_text(encoding="utf-8")
    sql = Path("database/migrations/003_cost_accounting_foundation.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in registry
    for table in ("cost_categories", "cost_entries", "cost_allocation_rule_versions", "cost_allocation_rules"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "LEGACY-INIT-2026" in sql
    assert "cost.allocation.manage" in sql


def test_repository_returns_category_totals_in_sort_order() -> None:
    connection = Connection([[{"code": "feed", "name": "饲料", "nature": "direct", "allocation_driver": "direct_consumption", "amount": Decimal("128000.00"), "source_quality": "legacy_import"}]])

    rows = CostRepository().list_category_totals(connection, period_start=date(2026, 1, 1), period_end=date(2026, 8, 16))

    assert rows[0]["code"] == "feed"
    sql, params = connection.cursor_instance.executed[0]
    assert "ce.status = 'confirmed'" in sql
    assert "ce.cost_nature = 'direct'" in sql
    assert params == (date(2026, 1, 1), date(2026, 8, 16))


def test_repository_pages_confirmed_entries_and_decodes_source_detail() -> None:
    connection = Connection([
        [{"total": 1}],
        [{
            "id": 3,
            "category_code": "feed",
            "category_name": "饲料",
            "amount": Decimal("128000.00"),
            "occurred_on": date(2026, 8, 15),
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 8, 15),
            "status": "confirmed",
            "source_type": "legacy_import",
            "source_ref": "LEGACY-INIT-2026",
            "source_detail_json": '{"note":"初始化口径"}',
        }],
    ])

    result = CostRepository().list_entries(
        connection,
        category_code="feed",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 8, 16),
        page=1,
        page_size=20,
    )

    assert result["total"] == 1
    assert result["has_next"] is False
    assert result["items"][0]["source_detail_json"] == {"note": "初始化口径"}
    assert all("ce.status = 'confirmed'" in sql for sql, _ in connection.cursor_instance.executed)


def test_repository_applies_area_scope_to_totals_and_entries() -> None:
    user = {"id": 8, "data_scopes": [{"scope_type": "area", "area_id": 17}]}
    totals = Connection([[]])
    CostRepository().list_category_totals(
        totals, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31), user=user,
    )
    totals_sql, totals_params = totals.cursor_instance.executed[0]
    assert "ce.area_id IN (%s)" in totals_sql
    assert totals_params == (date(2026, 8, 1), date(2026, 8, 31), 17)

    entries = Connection([[{"total": 0}], []])
    CostRepository().list_entries(
        entries, category_code="feed", period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
        page=1, page_size=20, user=user,
    )
    assert all("ce.area_id IN (%s)" in sql for sql, _ in entries.cursor_instance.executed)
    assert entries.cursor_instance.executed[0][1][-1] == 17


def test_repository_loads_rule_version_and_items() -> None:
    version_connection = Connection([[{"id": 4, "version_no": 2, "effective_from": date(2026, 9, 1), "effective_to": None, "status": "active", "change_reason": "月度调整"}]])
    rules_connection = Connection([[{"category_id": 7, "category_code": "feed", "category_name": "饲料", "driver": "direct_consumption", "fallback_driver": "equal", "manual_ratio_json": '{"pond-1":"1"}'}]])

    version = CostRepository().get_rule_version(version_connection, effective_at=date(2026, 9, 1))
    rules = CostRepository().list_rule_items(rules_connection, version_id=4)

    assert version and version["version_no"] == 2
    assert rules[0]["manual_ratio_json"] == {"pond-1": "1"}


def test_repository_loads_latest_rule_version_independently_of_effective_date() -> None:
    connection = Connection([[{"id": 5, "version_no": 3, "effective_from": date(2026, 10, 1), "status": "active"}]])

    version = CostRepository().get_latest_rule_version(connection)

    assert version and version["version_no"] == 3
    sql, params = connection.cursor_instance.executed[0]
    assert "ORDER BY v.version_no DESC" in sql
    assert params == ()


def test_repository_inserts_a_complete_rule_version() -> None:
    connection = Connection([
        [{"id": item} for item in range(1, 10)],
        [{"id": 1, "version_no": 1, "effective_from": date(2026, 1, 1), "status": "active"}],
    ])

    created = CostRepository().create_rule_version(
        connection,
        effective_from=date(2026, 9, 1),
        change_reason="按月更新分摊口径",
        created_by=1,
        rules=[{"category_id": item, "driver": "equal", "manual_ratio_json": None} for item in range(1, 10)],
    )

    assert created == {"version_id": 7, "version_no": 2, "previous_version_id": 1, "previous_version_no": 1}
    assert any(params and params[0] == 2 for sql, params in connection.cursor_instance.executed if "INSERT INTO cost_allocation_rule_versions" in sql)
    assert any("INSERT INTO cost_allocation_rules" in sql for sql, _ in connection.cursor_instance.executed)


def test_repository_rejects_rules_that_do_not_match_active_categories() -> None:
    connection = Connection([[{"id": item} for item in range(1, 10)]])

    with pytest.raises(ValueError, match="RULE_CATEGORY_SET_MISMATCH"):
        CostRepository().create_rule_version(
            connection,
            effective_from=date(2026, 9, 1),
            change_reason="错误类别集合",
            created_by=1,
            rules=[{"category_id": item, "driver": "equal", "manual_ratio_json": None} for item in range(11, 20)],
        )

    assert not any("INSERT INTO cost_allocation_rule_versions" in sql for sql, _ in connection.cursor_instance.executed)
