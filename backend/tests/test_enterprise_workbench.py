from __future__ import annotations

from typing import Any
from pathlib import Path

import pytest

from backend.app import create_app
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.mysql_store import MySqlAuthStore
from backend.layers.features.workbench.workbench_service import WorkbenchService, WorkbenchServiceError
from backend.tests.mysql_test_database import disposable_database, settings_for
from fake_auth_store import FakeAuthStore
from test_auth_api import _csrf, _settings


class EnterpriseWorkbenchStore(FakeAuthStore):
    def __init__(self) -> None:
        super().__init__()
        self.items = [
            {"id": 1, "title": "核验塘口", "action_code": "verify", "status": "pending", "row_version": 1},
            {"id": 2, "title": "已完成核验", "action_code": "verify", "status": "completed", "row_version": 2},
        ]

    def workbench_summary(self, *, user: dict[str, Any]) -> dict[str, Any]:
        assert user["data_scopes"] == [{"scope_type": "area", "area_id": 8}]
        return {
            "date_label": "2026年08月17日 星期一",
            "kpis": {"ponds": 2, "active_batches": 1, "current_stock": 900, "todo_open": 1},
            "pond_status": [{"status": "farming", "label": "养殖中", "count": 2}],
            "todos": [{"id": 1, "title": "核验塘口", "type": "核验", "due_at": "今天", "overdue": False}],
            "alerts": [],
            "recent_batches": [],
        }

    def list_work_items(self, *, user: dict[str, Any], status: str | None, include_history: bool, page: int, page_size: int) -> dict[str, Any]:
        assert user["permissions"] == ["workbench.enter", "work_item.view", "work_item.manage"]
        rows = self.items if include_history else [item for item in self.items if item["status"] == "pending"]
        return {"items": rows, "page": page, "page_size": page_size, "total": len(rows), "has_next": False}

    def transition_work_item(self, item_id: int, *, user: dict[str, Any], action: str, expected_version: int | None, note: str | None) -> dict[str, Any]:
        item = next(row for row in self.items if row["id"] == item_id)
        assert action == "complete" and expected_version == item["row_version"]
        item.update(status="completed", completed_by=user["id"], completion_note=note, row_version=item["row_version"] + 1)
        return dict(item)

    def list_notifications(self, **kwargs: Any) -> dict[str, Any]:
        return {"items": [], "page": kwargs["page"], "page_size": kwargs["page_size"], "total": 0, "has_next": False}

    def mark_notification_read(self, notification_id: int, *, user_id: int) -> dict[str, Any]:
        return {"id": notification_id, "recipient_user_id": user_id, "status": "read"}

    def close_notification(self, notification_id: int, *, user_id: int, conclusion: str) -> dict[str, Any]:
        return {"id": notification_id, "recipient_user_id": user_id, "status": "closed", "close_conclusion": conclusion}


def user() -> dict[str, Any]:
    return {
        "id": 7,
        "permissions": ["workbench.enter", "work_item.view", "work_item.manage"],
        "data_scopes": [{"scope_type": "area", "area_id": 8}],
    }


def test_summary_and_queue_receive_complete_user_scope() -> None:
    service = WorkbenchService(EnterpriseWorkbenchStore())

    assert service.summary(user())["kpis"]["ponds"] == 2
    assert service.list_work_items(user(), include_history=False)["total"] == 1


def test_completed_item_leaves_pending_queue_but_remains_in_history() -> None:
    store = EnterpriseWorkbenchStore()
    service = WorkbenchService(store)

    completed = service.transition_work_item(user(), 1, action="complete", expected_version=1, note="已核验")

    assert completed["status"] == "completed"
    assert service.list_work_items(user(), include_history=False)["items"] == []
    assert service.list_work_items(user(), include_history=True)["total"] == 2


def test_workbench_summary_route_returns_real_store_aggregate() -> None:
    store = EnterpriseWorkbenchStore()
    account = store.add_user(phone="13800000988", login_name="operator", password="Correct9!", status="active")
    account.update(user())
    client = create_app(_settings(), store=store).test_client()
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "operator", "password": "Correct9!"},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert login.status_code == 200

    response = client.get("/api/v1/workbench/summary")

    assert response.status_code == 200
    assert response.get_json()["data"]["kpis"]["current_stock"] == 900


def test_migration_fixes_finance_role_and_defines_complete_menu_matrix() -> None:
    migration = Path(__file__).parents[2] / "database/migrations/018_workbench_permissions.sql"
    text = migration.read_text(encoding="utf-8")
    assert "finance_staff" in text
    assert "'finance'" not in text
    for permission in ("master_data.view", "production.view", "warehouse.view", "purchase.view", "sales.view", "cost.view", "data_exchange.view"):
        assert permission in text


def test_finance_permissions_expose_finance_work_items() -> None:
    modules = MySqlAuthStore._work_item_modules({"finance.payable.view", "finance.receivable.view"})

    assert "finance" in modules


