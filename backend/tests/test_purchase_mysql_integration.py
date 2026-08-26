from __future__ import annotations

from decimal import Decimal
from typing import Any

import pymysql
import pytest

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.purchase.purchase_service import PurchaseService
from backend.layers.features.purchase.purchase_store import MySqlPurchaseStore
from backend.layers.features.warehouse.warehouse_service import WarehouseService
from backend.layers.features.warehouse.warehouse_store import MySqlWarehouseStore
from backend.tests.mysql_test_database import disposable_database, settings_for


def _seed(settings: Any) -> dict[str, int]:
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO users (phone,name,password_hash,status) VALUES (%s,%s,'hash','active')",
            [("13920000001", "采购经办"), ("13920000002", "采购审批"), ("13920000003", "仓储财务经办"), ("13920000004", "付款核验")],
        )
        cursor.execute("SELECT id AS organization_id FROM organizations WHERE code='default'")
        ids = dict(cursor.fetchone())
        cursor.execute("SELECT id AS farm_id FROM farms WHERE code='default-farm'")
        ids.update(cursor.fetchone())
        cursor.execute(
            "INSERT INTO areas (organization_id,farm_id,code,name,status,created_by) VALUES (%s,%s,'PA','采购区','verified',1)",
            (ids["organization_id"], ids["farm_id"]),
        )
        ids["area_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO business_partners (organization_id,farm_id,area_id,partner_type,code,name,settlement_days,status,created_by) VALUES (%s,%s,%s,'supplier','S1','饲料供应商',30,'verified',1)",
            (ids["organization_id"], ids["farm_id"], ids["area_id"]),
        )
        ids["supplier_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO materials (organization_id,farm_id,area_id,code,name,unit,status,created_by) VALUES (%s,%s,%s,'PM1','采购饲料','kg','verified',1)",
            (ids["organization_id"], ids["farm_id"], ids["area_id"]),
        )
        ids["material_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO materials (organization_id,farm_id,area_id,code,name,unit,status,created_by) VALUES (%s,%s,%s,'PM2','其他物料','kg','verified',1)",
            (ids["organization_id"], ids["farm_id"], ids["area_id"]),
        )
        ids["other_material_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO warehouses (organization_id,farm_id,area_id,code,name) VALUES (%s,%s,%s,'PW1','采购收货仓')",
            (ids["organization_id"], ids["farm_id"], ids["area_id"]),
        )
        ids["warehouse_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO warehouses (organization_id,farm_id,area_id,code,name) VALUES (%s,%s,%s,'PW2','其他仓库')",
            (ids["organization_id"], ids["farm_id"], ids["area_id"]),
        )
        ids["other_warehouse_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,'purchase_test',1,%s,%s,'voucher.pdf','application/pdf',12,3)",
            (ids["organization_id"], "c" * 64, "d" * 32),
        )
        ids["attachment_id"] = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,'purchase_test',1,%s,%s,'reversal.pdf','application/pdf',12,2)",
            (ids["organization_id"], "e" * 64, "f" * 32),
        )
        ids["reversal_attachment_id"] = int(cursor.lastrowid)
    return ids


def _actor(user_id: int, *permissions: str) -> dict[str, Any]:
    return {"id": user_id, "permissions": list(permissions), "data_scopes": []}


