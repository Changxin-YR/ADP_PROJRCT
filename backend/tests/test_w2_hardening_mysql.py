from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app import create_app
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.mysql_store import MySqlAuthStore
from backend.layers.common.security.session import hash_session_token, new_session_token
from backend.layers.features.master_data.master_data_service import MasterDataService
from backend.layers.features.master_data.master_data_store import MySqlMasterDataStore
from backend.tests.mysql_test_database import disposable_database, settings_for


def _login(client: Any, settings: Any, user_id: int) -> str:
    store = MySqlAuthStore(settings)
    token = new_session_token()
    store.create_session(
        user_id,
        token_hash=hash_session_token(token),
        ip="127.0.0.1",
        user_agent="pytest",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=12),
    )
    client.set_cookie("adp_session", token, path="/")
    csrf = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    return csrf


def _add_user(cursor: Any, phone: str, login_name: str, role_code: str) -> int:
    cursor.execute("INSERT INTO users (phone,login_name,name,password_hash,status) VALUES (%s,%s,%s,'hash','active')", (phone, login_name, login_name))
    user_id = int(cursor.lastrowid)
    cursor.execute("SELECT id FROM roles WHERE code=%s", (role_code,))
    role_id = int(cursor.fetchone()["id"])
    cursor.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s,%s)", (user_id, role_id))
    return user_id


