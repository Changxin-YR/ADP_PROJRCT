from __future__ import annotations

from backend.app import create_app
from backend.tests.test_auth_api import FakeAuthStore, _csrf, _settings
from backend.tests.test_cost_enterprise_flow import FakeEnterpriseStore


def client_with_cost_permissions(permissions: list[str] | None = None):
    auth = FakeAuthStore()
    user = auth.add_user(phone="13800000401", login_name="cost-api", password="CostApi9!", status="active")
    user["permissions"] = permissions or [
        "cost.view", "cost.entry.manage", "cost.entry.verify", "cost.entry.confirm", "cost.entry.reverse",
        "cost.asset.manage", "cost.asset.verify", "cost.asset.confirm", "cost.allocation.manage",
        "cost.settlement.manage", "cost.settlement.verify", "cost.settlement.confirm", "cost.settlement.reverse",
    ]
    client = create_app(_settings(), store=auth, cost_store=FakeEnterpriseStore()).test_client()
    login = client.post("/api/v1/auth/login", json={"identifier": "cost-api", "password": "CostApi9!"}, headers={"X-CSRF-Token": _csrf(client)})
    assert login.status_code == 200
    return client


def test_cost_write_routes_reject_malformed_json_and_non_numeric_fields() -> None:
    client = client_with_cost_permissions()
    csrf = {"X-CSRF-Token": _csrf(client)}
    malformed = client.post("/api/v1/cost/expenses", data="{", content_type="application/json", headers=csrf)
    assert malformed.status_code == 400
    assert malformed.get_json()["code"] == "COST_PAYLOAD_INVALID"
    invalid_target = client.post(
        "/api/v1/cost/expenses",
        json={
            "organization_id": 1, "farm_id": 1, "area_id": 1, "category_code": "electricity",
            "amount": "120.00", "occurred_on": "2026-08-10", "period_start": "2026-08-01",
            "period_end": "2026-08-31", "source_type": "expense", "source_ref": "EXP-BAD-TARGET",
            "target_type": "pond", "target_id": "not-a-number",
        },
        headers=csrf,
    )
    assert invalid_target.status_code == 400
    assert invalid_target.get_json()["code"] == "COST_TARGET_INVALID"
    invalid_run = client.post(
        "/api/v1/cost/settlements",
        json={"period_start": "2026-08-01", "period_end": "2026-08-31", "allocation_run_id": "not-a-number"},
        headers=csrf,
    )
    assert invalid_run.status_code == 400
    assert invalid_run.get_json()["code"] == "COST_ALLOCATION_RUN_INVALID"


def test_cost_detail_routes_require_view_permission() -> None:
    client = client_with_cost_permissions(["cost.entry.manage"])
    for path in ("/api/v1/cost/expenses/1", "/api/v1/cost/assets/2", "/api/v1/cost/settlements/3"):
        response = client.get(path)
        assert response.status_code == 403
        assert response.get_json()["code"] == "FORBIDDEN"


def test_enterprise_cost_routes_list_real_resources_and_run_allocation() -> None:
    client = client_with_cost_permissions()
    for path in ("/api/v1/cost/expenses", "/api/v1/cost/assets", "/api/v1/cost/settlements"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.get_json()["data"]["total"] == 1
    report = client.get("/api/v1/cost/reports/net?period_start=2026-08-01&period_end=2026-08-31")
    assert report.status_code == 200
    allocation = client.post("/api/v1/cost/allocations", json={"period_start": "2026-08-01", "period_end": "2026-08-31", "farm_id": 1, "area_id": 2}, headers={"X-CSRF-Token": _csrf(client)})
    assert allocation.status_code == 201
    assert allocation.get_json()["data"]["allocated_total"] == "100.00"


def test_expense_routes_require_csrf_and_map_bound_evidence_errors() -> None:
    client = client_with_cost_permissions()
    missing = client.post("/api/v1/cost/expenses", json={})
    assert missing.status_code == 403
    submitted = client.post("/api/v1/cost/expenses/1/submit", json={"expected_version": 1}, headers={"X-CSRF-Token": _csrf(client)})
    assert submitted.status_code == 200
    invalid = client.post("/api/v1/cost/expenses/1/verify", json={"expected_version": 2, "evidence_attachment_ids": [99]}, headers={"X-CSRF-Token": _csrf(client)})
    assert invalid.status_code == 422
    assert invalid.get_json()["code"] == "EVIDENCE_INVALID"


def test_legacy_entry_write_routes_share_the_governed_expense_lifecycle() -> None:
    client = client_with_cost_permissions()
    payload = {"category_code": "electricity", "amount": "120.00", "occurred_on": "2026-08-10", "period_start": "2026-08-01", "period_end": "2026-08-31", "source_type": "expense", "source_ref": "EXP-LEGACY-1"}
    created = client.post("/api/v1/cost/entries", json=payload, headers={"X-CSRF-Token": _csrf(client)})
    assert created.status_code == 201
    submitted = client.post("/api/v1/cost/entries/1/submit", json={"expected_version": 1}, headers={"X-CSRF-Token": _csrf(client)})
    assert submitted.status_code == 200
    invalid = client.post("/api/v1/cost/entries/1/verify", json={"expected_version": 2, "evidence_attachment_ids": [99]}, headers={"X-CSRF-Token": _csrf(client)})
    assert invalid.status_code == 422
    assert invalid.get_json()["code"] == "EVIDENCE_INVALID"


def test_settlement_draft_update_and_delete_routes_are_real() -> None:
    client = client_with_cost_permissions(); csrf = {"X-CSRF-Token": _csrf(client)}
    updated = client.patch("/api/v1/cost/settlements/3", json={"name": "八月正式结算", "expected_version": 1}, headers=csrf)
    assert updated.status_code == 200
    assert updated.get_json()["data"]["name"] == "八月正式结算"
    client = client_with_cost_permissions(); csrf = {"X-CSRF-Token": _csrf(client)}
    deleted = client.delete("/api/v1/cost/settlements/3", headers=csrf)
    assert deleted.status_code == 200
    assert deleted.get_json()["data"]["status"] == "draft"
