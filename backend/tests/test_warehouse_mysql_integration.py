from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pymysql
import pytest

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.production.production_store import MySqlProductionStore
from backend.layers.features.warehouse.warehouse_service import WarehouseService
from backend.layers.features.warehouse.warehouse_store import MySqlWarehouseStore
from backend.tests.mysql_test_database import disposable_database, settings_for


def _seed(settings: Any) -> dict[str, int]:
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO users (phone,name,password_hash,status) VALUES (%s,%s,'hash','active')",
            [("13810000001", "经办人"), ("13810000002", "核验人"), ("13810000003", "接收人")],
        )
        cursor.execute("SELECT id AS organization_id FROM organizations WHERE code='default'")
        ids = dict(cursor.fetchone())
        cursor.execute("SELECT id AS farm_id FROM farms WHERE code='default-farm'")
        ids.update(cursor.fetchone())
        cursor.execute(
            "INSERT INTO areas (organization_id,farm_id,code,name,status,created_by) VALUES (%s,%s,'A','A区','verified',1)",
            (ids["organization_id"], ids["farm_id"]),
        )
        ids["area_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO ponds (organization_id,farm_id,area_id,code,name,pond_status,status,created_by) VALUES (%s,%s,%s,'P1','一号塘','farming','verified',1)",
            (ids["organization_id"], ids["farm_id"], ids["area_id"]),
        )
        ids["pond_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO materials (organization_id,farm_id,area_id,code,name,unit,safety_stock,status,created_by) VALUES (%s,%s,%s,'FEED-1','成鱼饲料','kg',80,'verified',1)",
            (ids["organization_id"], ids["farm_id"], ids["area_id"]),
        )
        ids["material_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO business_partners (organization_id,farm_id,area_id,partner_type,code,name,status,created_by) VALUES (%s,%s,%s,'supplier','SUP-1','测试供应商','verified',1)",
            (ids["organization_id"], ids["farm_id"], ids["area_id"]),
        )
        ids["supplier_id"] = int(cursor.lastrowid)
        cursor.executemany(
            "INSERT INTO warehouses (organization_id,farm_id,area_id,code,name) VALUES (%s,%s,%s,%s,%s)",
            [
                (ids["organization_id"], ids["farm_id"], ids["area_id"], "W1", "主仓"),
                (ids["organization_id"], ids["farm_id"], ids["area_id"], "W2", "周转仓"),
            ],
        )
        cursor.execute("SELECT id FROM warehouses ORDER BY id")
        ids["warehouse_1"], ids["warehouse_2"] = [int(row["id"]) for row in cursor.fetchall()]
        cursor.execute(
            "INSERT INTO purchase_orders (organization_id,farm_id,area_id,code,name,supplier_id,material_id,warehouse_id,quantity,unit_price,total_amount,due_date,status,created_by) VALUES (%s,%s,%s,'PO-ALERT','预警补货',%s,%s,%s,100,5,500,'2026-12-31','approved',1)",
            (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["supplier_id"], ids["material_id"], ids["warehouse_1"]),
        )
        ids["purchase_order_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,'test',1,%s,%s,'receipt.pdf','application/pdf',10,1)",
            (ids["organization_id"], "a" * 64, "b" * 32),
        )
        ids["attachment_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO production_batches (organization_id,farm_id,area_id,code,name,pond_id,species,status,created_by) VALUES (%s,%s,%s,'B1','测试批次',%s,'草鱼','verified',1)",
            (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["pond_id"]),
        )
        ids["batch_id"] = int(cursor.lastrowid)
    return ids


def _actor(user_id: int) -> dict[str, Any]:
    return {
        "id": user_id,
        "permissions": ["warehouse.view", "warehouse.manage", "warehouse.verify"],
        "data_scopes": [],
    }


def _balance(settings: Any, warehouse_id: int) -> Decimal:
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COALESCE(SUM(quantity_delta),0) AS quantity FROM inventory_ledger WHERE warehouse_id=%s", (warehouse_id,))
        return Decimal(str(cursor.fetchone()["quantity"]))


