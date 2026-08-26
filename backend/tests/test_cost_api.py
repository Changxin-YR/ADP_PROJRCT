from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from backend.app import create_app
from backend.tests.test_auth_api import FakeAuthStore, _csrf, _settings


CATEGORY_ROWS = [
    {"id": 1, "code": "pond_rent", "name": "塘租", "nature": "public", "allocation_driver": "area", "amount": Decimal("120000.00"), "source_quality": "legacy_import"},
    {"id": 2, "code": "equipment", "name": "设备", "nature": "public", "allocation_driver": "equipment_count", "amount": Decimal("38000.00"), "source_quality": "legacy_import"},
    {"id": 3, "code": "infrastructure", "name": "基础建设", "nature": "public", "allocation_driver": "area", "amount": Decimal("46000.00"), "source_quality": "legacy_import"},
    {"id": 4, "code": "labor", "name": "人工", "nature": "public", "allocation_driver": "work_scope", "amount": Decimal("144000.00"), "source_quality": "legacy_import"},
    {"id": 5, "code": "electricity", "name": "电费", "nature": "public", "allocation_driver": "runtime_hours", "amount": Decimal("42000.00"), "source_quality": "legacy_import"},
    {"id": 6, "code": "seed", "name": "苗种", "nature": "direct", "allocation_driver": "direct_input", "amount": Decimal("96000.00"), "source_quality": "legacy_import"},
    {"id": 7, "code": "feed", "name": "饲料", "nature": "direct", "allocation_driver": "direct_consumption", "amount": Decimal("128000.00"), "source_quality": "legacy_import"},
    {"id": 8, "code": "health", "name": "动保", "nature": "direct", "allocation_driver": "direct_consumption", "amount": Decimal("26000.00"), "source_quality": "legacy_import"},
    {"id": 9, "code": "other", "name": "其他费用", "nature": "public", "allocation_driver": "equal", "amount": Decimal("32000.00"), "source_quality": "legacy_import"},
]


class FakeCostStore:
    def __init__(self) -> None:
        self.category_totals = CATEGORY_ROWS
        self.entries = [{
            "id": 1,
            "category_code": "feed",
            "category_name": "饲料",
            "amount": Decimal("128000.00"),
            "occurred_on": date(2026, 8, 15),
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 8, 15),
            "status": "confirmed",
            "source_type": "legacy_import",
            "source_ref": "LEGACY-INIT-2026",
            "source_detail_json": {"note": "从既有成本构成页面迁移的初始化口径"},
        }]
        self.rule_version = self._version(1, date(2026, 1, 1), "初始化九类成本分摊规则")
        self.rule_versions = [self.rule_version]
        self.created: dict[str, Any] | None = None

    @staticmethod
    def _version(version_no: int, effective_from: date, reason: str) -> dict[str, Any]:
        return {
            "id": version_no,
            "version_no": version_no,
            "effective_from": effective_from,
            "effective_to": None,
            "status": "active",
            "change_reason": reason,
            "created_by_name": "测试用户",
            "rules": [
                {
                    "category_id": row["id"],
                    "category_code": row["code"],
                    "category_name": row["name"],
                    "driver": row["allocation_driver"],
                    "fallback_driver": "equal",
                    "manual_ratio_json": None,
                }
                for row in CATEGORY_ROWS
            ],
        }

    def list_category_totals(self, **_kwargs):
        return self.category_totals

    def get_dashboard_facts(self, **_kwargs):
        return {
            "output_weight_jin": Decimal("0"),
            "income_amount": Decimal("0"),
            "source_fact_counts": {"warehouse": 0, "purchase": 0, "production": 0, "expense": 9, "asset": 0, "sales": 0},
        }

    def list_entries(self, **kwargs):
        items = [item for item in self.entries if item["category_code"] == kwargs["category_code"]]
        return {"items": items, "page": kwargs["page"], "page_size": kwargs["page_size"], "total": len(items), "has_next": False}

    def get_rule_version(self, **kwargs):
        effective_at = kwargs["effective_at"]
        candidates = [item for item in self.rule_versions if item["effective_from"] <= effective_at]
        return max(candidates, key=lambda item: item["version_no"]) if candidates else None

    def get_latest_rule_version(self):
        return max(self.rule_versions, key=lambda item: item["version_no"])

    def create_rule_version(self, **kwargs):
        if {int(item["category_id"]) for item in kwargs["rules"]} != {int(row["id"]) for row in CATEGORY_ROWS}:
            raise ValueError("RULE_CATEGORY_SET_MISMATCH")
        self.created = kwargs
        self.rule_version = self._version(2, kwargs["effective_from"], kwargs["change_reason"])
        self.rule_version["rules"] = [
            {
                **rule,
                "category_code": CATEGORY_ROWS[index]["code"],
                "category_name": CATEGORY_ROWS[index]["name"],
                "fallback_driver": "equal",
            }
            for index, rule in enumerate(kwargs["rules"])
        ]
        self.rule_versions.append(self.rule_version)
        return self.rule_version