def _one(settings: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return dict(cursor.fetchone())


def test_real_mysql_purchase_receipt_payable_and_payment_chain() -> None:
    with disposable_database("adp_purchase_test", through=12) as database:
        settings = settings_for(database)
        ids = _seed(settings)
        purchase = PurchaseService(MySqlPurchaseStore(settings))
        warehouse = WarehouseService(MySqlWarehouseStore(settings))
        purchaser = _actor(1, "purchase.view", "purchase.manage")
        approver = _actor(2, "purchase.view", "purchase.verify", "finance.payable.view", "warehouse.view", "warehouse.verify")
        warehouse_maker = _actor(3, "warehouse.view", "warehouse.manage", "finance.payable.view", "finance.payment.manage")
        finance_checker = _actor(4, "finance.payable.view", "finance.payment.verify")

        order = purchase.create_order(purchaser, {
            "code": "PO-REAL-1", "name": "真实饲料采购", "supplier_id": ids["supplier_id"],
            "material_id": ids["material_id"], "warehouse_id": ids["warehouse_id"],
            "quantity": 100, "unit_price": 5, "expected_delivery_date": "2026-08-25", "due_date": "2026-09-25",
        })
        order = purchase.submit_order(purchaser, order["id"], {"expected_version": order["version"]})
        assert _one(settings, "SELECT status FROM work_items WHERE source_key=%s", (f"purchase:order:{order['id']}:approve",))["status"] == "pending"
        outside_approver = _actor(2, "purchase.view", "purchase.verify")
        outside_approver["data_scopes"] = [{"scope_type": "area", "area_id": ids["area_id"] + 999}]
        with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
            purchase.approve_order(outside_approver, order["id"], {"expected_version": order["version"]})
        order = purchase.approve_order(approver, order["id"], {"expected_version": order["version"]})
        assert _one(settings, "SELECT status FROM work_items WHERE source_key=%s", (f"purchase:order:{order['id']}:approve",))["status"] == "completed"
        assert _one(settings, "SELECT COUNT(*) AS total FROM inventory_ledger")["total"] == 0
        assert _one(settings, "SELECT COUNT(*) AS total FROM purchase_payables")["total"] == 0

        receipt = warehouse.create(warehouse_maker, "receipts", {
            "code": "PIN-1", "name": "采购部分到货", "warehouse_id": ids["warehouse_id"],
            "material_id": ids["material_id"], "purchase_order_id": order["id"], "quantity": 40,
            "unit_cost": 5, "lot_no": "PLOT-1", "expiry_date": "2027-08-01",
        })
        receipt = warehouse.submit(warehouse_maker, "receipts", receipt["id"], {"expected_version": receipt["version"]})
        with pytest.raises(DomainError, match="EVIDENCE_INVALID"):
            warehouse.verify(approver, "receipts", receipt["id"], {
                "expected_version": receipt["version"], "evidence_attachment_ids": [ids["attachment_id"]],
            })
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_type='warehouse:receipts',entity_id=%s WHERE id=%s", (receipt["id"], ids["attachment_id"]))
        receipt = warehouse.verify(approver, "receipts", receipt["id"], {"expected_version": receipt["version"], "evidence_attachment_ids": [ids["attachment_id"]]})
        posted = _one(settings, "SELECT status,(SELECT SUM(quantity_delta) FROM inventory_ledger) AS stock,(SELECT COUNT(*) FROM purchase_payables) AS payables FROM purchase_orders WHERE id=%s", (order["id"],))
        assert posted == {"status": "partially_received", "stock": Decimal("40.000"), "payables": 1}
        payable = _one(settings, "SELECT id,amount,paid_amount,status,idempotency_key FROM purchase_payables WHERE source_receipt_id=%s", (receipt["id"],))
        assert payable["amount"] == Decimal("200.00")
        assert payable["idempotency_key"] == f"purchase-receipt:{receipt['id']}"
        outside_finance = _actor(3, "finance.payable.view", "finance.payment.manage")
        outside_finance["data_scopes"] = [{"scope_type": "area", "area_id": ids["area_id"] + 999}]
        with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
            purchase.create_payment(outside_finance, {
                "code": "PAY-OUTSIDE", "name": "越权付款", "payable_id": payable["id"], "amount": 1, "paid_at": "2026-08-17", "payment_method": "bank_transfer",
            })
        correction = warehouse.correct(warehouse_maker, "receipts", receipt["id"], {
            "expected_version": receipt["version"], "code": "PIN-1-C", "quantity": 30,
            "correction_reason": "实际验收数量复核为 30",
        })
        correction = warehouse.submit(warehouse_maker, "receipts", correction["id"], {"expected_version": correction["version"]})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_id=%s WHERE id=%s", (correction["id"], ids["attachment_id"]))
        correction = warehouse.verify(approver, "receipts", correction["id"], {
            "expected_version": correction["version"], "evidence_attachment_ids": [ids["attachment_id"]],
        })
        assert _one(settings, "SELECT SUM(quantity_delta) AS stock FROM inventory_ledger")["stock"] == Decimal("30.000")
        assert _one(settings, "SELECT status FROM purchase_orders WHERE id=%s", (order["id"],))["status"] == "partially_received"
        assert _one(settings, "SELECT amount_delta FROM purchase_payable_adjustments WHERE source_receipt_id=%s", (correction["id"],))["amount_delta"] == Decimal("-50.00")
        assert purchase.list_orders(approver)["items"][0]["received_quantity"] == Decimal("30.000")
        correction2 = warehouse.correct(warehouse_maker, "receipts", correction["id"], {
            "expected_version": correction["version"], "code": "PIN-1-C2", "quantity": 35,
            "correction_reason": "复核后确认到货 35",
        })
        correction2 = warehouse.submit(warehouse_maker, "receipts", correction2["id"], {"expected_version": correction2["version"]})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_id=%s WHERE id=%s", (correction2["id"], ids["attachment_id"]))
        warehouse.verify(approver, "receipts", correction2["id"], {"expected_version": correction2["version"], "evidence_attachment_ids": [ids["attachment_id"]]})
        assert _one(settings, "SELECT SUM(amount_delta) AS delta FROM purchase_payable_adjustments WHERE payable_id=%s", (payable["id"],))["delta"] == Decimal("-25.00")
        assert purchase.list_orders(approver)["items"][0]["received_quantity"] == Decimal("35.000")
        posted_counts = _one(settings, "SELECT (SELECT COUNT(*) FROM inventory_ledger) AS ledger,(SELECT COUNT(*) FROM purchase_payables) AS payables")
        with pytest.raises(DomainError):
            warehouse.verify(approver, "receipts", receipt["id"], {
                "expected_version": receipt["version"], "evidence_attachment_ids": [ids["attachment_id"]],
            })
        assert _one(settings, "SELECT (SELECT COUNT(*) FROM inventory_ledger) AS ledger,(SELECT COUNT(*) FROM purchase_payables) AS payables") == posted_counts
        with pytest.raises(DomainError):
            purchase.cancel_order(approver, order["id"], {
                "expected_version": order["version"], "cancellation_reason": "已有到货后误取消",
            })
        assert _one(settings, "SELECT status FROM purchase_orders WHERE id=%s", (order["id"],))["status"] == "partially_received"

        mismatch_cases = [
            ("PRICE", {"unit_cost": 6}, "PURCHASE_RECEIPT_PRICE_MISMATCH"),
            ("MATERIAL", {"material_id": ids["other_material_id"]}, "PURCHASE_RECEIPT_SCOPE_MISMATCH"),
            ("WAREHOUSE", {"warehouse_id": ids["other_warehouse_id"]}, "PURCHASE_RECEIPT_SCOPE_MISMATCH"),
            ("QUANTITY", {"quantity": 71}, "PURCHASE_RECEIPT_EXCEEDS_ORDER"),
        ]
        for suffix, overrides, error_code in mismatch_cases:
            bad_receipt = warehouse.create(warehouse_maker, "receipts", {
                "code": f"PIN-{suffix}", "name": f"{suffix} 不符到货", "warehouse_id": ids["warehouse_id"],
                "material_id": ids["material_id"], "purchase_order_id": order["id"], "quantity": 10,
                "unit_cost": 5, "lot_no": f"PLOT-{suffix}", **overrides,
            })
            bad_receipt = warehouse.submit(warehouse_maker, "receipts", bad_receipt["id"], {"expected_version": bad_receipt["version"]})
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE attachments SET entity_id=%s WHERE id=%s", (bad_receipt["id"], ids["attachment_id"]))
            with pytest.raises(DomainError, match=error_code):
                warehouse.verify(approver, "receipts", bad_receipt["id"], {
                    "expected_version": bad_receipt["version"], "evidence_attachment_ids": [ids["attachment_id"]],
                })
            assert warehouse.get(approver, "receipts", bad_receipt["id"])["status"] == "submitted"
            assert _one(settings, "SELECT (SELECT COUNT(*) FROM inventory_ledger) AS ledger,(SELECT COUNT(*) FROM purchase_payables) AS payables") == posted_counts

        final_receipt = warehouse.create(warehouse_maker, "receipts", {
            "code": "PIN-2", "name": "采购剩余到货", "warehouse_id": ids["warehouse_id"],
            "material_id": ids["material_id"], "purchase_order_id": order["id"], "quantity": 65,
            "unit_cost": 5, "lot_no": "PLOT-2",
        })
        final_receipt = warehouse.submit(warehouse_maker, "receipts", final_receipt["id"], {"expected_version": final_receipt["version"]})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_id=%s WHERE id=%s", (final_receipt["id"], ids["attachment_id"]))
        warehouse.verify(approver, "receipts", final_receipt["id"], {
            "expected_version": final_receipt["version"], "evidence_attachment_ids": [ids["attachment_id"]],
        })
        assert _one(settings, "SELECT status FROM purchase_orders WHERE id=%s", (order["id"],))["status"] == "fully_received"
        assert _one(settings, "SELECT COUNT(*) AS total FROM purchase_payables")["total"] == 2

        payment = purchase.create_payment(warehouse_maker, {
            "code": "PAY-REAL-1", "name": "首笔付款", "payable_id": payable["id"], "amount": 80, "paid_at": "2026-08-17", "payment_method": "bank_transfer",
        })
        payment = purchase.submit_payment(warehouse_maker, payment["id"], {"expected_version": payment["version"]})
        assert _one(settings, "SELECT status FROM work_items WHERE source_key=%s", (f"purchase:payment:{payment['id']}:verify",))["status"] == "pending"
        with pytest.raises(DomainError, match="EVIDENCE_REQUIRED"):
            purchase.verify_payment(finance_checker, payment["id"], {"expected_version": payment["version"]})
        with pytest.raises(DomainError, match="EVIDENCE_INVALID"):
            purchase.verify_payment(finance_checker, payment["id"], {
                "expected_version": payment["version"], "evidence_attachment_ids": [ids["attachment_id"]],
            })
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_type='purchase:payment',entity_id=%s WHERE id=%s", (payment["id"], ids["attachment_id"]))
        with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
            purchase.verify_payment(_actor(3, "finance.payment.verify"), payment["id"], {
                "expected_version": payment["version"], "evidence_attachment_ids": [ids["attachment_id"]],
            })
        purchase.verify_payment(finance_checker, payment["id"], {
            "expected_version": payment["version"], "evidence_attachment_ids": [ids["attachment_id"]],
        })
        assert _one(settings, "SELECT status FROM work_items WHERE source_key=%s", (f"purchase:payment:{payment['id']}:verify",))["status"] == "completed"
        assert _one(settings, "SELECT paid_amount,amount+COALESCE((SELECT SUM(amount_delta) FROM purchase_payable_adjustments WHERE payable_id=purchase_payables.id),0)-paid_amount AS balance,status FROM purchase_payables WHERE id=%s", (payable["id"],)) == {
            "paid_amount": Decimal("80.00"), "balance": Decimal("95.00"), "status": "partial",
        }
        payment = purchase.create_payment(warehouse_maker, {
            "code": "PAY-REAL-2", "name": "结清付款", "payable_id": payable["id"], "amount": 95, "paid_at": "2026-08-18", "payment_method": "bank_transfer",
        })
        payment = purchase.submit_payment(warehouse_maker, payment["id"], {"expected_version": payment["version"]})
        competing = purchase.create_payment(warehouse_maker, {
            "code": "PAY-REAL-3", "name": "并发付款", "payable_id": payable["id"], "amount": 95, "paid_at": "2026-08-18", "payment_method": "bank_transfer",
        })
        competing = purchase.submit_payment(warehouse_maker, competing["id"], {"expected_version": competing["version"]})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,'purchase:payment',%s,%s,%s,'payment-2.pdf','application/pdf',12,3)", (ids["organization_id"], payment["id"], "1" * 64, "2" * 32))
            payment_attachment_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,'purchase:payment',%s,%s,%s,'payment-3.pdf','application/pdf',12,3)", (ids["organization_id"], competing["id"], "3" * 64, "4" * 32))
            competing_attachment_id = int(cursor.lastrowid)
        payment = purchase.verify_payment(finance_checker, payment["id"], {
            "expected_version": payment["version"], "evidence_attachment_ids": [payment_attachment_id],
        })
        assert _one(settings, "SELECT paid_amount,status FROM purchase_payables WHERE id=%s", (payable["id"],)) == {"paid_amount": Decimal("175.00"), "status": "settled"}
        with pytest.raises(DomainError, match="PAYMENT_EXCEEDS_BALANCE"):
            purchase.verify_payment(finance_checker, competing["id"], {
                "expected_version": competing["version"], "evidence_attachment_ids": [competing_attachment_id],
            })
        assert _one(settings, "SELECT status,row_version FROM purchase_payments WHERE id=%s", (competing["id"],)) == {"status": "submitted", "row_version": competing["version"]}
        assert _one(settings, "SELECT status FROM work_items WHERE source_key=%s", (f"purchase:payment:{competing['id']}:verify",))["status"] == "pending"
        assert _one(settings, "SELECT paid_amount,status FROM purchase_payables WHERE id=%s", (payable["id"],)) == {"paid_amount": Decimal("175.00"), "status": "settled"}

        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_type='purchase:payment_reversal',entity_id=%s WHERE id=%s", (payment["id"], ids["reversal_attachment_id"]))
        reversal = purchase.reverse_payment(_actor(2, "finance.payment.verify"), payment["id"], {
            "expected_version": payment["version"], "reversal_reason": "原付款银行退回",
            "evidence_attachment_ids": [ids["reversal_attachment_id"]],
        })
        assert reversal["reversal_id"] and reversal["amount"] == Decimal("95.00")
        assert _one(settings, "SELECT paid_amount,status FROM purchase_payables WHERE id=%s", (payable["id"],)) == {"paid_amount": Decimal("80.00"), "status": "partial"}

        with pytest.raises(pymysql.OperationalError, match="formal purchase order"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("DELETE FROM purchase_orders WHERE id=%s", (order["id"],))
        with pytest.raises(pymysql.OperationalError, match="immutable"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE purchase_payments SET amount=1 WHERE code='PAY-REAL-1'")
