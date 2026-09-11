from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

import backend.layers.common.db.repositories.cost_expense_store as expense_store_module
import backend.layers.common.db.repositories.cost_store as legacy_store_module
from backend.app import create_app
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.cost_enterprise_repository import require_entry_open, require_source_not_duplicated
from backend.layers.common.db.repositories.cost_store import MySqlCostStore
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.cost.cost_enterprise_service import CostEnterpriseService
from backend.layers.features.cost.cost_service import CostService
from backend.tests.fake_auth_store import FakeAuthStore
from backend.tests.mysql_test_database import disposable_database, settings_for
from backend.tests.test_auth_api import _csrf, _settings


# ---------------------------------------------------------------------------
# 防重复归集判定口径（A1）：纯逻辑测试，不依赖 MySQL。
# ---------------------------------------------------------------------------
class StubCursor:
    """记录 SQL 并按语句特征返回预置行的最小游标。"""

    def __init__(self, duplicate: dict[str, Any] | None = None, target: dict[str, Any] | None = None) -> None:
        self.duplicate, self.target = duplicate, target
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self._current: dict[str, Any] | None = None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        normalized = " ".join(sql.split())
        self.statements.append((normalized, tuple(params)))
        self._current = self.target if "from ponds" in normalized.lower() else self.duplicate
        return 1

    def fetchone(self) -> dict[str, Any] | None:
        return self._current

    def matching(self, fragment: str) -> list[tuple[str, tuple[Any, ...]]]:
        return [item for item in self.statements if fragment.lower() in item[0].lower()]


def feed_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "organization_id": 1,
        "farm_id": 2,
        "area_id": 3,
        "category_code": "feed",
        "source_type": "manual_expense",
        "target_type": "pond",
        "target_id": 7,
        "period_start": date(2026, 8, 1),
        "period_end": date(2026, 8, 31),
    }
    row.update(overrides)
    return row


def test_duplicate_guard_rejects_cost_already_collected_by_stock_ledger() -> None:
    cursor = StubCursor(duplicate={"id": 42})

    with pytest.raises(DomainError) as error:
        require_source_not_duplicated(cursor, feed_row())

    assert error.value.code == "COST_SOURCE_DUPLICATED"
    assert error.value.status == 409
    assert "库存自动归集" in error.value.message
    sql, params = cursor.statements[-1]
    assert "source_type='warehouse_ledger'" in sql
    assert "status='confirmed'" in sql
    assert "ce.period_start<=%s AND ce.period_end>=%s" in sql
    assert params == ("pond", 7, 1, 2, date(2026, 8, 31), date(2026, 8, 1))


def test_duplicate_guard_allows_periods_without_overlap() -> None:
    cursor = StubCursor(duplicate=None)

    require_source_not_duplicated(cursor, feed_row())

    assert len(cursor.matching("from cost_entries")) == 1
    assert cursor.matching("from cost_entries")[0][1][-1] == date(2026, 8, 1)


@pytest.mark.parametrize("source_type", ["manual_feed_offset", "manual_feed_direct"])
def test_duplicate_guard_skips_explicit_stock_override_sources(source_type: str) -> None:
    cursor = StubCursor(duplicate={"id": 42})

    require_source_not_duplicated(cursor, feed_row(source_type=source_type))

    assert cursor.statements == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"category_code": "labor"},
        {"category_code": "other"},
        {"source_type": "purchase_invoice"},
        {"source_type": "asset_depreciation"},
        {"target_type": "area"},
        {"target_type": "farm"},
        {"target_id": None},
        {"period_start": None},
    ],
)
def test_duplicate_guard_ignores_other_categories_sources_and_targets(overrides: dict[str, Any]) -> None:
    cursor = StubCursor(duplicate={"id": 42})

    require_source_not_duplicated(cursor, feed_row(**overrides))

    assert cursor.statements == []


def test_duplicate_guard_resolves_scope_from_the_target_object() -> None:
    cursor = StubCursor(duplicate={"id": 42}, target={"organization_id": 11, "farm_id": 22, "area_id": 33})

    with pytest.raises(DomainError) as error:
        require_source_not_duplicated(cursor, feed_row(organization_id=None, farm_id=None))

    assert error.value.code == "COST_SOURCE_DUPLICATED"
    assert cursor.statements[-1][1] == ("pond", 7, 11, 22, date(2026, 8, 31), date(2026, 8, 1))


def test_duplicate_guard_keeps_null_scope_when_the_target_cannot_be_resolved() -> None:
    cursor = StubCursor(duplicate=None, target=None)

    require_source_not_duplicated(cursor, feed_row(organization_id=None, farm_id=None))

    assert len(cursor.matching("from ponds")) == 1
    assert cursor.matching("from cost_entries")[0][1][2:4] == (None, None)


