from __future__ import annotations

import pytest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from backend.layers.common.governance.idempotency import execute_idempotent, key_hash, request_hash
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.warehouse.warehouse_service import WarehouseService


def _actor(*permissions: str) -> dict[str, object]:
    return {"id": 9, "permissions": list(permissions), "data_scopes": []}


def test_alert_replenish_cannot_close_without_a_purchase_order_reference() -> None:
    class Store:
        @staticmethod
        def handle_alert(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {}

    service = WarehouseService(Store())

    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_REFERENCE_REQUIRED"):
        service.handle_alert(_actor("warehouse.manage"), "3:8:low_stock", {
            "action_code": "replenish",
            "resolution_note": "需要补货",
        })


def test_alert_threshold_requires_a_real_new_safety_stock_value() -> None:
    class Store:
        @staticmethod
        def handle_alert(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {}

    service = WarehouseService(Store())

    with pytest.raises(DomainError, match="WAREHOUSE_ALERT_THRESHOLD_REQUIRED"):
        service.handle_alert(_actor("warehouse.manage"), "3:8:low_stock", {
            "action_code": "threshold",
            "resolution_note": "调整安全库存",
        })


def test_database_idempotency_replays_completed_response_and_rejects_payload_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[tuple[int, str, str], dict[str, object]] = {}

    class Cursor:
        def __init__(self) -> None:
            self.row: dict[str, object] | None = None

        def __enter__(self) -> "Cursor": return self
        def __exit__(self, *_args: object) -> None: return None

        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            if sql.startswith("SELECT request_hash"):
                self.row = state.get((int(params[0]), str(params[1]), str(params[2])))
            elif sql.startswith("INSERT INTO idempotency_keys"):
                state[(int(params[0]), str(params[1]), str(params[2]))] = {
                    "request_hash": params[3], "response_json": None, "response_status": None,
                    "status": "processing", "expires_at": params[4],
                }
            elif sql.startswith("UPDATE idempotency_keys SET status='completed'"):
                row = state[(int(params[3]), str(params[4]), str(params[5]))]
                row.update(status="completed", response_json=params[0], response_status=params[1], expires_at=params[2])
            elif sql.startswith("UPDATE idempotency_keys SET status='failed'"):
                row = state[(int(params[1]), str(params[2]), str(params[3]))]
                row["status"] = "failed"

        def fetchone(self) -> dict[str, object] | None: return self.row

    class Connection:
        def cursor(self) -> Cursor: return Cursor()

    @contextmanager
    def fake_connection(_settings: object):
        yield Connection()

    monkeypatch.setattr("backend.layers.common.db.connection.get_connection", fake_connection)
    calls = 0

    def operation() -> tuple[dict[str, object], int]:
        nonlocal calls
        calls += 1
        return {"code": "OK", "data": {"id": 1}}, 201

    first = execute_idempotent(object(), user_id=9, action_code="POST /purchase/orders", key="idem-1234", payload={"code": "PO-1"}, operation=operation)
    replay = execute_idempotent(object(), user_id=9, action_code="POST /purchase/orders", key="idem-1234", payload={"code": "PO-1"}, operation=operation)
    assert first == replay and calls == 1
    with pytest.raises(DomainError, match="IDEMPOTENCY_CONFLICT"):
        execute_idempotent(object(), user_id=9, action_code="POST /purchase/orders", key="idem-1234", payload={"code": "PO-2"}, operation=operation)


def test_database_idempotency_rejects_an_unexpired_processing_request(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {(9, "POST /purchase/orders", key_hash("8-char-key")): {
        "request_hash": request_hash({}), "response_json": None, "response_status": None,
        "status": "processing", "expires_at": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5),
    }}

    class Cursor:
        def __enter__(self) -> "Cursor": return self
        def __exit__(self, *_args: object) -> None: return None
        def execute(self, _sql: str, params: tuple[object, ...]) -> None:
            self.row = state.get((int(params[0]), str(params[1]), str(params[2])))
        def fetchone(self) -> dict[str, object] | None: return self.row

    class Connection:
        def cursor(self) -> Cursor: return Cursor()

    @contextmanager
    def fake_connection(_settings: object):
        yield Connection()

    monkeypatch.setattr("backend.layers.common.db.connection.get_connection", fake_connection)
    with pytest.raises(DomainError, match="IDEMPOTENCY_IN_PROGRESS"):
        execute_idempotent(object(), user_id=9, action_code="POST /purchase/orders", key="8-char-key", payload={}, operation=lambda: ({}, 200))