def _login(client, identifier: str, password: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert response.status_code == 200


def _finance_client(*, permissions: list[str] | None = None):
    auth = FakeAuthStore()
    user = auth.add_user(phone="13800000102", login_name="finance", password="Finance9!", status="active")
    user["permissions"] = permissions or ["cost.view", "cost.allocation.manage"]
    costs = FakeCostStore()
    client = create_app(_settings(), store=auth, cost_store=costs).test_client()
    _login(client, "finance", "Finance9!")
    return auth, costs, client


def _first_next_month() -> date:
    return (date.today().replace(day=28) + timedelta(days=4)).replace(day=1)


def _valid_rule_payload() -> dict[str, Any]:
    return {
        "effective_from": _first_next_month().isoformat(),
        "change_reason": "按月更新分摊口径",
        "rules": [
            {"category_id": row["id"], "driver": row["allocation_driver"], "manual_ratio_json": None}
            for row in CATEGORY_ROWS
        ],
    }


def test_authorized_user_reads_server_calculated_structure() -> None:
    _, _, client = _finance_client()

    response = client.get("/api/v1/cost/structure?period_start=2026-01-01&period_end=2026-08-16")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["total_amount"] == "672000.00"
    assert data["direct_share"] == "37.2024"
    assert data["public_share"] == "62.7976"
    assert data["unit_production_cost"] is None
    assert data["unit_cost_status"] == "output_not_connected"
    assert data["confirmed_output_weight_jin"] == "0.000"
    assert data["confirmed_income_amount"] == "0.00"
    assert data["confirmed_profit_amount"] == "-672000.00"
    assert data["source_quality"] == "legacy_import"
    assert data["has_data"] is True
    assert data["categories"][0]["id"] == 1


def test_user_without_cost_permission_is_forbidden() -> None:
    _, _, client = _finance_client(permissions=["workbench.enter"])

    response = client.get("/api/v1/cost/structure?period_start=2026-01-01&period_end=2026-08-16")

    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"


def test_authorized_user_reads_traceable_entries_and_rules() -> None:
    _, _, client = _finance_client()

    entries = client.get("/api/v1/cost/entries?category_code=feed&period_start=2026-01-01&period_end=2026-08-16&page=1")
    rules = client.get("/api/v1/cost/allocation-rules?effective_at=2026-08-16")

    assert entries.status_code == 200
    assert entries.get_json()["data"]["items"][0]["source_ref"] == "LEGACY-INIT-2026"
    assert entries.get_json()["data"]["items"][0]["amount"] == "128000.00"
    assert rules.status_code == 200
    assert len(rules.get_json()["data"]["rules"]) == 9


def test_latest_rule_mode_distinguishes_scheduled_from_current_rules() -> None:
    _, _, client = _finance_client()
    saved = client.put(
        "/api/v1/cost/allocation-rules",
        json=_valid_rule_payload(),
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert saved.status_code == 200

    current = client.get("/api/v1/cost/allocation-rules?effective_at=2026-08-16")
    latest = client.get("/api/v1/cost/allocation-rules?mode=latest")

    assert current.get_json()["data"]["version_no"] == 1
    assert latest.get_json()["data"]["version_no"] == 2


def test_unknown_rule_mode_is_rejected() -> None:
    _, _, client = _finance_client()

    response = client.get("/api/v1/cost/allocation-rules?mode=unknown")

    assert response.status_code == 400
    assert response.get_json()["code"] == "COST_RULE_MODE_INVALID"


def test_rule_update_requires_csrf_and_manage_permission() -> None:
    _, costs, client = _finance_client()

    missing = client.put("/api/v1/cost/allocation-rules", json=_valid_rule_payload())
    assert missing.status_code == 403
    assert missing.get_json()["code"] == "CSRF_INVALID"

    saved = client.put(
        "/api/v1/cost/allocation-rules",
        json=_valid_rule_payload(),
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert saved.status_code == 200
    assert saved.get_json()["data"]["version_no"] == 2
    assert costs.created and costs.created["change_reason"] == "按月更新分摊口径"

    _, _, viewer = _finance_client(permissions=["cost.view"])
    forbidden = viewer.put(
        "/api/v1/cost/allocation-rules",
        json=_valid_rule_payload(),
        headers={"X-CSRF-Token": _csrf(viewer)},
    )
    assert forbidden.status_code == 403
    assert forbidden.get_json()["code"] == "FORBIDDEN"


def test_rule_update_rejects_incomplete_categories() -> None:
    _, _, client = _finance_client()
    payload = _valid_rule_payload()
    payload["rules"] = payload["rules"][:-1]

    response = client.put("/api/v1/cost/allocation-rules", json=payload, headers={"X-CSRF-Token": _csrf(client)})

    assert response.status_code == 400
    assert response.get_json()["code"] == "COST_RULES_INCOMPLETE"


def test_rule_update_rejects_nine_unknown_category_ids() -> None:
    _, _, client = _finance_client()
    payload = _valid_rule_payload()
    payload["rules"] = [
        {"category_id": item, "driver": "equal", "manual_ratio_json": None}
        for item in range(11, 20)
    ]

    response = client.put("/api/v1/cost/allocation-rules", json=payload, headers={"X-CSRF-Token": _csrf(client)})

    assert response.status_code == 400
    assert response.get_json()["code"] == "COST_RULES_INCOMPLETE"


def test_manual_ratios_must_total_one() -> None:
    _, _, client = _finance_client()
    payload = _valid_rule_payload()
    payload["rules"][0].update({"driver": "manual_ratio", "manual_ratio_json": {"pond-1": "0.6", "pond-2": "0.3"}})

    response = client.put("/api/v1/cost/allocation-rules", json=payload, headers={"X-CSRF-Token": _csrf(client)})

    assert response.status_code == 400
    assert response.get_json()["code"] == "COST_MANUAL_RATIO_INVALID"


def test_effective_date_must_be_first_day_of_a_future_month() -> None:
    _, _, client = _finance_client()
    payload = _valid_rule_payload()
    payload["effective_from"] = (_first_next_month() + timedelta(days=1)).isoformat()

    response = client.put("/api/v1/cost/allocation-rules", json=payload, headers={"X-CSRF-Token": _csrf(client)})

    assert response.status_code == 400
    assert response.get_json()["code"] == "COST_EFFECTIVE_DATE_INVALID"


def test_invalid_cost_dates_return_a_stable_validation_error() -> None:
    _, _, client = _finance_client()

    response = client.get("/api/v1/cost/structure?period_start=not-a-date&period_end=2026-08-16")

    assert response.status_code == 400
    assert response.get_json()["code"] == "COST_DATE_INVALID"