def test_duplicate_guard_prefers_the_explicit_category_code() -> None:
    row = feed_row()
    row.pop("category_code")
    overridden = StubCursor(duplicate={"id": 42})

    require_source_not_duplicated(overridden, row, category_code="labor")

    assert overridden.statements == []
    forced = StubCursor(duplicate={"id": 42})

    with pytest.raises(DomainError) as error:
        require_source_not_duplicated(forced, feed_row(category_code="labor"), category_code="feed")

    assert error.value.code == "COST_SOURCE_DUPLICATED"
    assert len(forced.matching("from cost_entries")) == 1


# ---------------------------------------------------------------------------
# 旧成本入口（cost_store / CostService）补锁账（A2）：不依赖 MySQL 的写入路径测试。
# ---------------------------------------------------------------------------
class ScriptedCursor:
    """按 SQL 特征返回预置行的假游标，覆盖成本写入路径上的最小取数集合。"""

    def __init__(self, rows: dict[str, Any]) -> None:
        self.rows, self.statements = rows, []
        self.rowcount, self.lastrowid = 1, 900
        self._current: Any = None

    def __enter__(self) -> ScriptedCursor:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        normalized = " ".join(sql.split())
        self.statements.append((normalized, tuple(params)))
        upper, self.rowcount, self._current = normalized.upper(), 1, None
        if "SOURCE_TYPE='WAREHOUSE_LEDGER'" in upper:
            self._current = self.rows.get("duplicate")
        elif "FROM COST_SETTLEMENTS" in upper:
            self._current = self.rows.get("settlement")
        elif "FROM FARMS WHERE ID" in upper:
            self._current = self.rows.get("farm")
        elif "FROM PONDS" in upper:
            self._current = self.rows.get("pond")
        elif "FROM PRODUCTION_BATCHES" in upper:
            self._current = self.rows.get("batch")
        elif "FROM COST_CATEGORIES WHERE CODE" in upper:
            self._current = self.rows.get("category")
        elif "AS CATEGORY_CODE" in upper:
            self._current = dict(self.rows["entry"])
        return self.rowcount

    def executemany(self, sql: str, values: Any = ()) -> int:
        self.statements.append((" ".join(sql.split()), tuple(values)))
        self.rowcount = len(values)
        return self.rowcount

    def fetchone(self) -> Any:
        return self._current

    def fetchall(self) -> list[Any]:
        return []

    def matching(self, fragment: str) -> list[tuple[str, tuple[Any, ...]]]:
        return [item for item in self.statements if fragment.lower() in item[0].lower()]


class ScriptedConnection:
    def __init__(self, rows: dict[str, Any]) -> None:
        self.cursor_obj = ScriptedCursor(rows)

    def __enter__(self) -> ScriptedConnection:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def cursor(self) -> ScriptedCursor:
        return self.cursor_obj


def entry_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 900,
        "organization_id": 1,
        "farm_id": 2,
        "area_id": 3,
        "category_id": 7,
        "category_code": "feed",
        "category_name": "饲料",
        "amount": Decimal("500.00"),
        "occurred_on": date(2026, 8, 10),
        "period_start": date(2026, 8, 1),
        "period_end": date(2026, 8, 31),
        "status": "draft",
        "row_version": 1,
        "cost_nature": "direct",
        "source_type": "manual_expense",
        "source_ref": "EXP-FEED-LEGACY",
        "source_detail_json": None,
        "target_type": "pond",
        "target_id": 7,
        "evidence_attachment_ids_json": None,
        "created_by": 1,
        "updated_by": None,
        "reversal_of_id": None,
    }
    row.update(overrides)
    return row


def scripted_rows(**overrides: Any) -> dict[str, Any]:
    rows: dict[str, Any] = {
        "farm": {"organization_id": 1},
        "pond": {"organization_id": 1, "farm_id": 2, "area_id": 3},
        "batch": {"organization_id": 1, "farm_id": 2, "area_id": 3},
        "category": {"id": 7, "default_nature": "direct"},
        "entry": entry_row(),
        "settlement": None,
        "duplicate": None,
    }
    rows.update(overrides)
    return rows


def legacy_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "category_code": "feed",
        "amount": Decimal("500.00"),
        "occurred_on": date(2026, 8, 10),
        "period_start": date(2026, 8, 1),
        "period_end": date(2026, 8, 31),
        "cost_nature": "direct",
        "source_type": "manual_expense",
        "source_ref": "EXP-FEED-LEGACY",
        "source_detail": {"note": "财务手工登记饲料"},
        "target_type": "pond",
        "target_id": 7,
    }
    payload.update(overrides)
    return payload