def test_w2_mysql_migration_023_shrinks_role_permissions() -> None:
    with disposable_database("adp_w2_roles", through=23) as database:
        with get_connection(settings_for(database)) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS total FROM role_permissions rp
                INNER JOIN roles r ON r.id=rp.role_id INNER JOIN permissions p ON p.id=rp.permission_id
                WHERE (r.code='breed_worker' AND p.code IN ('warehouse.view','sales.view'))
                   OR (r.code='warehouse_manager' AND p.code='production.view')
                   OR (r.code='breed_manager' AND p.code='sales.view')
                """
            )
            assert int(cursor.fetchone()["total"]) == 0
            cursor.execute(
                """
                SELECT COUNT(*) AS total FROM role_permissions rp
                INNER JOIN roles r ON r.id=rp.role_id INNER JOIN permissions p ON p.id=rp.permission_id
                WHERE (r.code='breed_manager' AND p.code='production.view')
                   OR (r.code='warehouse_manager' AND p.code='warehouse.view')
                   OR (r.code='finance_staff' AND p.code='sales.view')
                   OR (r.code='breed_worker' AND p.code='production.view')
                """
            )
            assert int(cursor.fetchone()["total"]) == 4


def test_w2_mysql_role_shrink_visible_via_api() -> None:
    with disposable_database("adp_w2_role_api", through=23) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            worker_id = _add_user(cursor, "13990000051", "w2-worker", "breed_worker")
            manager_id = _add_user(cursor, "13990000052", "w2-wm", "warehouse_manager")
        app = create_app(settings)
        client = app.test_client()
        _login(client, settings, worker_id)
        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200
        permissions = set(me.get_json()["data"]["user"]["permissions"])
        assert "warehouse.view" not in permissions
        assert "sales.view" not in permissions
        assert "production.view" in permissions
        blocked = client.get("/api/v1/warehouse/receipts")
        assert blocked.status_code == 403
        assert blocked.get_json()["code"] == "FORBIDDEN"
        _login(client, settings, manager_id)
        me = client.get("/api/v1/auth/me")
        permissions = set(me.get_json()["data"]["user"]["permissions"])
        assert "production.view" not in permissions
        assert "warehouse.view" in permissions


def test_w2_mysql_pond_extended_fields_roundtrip() -> None:
    with disposable_database("adp_w2_pond_fields", through=24) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            maker_id = _add_user(cursor, "13990000053", "w2-pond-maker", "breed_manager")
            cursor.execute("SELECT id,organization_id FROM farms WHERE code='default-farm'")
            farm = cursor.fetchone()
            cursor.execute("INSERT INTO areas (organization_id,farm_id,code,name,status,row_version,created_by) VALUES (%s,%s,'W2-A','扩展区','verified',1,%s)", (farm["organization_id"], farm["id"], maker_id))
            area_id = int(cursor.lastrowid)
        service = MasterDataService(MySqlMasterDataStore(settings))
        manager = {"id": maker_id, "permissions": ["master_data.view", "master_data.ponds.manage"], "data_scopes": [{"scope_type": "area", "area_id": area_id}]}
        created = service.create(manager, "ponds", {
            "code": "W2-POND", "name": "扩展塘", "area_id": area_id, "capacity_mu": 8.5,
            "pond_status": "stocked", "aerator_count": 2, "stocking_spec": "2cm",
            "current_spec": "8cm", "stock_quantity": 3000, "stock_quantity_source": "sampled",
        })
        assert created["aerator_count"] == 2
        assert created["stocking_spec"] == "2cm"
        assert created["current_spec"] == "8cm"
        assert str(created["stock_quantity"]) == "3000.000"
        assert created["stock_quantity_source"] == "sampled"
        detail = service.get(manager, "ponds", created["id"])
        assert detail["stock_quantity_source"] == "sampled"
        plain = service.create(manager, "ponds", {"code": "W2-PLAIN", "name": "默认塘", "area_id": area_id})
        assert plain["aerator_count"] == 0
        assert plain["stock_quantity_source"] == "manual"
        assert plain["stock_quantity"] is None


def test_w2_mysql_pond_errors_are_400_409_not_500() -> None:
    with disposable_database("adp_w2_pond_errors", through=24) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            maker_id = _add_user(cursor, "13990000054", "w2-err-maker", "breed_manager")
            cursor.execute("SELECT id,organization_id FROM farms WHERE code='default-farm'")
            farm = cursor.fetchone()
            cursor.execute("INSERT INTO areas (organization_id,farm_id,code,name,status,row_version,created_by) VALUES (%s,%s,'W2-E','错误区','verified',1,%s)", (farm["organization_id"], farm["id"], maker_id))
            area_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO data_scopes (code,name,scope_type,area_id,status) VALUES (%s,'W2错误区范围','area',%s,'active')", (f"W2-E-SCOPE-{maker_id}", area_id))
            scope_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO user_data_scopes (user_id,data_scope_id,granted_by) VALUES (%s,%s,%s)", (maker_id, scope_id, maker_id))
        app = create_app(settings)
        client = app.test_client()
        csrf = _login(client, settings, maker_id)
        headers = {"X-CSRF-Token": csrf}
        base = {"code": "W2-ERR", "name": "错误塘", "area_id": area_id, "capacity_mu": 10}
        # 面积 'abc' → 400（服务层）
        response = client.post("/api/v1/master-data/ponds", json={**base, "capacity_mu": "abc"}, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["code"] == "FIELD_INVALID"
        # 超长名称 → 400
        response = client.post("/api/v1/master-data/ponds", json={**base, "name": "塘" * 121}, headers=headers)
        assert response.status_code == 400
        # 非法状态 → 400
        response = client.post("/api/v1/master-data/ponds", json={**base, "pond_status": "farming"}, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["code"] == "POND_STATUS_INVALID"
        # 正常创建
        response = client.post("/api/v1/master-data/ponds", json=base, headers=headers)
        assert response.status_code == 201
        # 重复编码 → 409 DUPLICATE_CODE（全局 1062 映射）
        response = client.post("/api/v1/master-data/ponds", json=base, headers=headers)
        assert response.status_code == 409
        assert response.get_json()["code"] == "DUPLICATE_CODE"
        # 塘口描述超长（无服务层拦截）→ 全局 DataError → 400 FIELD_INVALID 带字段名
        response = client.post("/api/v1/master-data/ponds", json={**base, "code": "W2-DESC", "description": "塘" * 600}, headers=headers)
        assert response.status_code == 400
        assert response.get_json()["code"] == "FIELD_INVALID"
        assert "description" in response.get_json()["message"]


def test_w2_mysql_feed_logs_filter_by_pond_and_area() -> None:
    with disposable_database("adp_w2_feed_filter", through=24) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            maker_id = _add_user(cursor, "13990000055", "w2-feed-maker", "breed_manager")
            cursor.execute("SELECT id,organization_id FROM farms WHERE code='default-farm'")
            farm = cursor.fetchone()
            cursor.execute(
                "INSERT INTO areas (organization_id,farm_id,code,name,status,row_version,created_by) VALUES (%s,%s,'W2-N','北区','verified',1,%s),(%s,%s,'W2-S','南区','verified',1,%s)",
                (farm["organization_id"], farm["id"], maker_id, farm["organization_id"], farm["id"], maker_id),
            )
            area_north = int(cursor.lastrowid)
            area_south = int(cursor.lastrowid) + 1
            cursor.execute("INSERT INTO data_scopes (code,name,scope_type,area_id,status) VALUES (%s,'W2养殖范围','area',%s,'active')", (f"W2-FEED-SCOPE-{maker_id}", area_north))
            scope_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO user_data_scopes (user_id,data_scope_id,granted_by) VALUES (%s,%s,%s)", (maker_id, scope_id, maker_id))
            cursor.execute("INSERT INTO data_scopes (code,name,scope_type,area_id,status) VALUES (%s,'W2养殖范围','area',%s,'active')", (f"W2-FEED-SCOPE-{maker_id}-S", area_south))
            scope_south_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO user_data_scopes (user_id,data_scope_id,granted_by) VALUES (%s,%s,%s)", (maker_id, scope_south_id, maker_id))
            cursor.execute(
                "INSERT INTO ponds (organization_id,farm_id,area_id,code,name,capacity_mu,pond_status,status,row_version,created_by) VALUES (%s,%s,%s,'W2-PN','北塘',5,'farming','verified',1,%s),(%s,%s,%s,'W2-PS','南塘',5,'farming','verified',1,%s)",
                (farm["organization_id"], farm["id"], area_north, maker_id, farm["organization_id"], farm["id"], area_south, maker_id),
            )
            pond_north = int(cursor.lastrowid)
            pond_south = int(cursor.lastrowid) + 1
        from backend.layers.features.production.production_store import MySqlProductionStore
        store = MySqlProductionStore(settings)
        actor = {"id": maker_id, "permissions": ["production.manage"], "data_scopes": []}
        store.create_record("feed-logs", {"code": "F-N1", "name": "北塘投喂", "pond_id": pond_north}, user=actor, user_id=maker_id)
        store.create_record("feed-logs", {"code": "F-S1", "name": "南塘投喂", "pond_id": pond_south}, user=actor, user_id=maker_id)
        app = create_app(settings)
        client = app.test_client()
        _login(client, settings, maker_id)
        north = client.get(f"/api/v1/production/feed-logs?pond_id={pond_north}")
        assert north.status_code == 200
        assert north.get_json()["data"]["total"] == 1
        assert north.get_json()["data"]["items"][0]["code"] == "F-N1"
        area = client.get(f"/api/v1/production/feed-logs?area_id={area_south}")
        assert area.get_json()["data"]["total"] == 1
        assert area.get_json()["data"]["items"][0]["code"] == "F-S1"
        missing = client.get("/api/v1/production/feed-logs?pond_id=999999")
        assert missing.status_code == 200
        assert missing.get_json()["data"]["total"] == 0
        invalid = client.get("/api/v1/production/feed-logs?pond_id=abc")
        assert invalid.status_code == 400
        assert invalid.get_json()["code"] == "PRODUCTION_FILTER_INVALID"


def test_w2_mysql_cost_draft_submit_creates_notification() -> None:
    with disposable_database("adp_w2_notify", through=24) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            maker_id = _add_user(cursor, "13990000056", "w2-cost-maker", "finance_staff")
            checker_id = _add_user(cursor, "13990000057", "w2-cost-checker", "finance_staff")
            cursor.execute("SELECT id,organization_id FROM farms WHERE code='default-farm'")
            farm = cursor.fetchone()
            cursor.execute("INSERT INTO areas (organization_id,farm_id,code,name,status,row_version,created_by) VALUES (%s,%s,'W2-C','成本区','verified',1,%s)", (farm["organization_id"], farm["id"], maker_id))
            area_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO data_scopes (code,name,scope_type,area_id,status) VALUES ('w2-cost-area','成本区数据','area',%s,'active')",
                (area_id,),
            )
            scope_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO user_data_scopes (user_id,data_scope_id,granted_by) VALUES (%s,%s,%s),(%s,%s,%s)",
                (maker_id, scope_id, maker_id, checker_id, scope_id, maker_id),
            )
        app = create_app(settings)
        client = app.test_client()
        csrf = _login(client, settings, maker_id)
        headers = {"X-CSRF-Token": csrf}
        payload = {
            "organization_id": int(farm["organization_id"]), "farm_id": int(farm["id"]), "area_id": area_id,
            "category_code": "feed", "amount": "100.00", "occurred_on": "2026-01-15",
            "period_start": "2026-01-01", "period_end": "2026-01-31",
            "source_type": "manual", "source_ref": "FEE-W2-1",
        }
        created = client.post("/api/v1/cost/expenses", json=payload, headers=headers)
        assert created.status_code == 201, created.get_json()
        entry_id = created.get_json()["data"]["id"]
        submitted = client.post(f"/api/v1/cost/expenses/{entry_id}/submit", json={"expected_version": 1}, headers=headers)
        assert submitted.status_code == 200, submitted.get_json()
        _login(client, settings, checker_id)
        notifications = client.get("/api/v1/notifications")
        assert notifications.status_code == 200
        items = notifications.get_json()["data"]["items"]
        matching = [item for item in items if "FEE-W2-1" in str(item.get("title", ""))]
        assert matching, f"未找到费用提交通知: {items}"
        assert matching[0]["status"] == "unread"
        assert "核验费用" in matching[0]["title"]
        # 数据库侧断言：work_items 与 notifications 同步生成
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT id FROM work_items WHERE source_key=%s", (f"cost:entry:{entry_id}:verify",))
            assert cursor.fetchone() is not None
            cursor.execute(
                "SELECT COUNT(*) AS total FROM notifications WHERE recipient_user_id=%s AND module_code='cost' AND object_id=%s",
                (checker_id, entry_id),
            )
            assert int(cursor.fetchone()["total"]) == 1