def test_real_mysql_workbench_uses_scoped_business_facts_and_role_matrix() -> None:
    with disposable_database("adp_workbench", through=18) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO users (phone,login_name,name,password_hash,status) VALUES ('13990000018','workbench-admin','工作台管理员','hash','active')")
            user_id = int(cursor.lastrowid)
            cursor.execute("SELECT id FROM roles WHERE code='super_admin'"); role_id = int(cursor.fetchone()["id"])
            cursor.execute("SELECT id FROM data_scopes WHERE code='farm-all'"); scope_id = int(cursor.fetchone()["id"])
            cursor.execute("INSERT INTO user_roles (user_id,role_id,granted_by) VALUES (%s,%s,%s)", (user_id, role_id, user_id))
            cursor.execute("INSERT INTO user_data_scopes (user_id,data_scope_id,granted_by) VALUES (%s,%s,%s)", (user_id, scope_id, user_id))
            cursor.execute("SELECT id,organization_id FROM farms WHERE code='default-farm'"); farm = cursor.fetchone()
            cursor.execute("INSERT INTO areas (organization_id,farm_id,code,name,status,row_version,created_by) VALUES (%s,%s,'WB-A','工作台区域','verified',1,%s)", (farm["organization_id"], farm["id"], user_id))
            area_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO ponds (organization_id,farm_id,area_id,code,name,capacity_mu,pond_status,status,row_version,created_by) VALUES (%s,%s,%s,'WB-P','工作台塘口',10,'farming','verified',1,%s)", (farm["organization_id"], farm["id"], area_id, user_id))
            pond_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO production_batches (organization_id,farm_id,area_id,pond_id,code,name,species,batch_status,status,created_by) VALUES (%s,%s,%s,%s,'WB-B','工作台批次','鲈鱼','farming','verified',%s)", (farm["organization_id"], farm["id"], area_id, pond_id, user_id))
            batch_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO batch_stock_records (organization_id,batch_id,pond_id,source_type,source_id,quantity_delta,posted_by) VALUES (%s,%s,%s,'stocking',%s,900,%s)", (farm["organization_id"], batch_id, pond_id, batch_id, user_id))
            cursor.execute("INSERT INTO work_items (organization_id,assignee_user_id,module_code,action_code,object_type,object_id,source_key,title,status) VALUES (%s,%s,'production','verify','production:batches',%s,'wb:verify','核验工作台批次','pending')", (farm["organization_id"], user_id, batch_id))
            cursor.execute("INSERT INTO notifications (recipient_user_id,module_code,notification_type,dedup_key,title,level,status) VALUES (%s,'production','exception','wb:notice','批次异常提醒','high','unread')", (user_id,))
            cursor.execute("SELECT COUNT(*) AS total FROM role_permissions rp INNER JOIN roles r ON r.id=rp.role_id INNER JOIN permissions p ON p.id=rp.permission_id WHERE r.code='finance_staff' AND p.code='data_exchange.view'")
            assert int(cursor.fetchone()["total"]) == 1
            cursor.execute("SELECT COUNT(*) AS total FROM permissions WHERE code='workbench.enter'")
            assert int(cursor.fetchone()["total"]) == 1
            cursor.execute("SELECT COUNT(*) AS total FROM role_permissions rp INNER JOIN roles r ON r.id=rp.role_id INNER JOIN permissions p ON p.id=rp.permission_id WHERE r.code='super_admin' AND p.code='workbench.enter'")
            assert int(cursor.fetchone()["total"]) == 1

            cursor.execute("INSERT INTO users (phone,login_name,name,password_hash,status) VALUES ('13990000020','workbench-purchaser','采购测试员','hash','active')")
            purchaser_id = int(cursor.lastrowid)
            cursor.execute("SELECT id FROM roles WHERE code='purchaser'"); purchaser_role_id = int(cursor.fetchone()["id"])
            cursor.execute("INSERT INTO user_roles (user_id,role_id,granted_by) VALUES (%s,%s,%s)", (purchaser_id, purchaser_role_id, user_id))
            cursor.execute("INSERT INTO user_data_scopes (user_id,data_scope_id,granted_by) VALUES (%s,%s,%s)", (purchaser_id, scope_id, user_id))
            cursor.execute("INSERT INTO work_items (organization_id,module_code,action_code,object_type,object_id,source_key,title,status) VALUES (%s,'production','verify','production:batches',%s,'wb:unassigned-domain','未分配领域核验','pending')", (farm["organization_id"], batch_id))
            unassigned_domain_id = int(cursor.lastrowid)

        store = MySqlAuthStore(settings)
        current = store.get_user_by_id(user_id)
        assert current is not None
        summary = WorkbenchService(store).summary(current)

        assert summary["kpis"] == {"ponds": 1, "active_batches": 1, "current_stock": 900.0, "todo_open": 2}
        assert any(item["title"] == "核验工作台批次" for item in summary["todos"])
        assert summary["alerts"][0]["title"] == "批次异常提醒"

        purchaser = store.get_user_by_id(purchaser_id)
        assert purchaser is not None
        restricted = WorkbenchService(store).summary(purchaser)
        assert restricted["availability"]["production"] is False
        assert restricted["kpis"]["ponds"] is None
        assert restricted["kpis"]["active_batches"] is None
        assert restricted["kpis"]["current_stock"] is None
        with pytest.raises(WorkbenchServiceError) as caught:
            WorkbenchService(store).transition_work_item(purchaser, unassigned_domain_id, action="claim", expected_version=1)
        assert caught.value.code == "FORBIDDEN"
