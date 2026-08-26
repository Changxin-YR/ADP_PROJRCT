from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date

from backend.layers.common.db.repositories.cost_store import MySqlCostStore


class FakeCosts:
    def create_rule_version(self, _connection, **_kwargs):
        return {
            "version_id": 12,
            "version_no": 3,
            "previous_version_id": 9,
            "previous_version_no": 2,
        }

    def get_rule_version(self, _connection, *, effective_at):
        return {
            "id": 12,
            "version_no": 3,
            "effective_from": effective_at,
            "effective_to": None,
            "status": "active",
            "change_reason": "调整口径",
        }

    def list_rule_items(self, _connection, *, version_id):
        if version_id == 9:
            return [{"category_id": 1, "driver": "equal", "manual_ratio_json": None}]
        assert version_id == 12
        return [{"category_id": 1, "driver": "area", "manual_ratio_json": None}]


class FakeAudit:
    def __init__(self) -> None:
        self.payload = None

    def write(self, _connection, **kwargs):
        self.payload = kwargs


def test_rule_version_audit_records_previous_new_and_rule_diff(monkeypatch) -> None:
    connection = object()

    @contextmanager
    def fake_connection(_settings):
        yield connection

    monkeypatch.setattr("backend.layers.common.db.repositories.cost_store.get_connection", fake_connection)
    store = MySqlCostStore(object())
    store.costs = FakeCosts()
    store.audit = FakeAudit()
    rules = [{"category_id": 1, "driver": "area", "manual_ratio_json": None}]

    result = store.create_rule_version(
        user_id=7,
        ip_address="127.0.0.1",
        effective_from=date(2026, 10, 1),
        change_reason="调整口径",
        rules=rules,
    )

    assert result["version_no"] == 3
    detail = json.loads(store.audit.payload["detail_json"])
    assert detail["previous_version"] == {"id": 9, "version_no": 2}
    assert detail["new_version"] == {"id": 12, "version_no": 3}
    assert detail["rules"] == rules
    assert detail["rule_changes"] == [{
        "category_id": 1,
        "from_driver": "equal",
        "to_driver": "area",
        "from_manual_ratio_json": None,
        "to_manual_ratio_json": None,
    }]
