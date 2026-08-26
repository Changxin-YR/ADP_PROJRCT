from __future__ import annotations

from decimal import Decimal
from typing import Any

import pymysql
import pytest

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.sales.sales_service import SalesService
from backend.layers.features.sales.sales_store import MySqlSalesStore
from backend.tests.mysql_test_database import ROOT, disposable_database, run_mysql, settings_for


def actor(user_id: int, *permissions: str) -> dict[str, Any]:
    return {"id": user_id, "permissions": list(permissions), "data_scopes": []}


def one(settings: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return dict(cursor.fetchone())


def seed(settings: Any) -> dict[str, int]:
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO users (phone,name,password_hash,status) VALUES (%s,%s,'hash','active')",
            [("13930000001", "销售经办"), ("13930000002", "销售审批"), ("13930000003", "收款经办"), ("13930000004", "收款核验")],
        )
        cursor.execute("SELECT id AS organization_id FROM organizations WHERE code='default'")
        ids = dict(cursor.fetchone())
        cursor.execute("SELECT id AS farm_id FROM farms WHERE code='default-farm'")
        ids.update(cursor.fetchone())
        cursor.execute("INSERT INTO areas (organization_id,farm_id,code,name,status,created_by) VALUES (%s,%s,'SA','销售区','verified',1)", (ids["organization_id"], ids["farm_id"]))
        ids["area_id"] = int(cursor.lastrowid)
        cursor.execute("INSERT INTO ponds (organization_id,farm_id,area_id,code,name,status,created_by) VALUES (%s,%s,%s,'SP1','销售塘','verified',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"]))
        ids["pond_id"] = int(cursor.lastrowid)
        cursor.execute("INSERT INTO business_partners (organization_id,farm_id,area_id,partner_type,code,name,settlement_days,status,created_by) VALUES (%s,%s,%s,'customer','C1','水产客户',30,'verified',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"]))
        ids["customer_id"] = int(cursor.lastrowid)
        cursor.execute("INSERT INTO production_batches (organization_id,farm_id,area_id,pond_id,code,name,species,initial_quantity,initial_weight_kg,stocked_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,%s,'SB1','鲈鱼批次','鲈鱼',100,100,'2026-06-01','verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["pond_id"]))
        ids["batch_id"] = int(cursor.lastrowid)
        cursor.execute("INSERT INTO batch_stock_records (organization_id,batch_id,pond_id,source_type,source_id,line_no,quantity_delta,weight_delta_kg,posted_by) VALUES (%s,%s,%s,'stocking',%s,1,100,100,2)", (ids["organization_id"], ids["batch_id"], ids["pond_id"], ids["batch_id"]))
        cursor.execute("INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,quantity,weight_kg,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'harvest','SH1','首批出塘',%s,%s,40,40,'2026-08-18','verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["batch_id"], ids["pond_id"]))
        ids["harvest_id"] = int(cursor.lastrowid)
        cursor.execute("INSERT INTO batch_stock_records (organization_id,batch_id,pond_id,source_type,source_id,line_no,quantity_delta,weight_delta_kg,posted_by) VALUES (%s,%s,%s,'harvest',%s,1,-40,-40,2)", (ids["organization_id"], ids["batch_id"], ids["pond_id"], ids["harvest_id"]))
        for index, entity in enumerate(("unbound",) * 6, 1):
            cursor.execute("INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,%s,1,%s,%s,%s,'application/pdf',12,3)", (ids["organization_id"], entity, str(index) * 64, format(index + 4, "x") * 32, f"voucher-{index}.pdf"))
            ids[f"attachment_{index}"] = int(cursor.lastrowid)
    return ids


def test_real_mysql_sales_delivery_receivable_receipt_and_reversal_chain() -> None:
    with disposable_database("adp_sales_test", through=14) as database:
        settings = settings_for(database); ids = seed(settings); store = MySqlSalesStore(settings); service = SalesService(store)
        seller = actor(1, "sales.view", "sales.manage"); approver = actor(2, "sales.view", "sales.verify", "sales.manage")
        cashier = actor(3, "finance.receivable.view", "finance.receipt.manage"); checker = actor(4, "finance.receivable.view", "finance.receipt.verify"); finance_editor = actor(2, "finance.receipt.manage", "finance.receipt.verify")
        order = service.create_order(seller, {"code": "SO-REAL-1", "name": "真实鲈鱼销售", "customer_id": ids["customer_id"], "pond_id": ids["pond_id"], "batch_id": ids["batch_id"], "species": "鲈鱼", "quantity": 100, "unit": "kg", "unit_price": 26, "sold_at": "2026-08-17", "due_date": "2026-09-17"})
        with pytest.raises(DomainError, match="EVIDENCE_INVALID"):
            service.update_order(seller, order["id"], {"expected_version": order["version"], "evidence_attachment_ids": [ids["attachment_6"]]})
        order = service.submit_order(seller, order["id"], {"expected_version": order["version"]})
        outside = actor(2, "sales.view", "sales.verify"); outside["data_scopes"] = [{"scope_type": "area", "area_id": ids["area_id"] + 1}]
        with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
            service.approve_order(outside, order["id"], {"expected_version": order["version"]})
        order = service.approve_order(approver, order["id"], {"expected_version": order["version"]})
        assert one(settings, "SELECT status FROM work_items WHERE source_key=%s", (f"sales:order:{order['id']}:approve",))["status"] == "completed"
        delivery = service.create_delivery(seller, {"code": "SD-REAL-1", "name": "首批交付", "sales_order_id": order["id"], "harvest_document_id": ids["harvest_id"], "quantity": 40, "delivered_at": "2026-08-18"})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,quantity,weight_kg,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'harvest','SH2','第二批出塘',%s,%s,40,40,'2026-08-18','verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["batch_id"], ids["pond_id"]))
            second_harvest = int(cursor.lastrowid)
        with pytest.raises(DomainError) as duplicate_code:
            service.create_delivery(seller, {"code": "SD-REAL-1", "name": "重复单号", "sales_order_id": order["id"], "harvest_document_id": second_harvest, "quantity": 40, "delivered_at": "2026-08-18"})
        assert duplicate_code.value.code == "SALES_DELIVERY_CONFLICT"
        with pytest.raises(DomainError, match="VERSION_CONFLICT"):
            store.update_delivery(delivery["id"], {"harvest_document_id": second_harvest, "quantity": 40}, expected_version=99, user=seller, user_id=1)
        assert one(settings, "SELECT harvest_root_id FROM sales_delivery_harvest_claims WHERE sales_delivery_id=%s", (delivery["id"],))["harvest_root_id"] == ids["harvest_id"]
        delivery = service.submit_delivery(seller, delivery["id"], {"expected_version": delivery["version"]})
        with pytest.raises(DomainError, match="EVIDENCE_INVALID"):
            service.verify_delivery(approver, delivery["id"], {"expected_version": delivery["version"], "evidence_attachment_ids": [ids["attachment_1"]]})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_type='sales:delivery',entity_id=%s WHERE id=%s", (delivery["id"], ids["attachment_1"]))
        delivery = service.verify_delivery(approver, delivery["id"], {"expected_version": delivery["version"], "evidence_attachment_ids": [ids["attachment_1"]]})
        assert one(settings, "SELECT SUM(weight_delta_kg) AS stock FROM batch_stock_records WHERE batch_id=%s", (ids["batch_id"],))["stock"] == Decimal("60.000")
        receivable = one(settings, "SELECT id,amount,received_amount,status FROM sales_receivables WHERE source_delivery_id=%s", (delivery["id"],))
        assert receivable == {"id": receivable["id"], "amount": Decimal("1040.00"), "received_amount": Decimal("0.00"), "status": "unpaid"}
        assert service.list_orders(approver)["items"][0]["delivered_quantity"] == Decimal("40.000")
        with pytest.raises(DomainError):
            service.verify_delivery(approver, delivery["id"], {"expected_version": delivery["version"], "evidence_attachment_ids": [ids["attachment_1"]]})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,quantity,weight_kg,happened_at,correction_of_id,note,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'harvest','SH1-C','更正出塘',%s,%s,35,35,'2026-08-18',%s,'复核为35','verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["batch_id"], ids["pond_id"], ids["harvest_id"]))
            corrected_harvest = int(cursor.lastrowid)
            cursor.execute("INSERT INTO batch_stock_records (organization_id,batch_id,pond_id,source_type,source_id,line_no,quantity_delta,weight_delta_kg,posted_by) VALUES (%s,%s,%s,'correction',%s,1,5,5,2)", (ids["organization_id"], ids["batch_id"], ids["pond_id"], corrected_harvest))
        with pytest.raises(DomainError, match="SALES_HARVEST_ALREADY_DELIVERED"):
            service.create_delivery(seller, {"code": "SD-DUP", "name": "重复交付", "sales_order_id": order["id"], "harvest_document_id": corrected_harvest, "quantity": 35, "delivered_at": "2026-08-18"})
        correction = service.correct_delivery(seller, delivery["id"], {"expected_version": delivery["version"], "code": "SD-REAL-1-C", "harvest_document_id": corrected_harvest, "quantity": 35, "correction_reason": "客户复核交付35"})
        correction = service.submit_delivery(seller, correction["id"], {"expected_version": correction["version"]})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_type='sales:delivery',entity_id=%s WHERE id=%s", (correction["id"], ids["attachment_4"]))
        service.verify_delivery(approver, correction["id"], {"expected_version": correction["version"], "evidence_attachment_ids": [ids["attachment_4"]]})
        assert one(settings, "SELECT SUM(weight_delta_kg) AS stock FROM batch_stock_records WHERE batch_id=%s", (ids["batch_id"],))["stock"] == Decimal("65.000")
        assert one(settings, "SELECT amount+COALESCE((SELECT SUM(amount_delta) FROM sales_receivable_adjustments WHERE receivable_id=sales_receivables.id),0) AS amount FROM sales_receivables WHERE id=%s", (receivable["id"],))["amount"] == Decimal("910.00")
        assert service.list_orders(approver)["items"][0]["delivered_quantity"] == Decimal("35.000")
        receipt = service.create_receipt(cashier, {"code": "RC-REAL-1", "name": "客户首款", "receivable_id": receivable["id"], "amount": 400, "received_at": "2026-08-20", "receipt_method": "bank_transfer"})
        receipt = service.submit_receipt(cashier, receipt["id"], {"expected_version": receipt["version"]})
        receipt = service.update_receipt(finance_editor, receipt["id"], {"expected_version": receipt["version"], "note": "补录银行摘要"})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_type='sales:receipt',entity_id=%s WHERE id=%s", (receipt["id"], ids["attachment_2"]))
        receipt = service.verify_receipt(checker, receipt["id"], {"expected_version": receipt["version"], "evidence_attachment_ids": [ids["attachment_2"]]})
        with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
            service.reverse_receipt(finance_editor, receipt["id"], {"expected_version": receipt["version"], "reversal_reason": "历史经办人冲销", "evidence_attachment_ids": [ids["attachment_3"]]})
        assert one(settings, "SELECT received_amount,status FROM sales_receivables WHERE id=%s", (receivable["id"],)) == {"received_amount": Decimal("400.00"), "status": "partial"}
        final = service.create_receipt(cashier, {"code": "RC-REAL-2", "name": "客户尾款", "receivable_id": receivable["id"], "amount": 510, "received_at": "2026-08-21", "receipt_method": "bank_transfer"})
        final = service.submit_receipt(cashier, final["id"], {"expected_version": final["version"]})
        competing = service.create_receipt(cashier, {"code": "RC-REAL-3", "name": "并发尾款", "receivable_id": receivable["id"], "amount": 510, "received_at": "2026-08-21", "receipt_method": "bank_transfer"})
        competing = service.submit_receipt(cashier, competing["id"], {"expected_version": competing["version"]})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_type='sales:receipt',entity_id=%s WHERE id=%s", (final["id"], ids["attachment_5"]))
            cursor.execute("UPDATE attachments SET entity_type='sales:receipt',entity_id=%s WHERE id=%s", (competing["id"], ids["attachment_6"]))
        final = service.verify_receipt(checker, final["id"], {"expected_version": final["version"], "evidence_attachment_ids": [ids["attachment_5"]]})
        with pytest.raises(DomainError, match="RECEIPT_EXCEEDS_BALANCE"):
            service.verify_receipt(checker, competing["id"], {"expected_version": competing["version"], "evidence_attachment_ids": [ids["attachment_6"]]})
        assert one(settings, "SELECT received_amount,status FROM sales_receivables WHERE id=%s", (receivable["id"],)) == {"received_amount": Decimal("910.00"), "status": "settled"}
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_type='sales:receipt_reversal',entity_id=%s WHERE id=%s", (final["id"], ids["attachment_3"]))
        service.reverse_receipt(checker, final["id"], {"expected_version": final["version"], "reversal_reason": "银行退回", "evidence_attachment_ids": [ids["attachment_3"]]})
        assert one(settings, "SELECT received_amount,status FROM sales_receivables WHERE id=%s", (receivable["id"],)) == {"received_amount": Decimal("400.00"), "status": "partial"}
        summary = service.list_receivables(checker)["summary"]
        assert summary == {"total_amount": Decimal("910.00"), "total_balance": Decimal("510.00"), "overpaid_amount": Decimal("0.00"), "overdue_count": 0}
        with pytest.raises(pymysql.OperationalError, match="formal sales order"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("DELETE FROM sales_orders WHERE id=%s", (order["id"],))
        with pytest.raises(pymysql.OperationalError, match="immutable"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE sales_receipts SET amount=1 WHERE id=%s", (receipt["id"],))
        with pytest.raises(pymysql.OperationalError, match="immutable"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE sales_orders SET species='草鱼' WHERE id=%s", (order["id"],))


def test_sales_hardening_rejects_duplicate_legacy_roots_before_permanent_ddl() -> None:
    with disposable_database("adp_sales_upgrade_test", through=13) as database:
        settings = settings_for(database); ids = seed(settings)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,quantity,weight_kg,happened_at,correction_of_id,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'harvest','SH1-C','更正出塘',%s,%s,35,35,'2026-08-18',%s,'verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["batch_id"], ids["pond_id"], ids["harvest_id"]))
            corrected_harvest = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_orders (organization_id,farm_id,area_id,pond_id,batch_id,customer_id,code,name,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,'SO-OLD','旧销售','鲈鱼',75,'kg',20,1500,'2026-08-17','2026-09-17','approved',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["pond_id"], ids["batch_id"], ids["customer_id"]))
            order_id = int(cursor.lastrowid)
            cursor.executemany("INSERT INTO sales_deliveries (organization_id,sales_order_id,harvest_document_id,code,name,quantity,delivered_at,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,'2026-08-18','submitted',1)", [(ids["organization_id"], order_id, ids["harvest_id"], "SD-OLD-1", "原出塘交付", 40), (ids["organization_id"], order_id, corrected_harvest, "SD-OLD-2", "更正出塘重复交付", 35)])
        with pytest.raises(AssertionError, match="Duplicate entry"):
            run_mysql(f"--database={database}", sql=(ROOT / "database/migrations/014_sales_hardening.sql").read_bytes())
        assert one(settings, "SELECT COUNT(*) AS total FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='sales_deliveries' AND column_name='harvest_root_id'")["total"] == 0
        assert one(settings, "SELECT COUNT(*) AS total FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='sales_delivery_harvest_claims'")["total"] == 0


def test_sales_hardening_upgrades_a_verified_legacy_delivery() -> None:
    with disposable_database("adp_sales_verified_upgrade", through=13) as database:
        settings = settings_for(database); ids = seed(settings)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO sales_orders (organization_id,farm_id,area_id,pond_id,batch_id,customer_id,code,name,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,'SO-VERIFIED','旧销售','鲈鱼',40,'kg',20,800,'2026-08-17','2026-09-17','approved',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["pond_id"], ids["batch_id"], ids["customer_id"]))
            order_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_deliveries (organization_id,sales_order_id,harvest_document_id,code,name,quantity,delivered_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'SD-VERIFIED','已核验旧交付',40,'2026-08-18','verified',1,2,NOW())", (ids["organization_id"], order_id, ids["harvest_id"]))
            delivery_id = int(cursor.lastrowid)
        run_mysql(f"--database={database}", sql=(ROOT / "database/migrations/014_sales_hardening.sql").read_bytes())
        assert one(settings, "SELECT harvest_root_id FROM sales_deliveries WHERE id=%s", (delivery_id,))["harvest_root_id"] == ids["harvest_id"]
        with pytest.raises(pymysql.OperationalError, match="immutable"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE sales_deliveries SET quantity=1 WHERE id=%s", (delivery_id,))


def test_receivable_summary_keeps_overpayments_out_of_unpaid_balance() -> None:
    with disposable_database("adp_sales_overpayment", through=14) as database:
        settings = settings_for(database); ids = seed(settings); store = MySqlSalesStore(settings)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO sales_orders (organization_id,farm_id,area_id,pond_id,batch_id,customer_id,code,name,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,'SO-A','多收销售','鲈鱼',10,'kg',10,100,'2026-08-17','2026-09-17','approved',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["pond_id"], ids["batch_id"], ids["customer_id"]))
            first_order = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_orders (organization_id,farm_id,area_id,pond_id,batch_id,customer_id,code,name,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,'SO-B','未收销售','鲈鱼',20,'kg',10,200,'2026-08-17','2026-09-17','approved',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["pond_id"], ids["batch_id"], ids["customer_id"]))
            second_order = int(cursor.lastrowid)
            cursor.execute("INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,quantity,weight_kg,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'harvest','SH-B','第二应收出塘',%s,%s,20,20,'2026-08-18','verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["batch_id"], ids["pond_id"]))
            second_harvest = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_deliveries (organization_id,sales_order_id,harvest_document_id,harvest_root_id,code,name,quantity,delivered_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,%s,'SD-A','多收交付',10,'2026-08-18','verified',1,2,NOW())", (ids["organization_id"], first_order, ids["harvest_id"], ids["harvest_id"]))
            first_delivery = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_deliveries (organization_id,sales_order_id,harvest_document_id,harvest_root_id,code,name,quantity,delivered_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,%s,'SD-B','未收交付',20,'2026-08-18','verified',1,2,NOW())", (ids["organization_id"], second_order, second_harvest, second_harvest))
            second_delivery = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_receivables (organization_id,sales_order_id,source_delivery_id,customer_id,idempotency_key,amount,received_amount,due_date,status) VALUES (%s,%s,%s,%s,'A',100,130,'2026-09-17','overpaid')", (ids["organization_id"], first_order, first_delivery, ids["customer_id"]))
            cursor.execute("INSERT INTO sales_receivables (organization_id,sales_order_id,source_delivery_id,customer_id,idempotency_key,amount,received_amount,due_date,status) VALUES (%s,%s,%s,%s,'B',200,0,'2026-09-17','unpaid')", (ids["organization_id"], second_order, second_delivery, ids["customer_id"]))
        summary = store.list_receivables(user=actor(4, "finance.receivable.view"))["summary"]
        assert summary["total_balance"] == Decimal("200.00")
        assert summary["overpaid_amount"] == Decimal("30.00")


def test_sales_hardening_rejects_cross_line_legacy_correction_before_permanent_ddl() -> None:
    with disposable_database("adp_sales_lineage_test", through=13) as database:
        settings = settings_for(database); ids = seed(settings)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,quantity,weight_kg,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'harvest','SH-OTHER','另一出塘链',%s,%s,40,40,'2026-08-18','verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["batch_id"], ids["pond_id"]))
            other_harvest = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_orders (organization_id,farm_id,area_id,pond_id,batch_id,customer_id,code,name,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,'SO-LINE','旧销售','鲈鱼',80,'kg',20,1600,'2026-08-17','2026-09-17','approved',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["pond_id"], ids["batch_id"], ids["customer_id"]))
            order_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_deliveries (organization_id,sales_order_id,harvest_document_id,code,name,quantity,delivered_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'SD-LINE-1','原交付',40,'2026-08-18','verified',1,2,NOW())", (ids["organization_id"], order_id, ids["harvest_id"]))
            parent_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_deliveries (organization_id,sales_order_id,harvest_document_id,code,name,quantity,delivered_at,correction_of_id,correction_reason,status,created_by) VALUES (%s,%s,%s,'SD-LINE-2','跨链更正',40,'2026-08-18',%s,'旧数据错误','draft',1)", (ids["organization_id"], order_id, other_harvest, parent_id))
        with pytest.raises(AssertionError):
            run_mysql(f"--database={database}", sql=(ROOT / "database/migrations/014_sales_hardening.sql").read_bytes())
        assert one(settings, "SELECT COUNT(*) AS total FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='sales_deliveries' AND column_name='harvest_root_id'")["total"] == 0