def test_legacy_store_locks_entry_creation_inside_a_confirmed_settlement(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ScriptedConnection(scripted_rows(settlement={"id": 5}))
    monkeypatch.setattr(legacy_store_module, "get_connection", lambda *args, **kwargs: fake)

    with pytest.raises(DomainError) as error:
        MySqlCostStore(_settings()).create_entry(user_id=1, **legacy_payload())

    assert error.value.code == "COST_PERIOD_LOCKED"
    assert error.value.status == 409
    assert error.value.message == "该期间已确认结算，请先执行反结算"
    assert fake.cursor_obj.matching("from cost_settlements")
    assert not fake.cursor_obj.matching("insert into cost_entries")


def test_legacy_store_locks_draft_update_inside_a_confirmed_settlement(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ScriptedConnection(scripted_rows(settlement={"id": 5}))
    monkeypatch.setattr(legacy_store_module, "get_connection", lambda *args, **kwargs: fake)

    with pytest.raises(DomainError) as error:
        MySqlCostStore(_settings()).update_draft(900, user_id=1, **legacy_payload())

    assert error.value.code == "COST_PERIOD_LOCKED"
    assert not fake.cursor_obj.matching("update cost_entries")


def test_legacy_store_rejects_stock_duplicates_on_entry_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ScriptedConnection(scripted_rows(duplicate={"id": 42}))
    monkeypatch.setattr(legacy_store_module, "get_connection", lambda *args, **kwargs: fake)

    with pytest.raises(DomainError) as error:
        MySqlCostStore(_settings()).create_entry(user_id=1, **legacy_payload())

    assert error.value.code == "COST_SOURCE_DUPLICATED"
    assert not fake.cursor_obj.matching("insert into cost_entries")


def test_legacy_store_writes_when_the_period_is_open_and_stock_is_free(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ScriptedConnection(scripted_rows())
    monkeypatch.setattr(legacy_store_module, "get_connection", lambda *args, **kwargs: fake)

    created = MySqlCostStore(_settings()).create_entry(user_id=1, **legacy_payload())

    assert created["id"] == 900
    assert fake.cursor_obj.matching("from cost_settlements")
    assert fake.cursor_obj.matching("insert into cost_entries")


def test_entry_open_without_scope_or_target_only_checks_the_null_scope_lock() -> None:
    fake = ScriptedConnection(scripted_rows())

    resolved = require_entry_open(fake, {
        "category_code": "feed",
        "source_type": "manual_expense",
        "occurred_on": date(2026, 8, 10),
        "period_start": date(2026, 8, 1),
        "period_end": date(2026, 8, 31),
    })

    assert (resolved["organization_id"], resolved["farm_id"], resolved["area_id"]) == (None, None, None)
    assert fake.cursor_obj.matching("from cost_settlements")
    assert not fake.cursor_obj.matching("from cost_entries")


def test_cost_service_preserves_the_period_lock_error_code(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ScriptedConnection(scripted_rows(settlement={"id": 5}))
    monkeypatch.setattr(legacy_store_module, "get_connection", lambda *args, **kwargs: fake)
    service = CostService(MySqlCostStore(_settings()))

    with pytest.raises(DomainError) as error:
        service.create_entry({"id": 1, "permissions": ["cost.entry.manage"]}, legacy_payload())

    assert error.value.code == "COST_PERIOD_LOCKED"
    with pytest.raises(DomainError) as draft_error:
        service.update_draft({"id": 1, "permissions": ["cost.entry.manage"]}, 900, legacy_payload())

    assert draft_error.value.code == "COST_PERIOD_LOCKED"


# ---------------------------------------------------------------------------
# HTTP 端到端：/cost/expenses 与旧 /cost/entries 走真实 store，只把连接换成脚本游标。
# ---------------------------------------------------------------------------
def expense_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "organization_id": 1,
        "farm_id": 2,
        "category_code": "feed",
        "amount": "500.00",
        "occurred_on": "2026-08-10",
        "period_start": "2026-08-01",
        "period_end": "2026-08-31",
        "source_type": "manual_expense",
        "source_ref": "EXP-FEED-HTTP",
        "target_type": "pond",
        "target_id": 7,
    }
    body.update(overrides)
    return body


def http_client(monkeypatch: pytest.MonkeyPatch, rows: dict[str, Any]) -> tuple[ScriptedConnection, Any]:
    fake = ScriptedConnection(rows)
    monkeypatch.setattr(expense_store_module, "get_connection", lambda *args, **kwargs: fake)
    monkeypatch.setattr(legacy_store_module, "get_connection", lambda *args, **kwargs: fake)
    auth = FakeAuthStore()
    user = auth.add_user(phone="13800000777", login_name="cost-closure", password="Closure9!", status="active")
    user["permissions"] = ["cost.view", "cost.entry.manage", "cost.entry.verify", "cost.entry.confirm", "cost.entry.reverse"]
    settings = _settings()
    client = create_app(settings, store=auth, cost_store=MySqlCostStore(settings)).test_client()
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "cost-closure", "password": "Closure9!"},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert login.status_code == 200
    return fake, client


@pytest.mark.parametrize("path", ["/api/v1/cost/expenses", "/api/v1/cost/entries"])
def test_manual_feed_expense_is_rejected_when_stock_already_collected(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    fake, client = http_client(monkeypatch, scripted_rows(duplicate={"id": 42}))

    response = client.post(path, json=expense_body(), headers={"X-CSRF-Token": _csrf(client)})

    assert response.status_code == 409
    assert response.get_json()["code"] == "COST_SOURCE_DUPLICATED"
    assert "库存自动归集" in response.get_json()["message"]
    assert not fake.cursor_obj.matching("insert into cost_entries")


@pytest.mark.parametrize("path", ["/api/v1/cost/expenses", "/api/v1/cost/entries"])
def test_manual_feed_expense_is_allowed_without_stock_overlap(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    fake, client = http_client(monkeypatch, scripted_rows())

    response = client.post(path, json=expense_body(), headers={"X-CSRF-Token": _csrf(client)})

    assert response.status_code == 201
    assert fake.cursor_obj.matching("insert into cost_entries")


@pytest.mark.parametrize("source_type", ["manual_feed_offset", "manual_feed_direct"])
def test_explicit_manual_feed_sources_bypass_the_duplicate_guard(monkeypatch: pytest.MonkeyPatch, source_type: str) -> None:
    fake, client = http_client(monkeypatch, scripted_rows(duplicate={"id": 42}))

    response = client.post(
        "/api/v1/cost/expenses",
        json=expense_body(source_type=source_type, source_ref=f"EXP-{source_type.upper()}"),
        headers={"X-CSRF-Token": _csrf(client)},
    )

    assert response.status_code == 201
    assert not fake.cursor_obj.matching("warehouse_ledger")


@pytest.mark.parametrize("path", ["/api/v1/cost/expenses", "/api/v1/cost/entries"])
def test_confirmed_settlement_locks_manual_expense_creation(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    fake, client = http_client(monkeypatch, scripted_rows(settlement={"id": 5}))

    response = client.post(path, json=expense_body(), headers={"X-CSRF-Token": _csrf(client)})

    assert response.status_code == 409
    assert response.get_json()["code"] == "COST_PERIOD_LOCKED"
    assert response.get_json()["message"] == "该期间已确认结算，请先执行反结算"
    assert not fake.cursor_obj.matching("insert into cost_entries")


@pytest.mark.parametrize("path", ["/api/v1/cost/expenses/900", "/api/v1/cost/entries/900"])
def test_confirmed_settlement_locks_manual_expense_update(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    fake, client = http_client(monkeypatch, scripted_rows(settlement={"id": 5}))

    response = client.patch(path, json={**expense_body(), "expected_version": 1}, headers={"X-CSRF-Token": _csrf(client)})

    assert response.status_code == 409
    assert response.get_json()["code"] == "COST_PERIOD_LOCKED"
    assert not fake.cursor_obj.matching("update cost_entries")


@pytest.mark.parametrize("path", ["/api/v1/cost/expenses/900", "/api/v1/cost/entries/900"])
def test_open_period_allows_manual_expense_update(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    fake, client = http_client(monkeypatch, scripted_rows())

    response = client.patch(path, json={**expense_body(), "expected_version": 1}, headers={"X-CSRF-Token": _csrf(client)})

    assert response.status_code == 200
    assert fake.cursor_obj.matching("update cost_entries")


# ---------------------------------------------------------------------------
# MySQL 集成：本机没有可用凭据时自动 skip（disposable_database 内部判断）。
# ---------------------------------------------------------------------------
def seed_closure_database(settings: Any) -> dict[str, int]:
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO users (phone,name,password_hash,status) VALUES (%s,%s,'hash','active')",
            [("13950000001", "闭环经办"), ("13950000002", "闭环核验")],
        )
        cursor.execute("SELECT id AS organization_id FROM organizations WHERE code='default'")
        ids = dict(cursor.fetchone())
        cursor.execute("SELECT id AS farm_id FROM farms WHERE code='default-farm'")
        ids.update(cursor.fetchone())
        cursor.execute(
            "INSERT INTO areas (organization_id,farm_id,code,name,status,created_by) VALUES (%s,%s,'CLOSURE','闭环区','verified',1)",
            (ids["organization_id"], ids["farm_id"]),
        )
        ids["area_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO ponds (organization_id,farm_id,area_id,code,name,status,created_by) VALUES (%s,%s,%s,'CLOSURE-P1','闭环塘一号','verified',1)",
            (ids["organization_id"], ids["farm_id"], ids["area_id"]),
        )
        ids["pond_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,target_type,target_id,created_by,confirmed_by,confirmed_at)"
            " SELECT %s,%s,%s,id,300.00,'2026-08-10','2026-08-10','2026-08-10','confirmed','direct','warehouse_ledger','WD-CLOSURE-1','pond',%s,1,1,NOW() FROM cost_categories WHERE code='feed'",
            (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["pond_id"]),
        )
        ids["warehouse_entry_id"] = int(cursor.lastrowid)
    return ids


def confirm_august_settlement(settings: Any, ids: dict[str, int]) -> int:
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id AS rule_version_id FROM cost_allocation_rule_versions WHERE status='active' ORDER BY version_no DESC LIMIT 1")
        rule_version_id = int(cursor.fetchone()["rule_version_id"])
        cursor.execute(
            "INSERT INTO cost_allocation_runs (organization_id,farm_id,area_id,period_start,period_end,rule_version_id,result_version,source_total,allocated_total,participant_snapshot_json,created_by)"
            " VALUES (%s,%s,%s,'2026-08-01','2026-08-31',%s,1,0,0,JSON_ARRAY(),1)",
            (ids["organization_id"], ids["farm_id"], ids["area_id"], rule_version_id),
        )
        run_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO cost_settlements (organization_id,farm_id,area_id,code,name,period_start,period_end,allocation_run_id,income_amount,cost_amount,profit_amount,status,created_by)"
            " VALUES (%s,%s,%s,'ST-CLOSURE-AUG','闭环八月结算','2026-08-01','2026-08-31',%s,0,0,0,'draft',1)",
            (ids["organization_id"], ids["farm_id"], ids["area_id"], run_id),
        )
        settlement_id = int(cursor.lastrowid)
        cursor.execute("UPDATE cost_settlements SET status='confirmed',confirmed_by=2,confirmed_at=NOW() WHERE id=%s", (settlement_id,))
        return settlement_id


def test_mysql_stock_dedup_and_legacy_period_lock() -> None:
    with disposable_database("adp_cost_closure", through=33) as database:
        settings = settings_for(database)
        ids = seed_closure_database(settings)
        service = CostEnterpriseService(MySqlCostStore(settings))
        maker = {"id": 1, "permissions": ["cost.entry.manage"], "data_scopes": [{"scope_type": "area", "area_id": ids["area_id"]}]}

        def expense(code: str, *, period: tuple[str, str], source_type: str = "manual_expense") -> dict[str, Any]:
            return {
                "organization_id": ids["organization_id"], "farm_id": ids["farm_id"], "area_id": ids["area_id"],
                "category_code": "feed", "amount": "300.00", "occurred_on": period[0],
                "period_start": period[0], "period_end": period[1],
                "source_type": source_type, "source_ref": code,
                "target_type": "pond", "target_id": ids["pond_id"],
            }

        with pytest.raises(DomainError, match="COST_SOURCE_DUPLICATED"):
            service.create_expense(maker, expense("EXP-CLOSURE-DUP", period=("2026-08-10", "2026-08-31")))

        September = ("2026-09-10", "2026-09-30")
        assert service.create_expense(maker, expense("EXP-CLOSURE-OK", period=September))["status"] == "draft"
        offset = service.create_expense(
            maker, expense("EXP-CLOSURE-OFFSET", period=("2026-08-10", "2026-08-31"), source_type="manual_feed_offset"),
        )
        assert offset["status"] == "draft"

        confirm_august_settlement(settings, ids)
        legacy = CostService(MySqlCostStore(settings))
        with pytest.raises(DomainError) as error:
            legacy.create_entry(
                {"id": 1, "permissions": ["cost.entry.manage"]},
                {
                    "category_code": "other", "amount": "20.00", "occurred_on": "2026-08-12",
                    "period_start": "2026-08-01", "period_end": "2026-08-31",
                    "source_type": "manual_expense", "source_ref": "EXP-LEGACY-LOCK",
                    "target_type": "pond", "target_id": ids["pond_id"],
                },
            )
        assert error.value.code == "COST_PERIOD_LOCKED"