def _create_submit(service: WarehouseService, actor: dict[str, Any], resource: str, payload: dict[str, Any]) -> dict[str, Any]:
    created = service.create(actor, resource, payload)
    return service.submit(actor, resource, int(created["id"]), {"expected_version": created["version"]})


def _bind_receipt_evidence(settings: Any, record_id: int, attachment_id: int) -> None:
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE attachments SET entity_type='warehouse:receipts',entity_id=%s WHERE id=%s", (record_id, attachment_id))


def test_real_mysql_warehouse_business_chain_is_transactional_and_immutable() -> None:
    with disposable_database("adp_warehouse_test", through=25) as database:
        settings = settings_for(database)
        ids = _seed(settings)
        service = WarehouseService(MySqlWarehouseStore(settings))
        creator, verifier, receiver = _actor(1), _actor(2), _actor(3)
        base = {"warehouse_id": ids["warehouse_1"], "material_id": ids["material_id"]}

        receipt = _create_submit(service, creator, "receipts", {
            **base, "code": "IN-1", "name": "采购入库", "quantity": 100, "unit_cost": 5,
            "lot_no": "LOT-1", "expiry_date": (date.today() + timedelta(days=10)).isoformat(),
        })
        with pytest.raises(DomainError, match="WAREHOUSE_CODE_EXISTS"):
            service.create(creator, "receipts", {
                **base, "code": "IN-1", "name": "重复采购入库", "quantity": 1,
                "unit_cost": 5, "lot_no": "LOT-1",
            })
        _bind_receipt_evidence(settings, receipt["id"], ids["attachment_id"])
        receipt = service.verify(verifier, "receipts", receipt["id"], {
            "expected_version": receipt["version"], "evidence_attachment_ids": [ids["attachment_id"]],
        })
        lot_id = int(receipt["inventory_lot_id"])
        assert _balance(settings, ids["warehouse_1"]) == Decimal("100")

        request = _create_submit(service, creator, "issue-requests", {
            **base, "code": "REQ-1", "name": "投喂领料", "quantity": 40,
            "scene": "feed", "pond_id": ids["pond_id"], "batch_id": ids["batch_id"],
        })
        request = service.verify(verifier, "issue-requests", request["id"], {"expected_version": request["version"]})
        issue = _create_submit(service, creator, "issues", {
            **base, "code": "OUT-1", "name": "实际出库", "quantity": 30, "scene": "feed",
            "pond_id": ids["pond_id"], "batch_id": ids["batch_id"], "source_document_id": request["id"],
        })
        issue = service.verify(verifier, "issues", issue["id"], {"expected_version": issue["version"]})
        assert _balance(settings, ids["warehouse_1"]) == Decimal("70")

        excessive = _create_submit(service, creator, "issues", {
            **base, "code": "OUT-2", "name": "超额出库", "quantity": 15, "scene": "feed",
            "pond_id": ids["pond_id"], "source_document_id": request["id"],
        })
        with pytest.raises(DomainError, match="WAREHOUSE_ISSUE_REQUEST_INVALID"):
            service.verify(verifier, "issues", excessive["id"], {"expected_version": excessive["version"]})
        assert service.get(verifier, "issues", excessive["id"])["status"] == "submitted"

        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,material_id,quantity,status,created_by) VALUES (%s,%s,%s,'feed_task','FT-1','投喂任务',%s,%s,%s,30,'verified',1)",
                (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["batch_id"], ids["pond_id"], ids["material_id"]),
            )
            task_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,material_id,feed_task_id,material_issue_request_id,quantity,status,created_by) VALUES (%s,%s,%s,'feed_log','FL-1','投喂记录',%s,%s,%s,%s,%s,31,'submitted',1)",
                (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["batch_id"], ids["pond_id"], ids["material_id"], task_id, request["id"]),
            )
            feed_log_id = int(cursor.lastrowid)
        production = MySqlProductionStore(settings)
        with pytest.raises(DomainError, match="FEED_MATERIAL_ISSUE_REQUIRED"):
            production.set_status("feed-logs", feed_log_id, "verified", expected_version=1, user_id=2)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE production_documents SET quantity=30 WHERE id=%s", (feed_log_id,))
        assert production.set_status("feed-logs", feed_log_id, "verified", expected_version=1, user_id=2)["status"] == "verified"

        correction = service.correct(creator, "receipts", receipt["id"], {
            "expected_version": receipt["version"], "code": "IN-1-C1", "quantity": 90,
            "correction_reason": "复核送货单后更正数量",
        })
        correction = service.submit(creator, "receipts", correction["id"], {"expected_version": correction["version"]})
        _bind_receipt_evidence(settings, correction["id"], ids["attachment_id"])
        service.verify(verifier, "receipts", correction["id"], {
            "expected_version": correction["version"], "evidence_attachment_ids": [ids["attachment_id"]],
        })
        assert _balance(settings, ids["warehouse_1"]) == Decimal("60")
        assert service.get(verifier, "receipts", receipt["id"])["status"] == "verified"

        transfer = _create_submit(service, creator, "transfers", {
            **base, "target_warehouse_id": ids["warehouse_2"], "code": "TR-1", "name": "取消调拨", "quantity": 20,
        })
        transfer = service.dispatch(verifier, "transfers", transfer["id"], {"expected_version": transfer["version"]})
        assert _balance(settings, ids["warehouse_1"]) == Decimal("40")
        cancelled_transfer_id = int(transfer["id"])
        service.cancel_transfer(receiver, "transfers", transfer["id"], {
            "expected_version": transfer["version"], "cancellation_reason": "目标仓暂停收货",
        })
        assert _balance(settings, ids["warehouse_1"]) == Decimal("60")

        transfer = _create_submit(service, creator, "transfers", {
            **base, "target_warehouse_id": ids["warehouse_2"], "code": "TR-2", "name": "差异调拨", "quantity": 20,
        })
        transfer = service.dispatch(verifier, "transfers", transfer["id"], {"expected_version": transfer["version"]})
        service.receive(receiver, "transfers", transfer["id"], {
            "expected_version": transfer["version"], "received_quantity": 18, "receipt_difference_reason": "途中破包损耗2kg",
        })
        assert (_balance(settings, ids["warehouse_1"]), _balance(settings, ids["warehouse_2"])) == (Decimal("40"), Decimal("18"))

        alert = next(item for item in service.alerts(verifier) if int(item["inventory_lot_id"]) == lot_id and int(item["warehouse_id"]) == ids["warehouse_1"])
        service.handle_alert(creator, alert["alert_key"], {"action_code": "replenish", "purchase_order_id": ids["purchase_order_id"], "resolution_note": "采购申请已提交"})
        assert next(item for item in service.alerts(verifier) if item["alert_key"] == alert["alert_key"])["status"] == "handled"
        extra = _create_submit(service, creator, "receipts", {**base, "inventory_lot_id": lot_id, "code": "IN-2", "name": "补收入库", "quantity": 1})
        _bind_receipt_evidence(settings, extra["id"], ids["attachment_id"])
        service.verify(verifier, "receipts", extra["id"], {"expected_version": extra["version"], "evidence_attachment_ids": [ids["attachment_id"]]})
        assert next(item for item in service.alerts(verifier) if item["alert_key"] == alert["alert_key"])["status"] == "pending"

        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status,cancel_reason FROM work_items WHERE source_key=%s", (f"warehouse:transfers:{transfer['id']}:verify",))
            assert cursor.fetchone()["status"] == "completed"
            cursor.execute("SELECT status,cancel_reason FROM work_items WHERE source_key=%s", (f"warehouse:transfers:{cancelled_transfer_id}:verify",))
            cancelled_item = cursor.fetchone()
            assert cancelled_item == {"status": "cancelled", "cancel_reason": "目标仓暂停收货"}
        with pytest.raises(pymysql.OperationalError, match="immutable"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE warehouse_documents SET name='禁止修改' WHERE id=%s", (receipt["id"],))
        with pytest.raises(pymysql.OperationalError, match="append-only"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("DELETE FROM inventory_ledger WHERE source_id=%s LIMIT 1", (receipt["id"],))
        with pytest.raises(pymysql.IntegrityError):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,material_id,quantity,created_by) VALUES (%s,%s,%s,'receipt','BAD-FK','非法外键',%s,999999,1,1)",
                    (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["warehouse_1"]),
                )
