from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any


PREFIX = "TEST-20260817"
VOUCHER = b"ADP manual test voucher 2026-08-17\n"


def _new(cursor: Any, sql: str, params: tuple[object, ...]) -> int:
    cursor.execute(sql, params)
    return int(cursor.lastrowid)


def _context(cursor: Any) -> dict[str, int]:
    queries = {
        "org": "SELECT id FROM organizations WHERE code='TEST-20260817-ORG'",
        "farm": "SELECT id FROM farms WHERE code='TEST-20260817-FARM'",
        "area": "SELECT id FROM areas WHERE code='TEST-20260817-AREA-EAST'",
        "pond": "SELECT id FROM ponds WHERE code='TEST-20260817-POND-01'",
        "material": "SELECT id FROM materials WHERE code='TEST-20260817-MAT-FEED'",
        "supplier": "SELECT id FROM business_partners WHERE code='TEST-20260817-SUPPLIER'",
        "customer": "SELECT id FROM business_partners WHERE code='TEST-20260817-CUSTOMER'",
        "warehouse": "SELECT id FROM warehouses WHERE code='TEST-20260817-WAREHOUSE'",
        "category": "SELECT id FROM cost_categories WHERE code='other'",
        "rule": "SELECT id FROM cost_allocation_rule_versions WHERE status='active' ORDER BY version_no DESC LIMIT 1",
    }
    result: dict[str, int] = {}
    for name, sql in queries.items():
        cursor.execute(sql)
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(f"Required manual test master data not found: {name}")
        result[name] = int(row["id"])
    cursor.execute("SELECT id,login_name FROM users WHERE login_name LIKE 'test-%'")
    result.update({str(row["login_name"]): int(row["id"]) for row in cursor.fetchall()})
    return result


def _attachment(cursor: Any, ids: dict[str, int], entity_type: str, entity_id: int, index: int) -> int:
    directory_text = os.environ.get("ADP_MANUAL_TEST_ATTACHMENT_DIR", "").strip()
    if not directory_text:
        raise RuntimeError("Missing required environment variable: ADP_MANUAL_TEST_ATTACHMENT_DIR")
    directory = Path(directory_text)
    directory.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256(VOUCHER).hexdigest()
    storage_name = f"{sha256[:24]}{index:08d}"
    path = directory / storage_name
    if not path.exists():
        path.write_bytes(VOUCHER)
    return _new(
        cursor,
        "INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,%s,%s,%s,%s,'manual-test-voucher.txt','text/plain',%s,%s)",
        (ids["org"], entity_type, entity_id, sha256, storage_name, len(VOUCHER), ids["test-finance"]),
    )


def _production(cursor: Any, ids: dict[str, int]) -> dict[str, int]:
    batch = _new(cursor,
        "INSERT INTO production_batches (organization_id,farm_id,area_id,pond_id,code,name,species,initial_quantity,initial_weight_kg,stocked_at,batch_status,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,%s,%s,%s,'草鱼',1000,1000,'2026-08-01 08:00:00','farming','verified',%s,%s,NOW())",
        (ids["org"], ids["farm"], ids["area"], ids["pond"], f"{PREFIX}-BATCH-01", "[测试]草鱼养殖批次", ids["test-breed-worker"], ids["test-breed-manager"]))
    cursor.execute("INSERT INTO batch_stock_records (organization_id,batch_id,pond_id,source_type,source_id,line_no,quantity_delta,weight_delta_kg,happened_at,posted_by) VALUES (%s,%s,%s,'stocking',%s,1,1000,1000,'2026-08-01 08:00:00',%s)", (ids["org"], batch, ids["pond"], batch, ids["test-breed-manager"]))
    base = (ids["org"], ids["farm"], ids["area"], batch, ids["pond"])
    _new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,happened_at,status,created_by) VALUES (%s,%s,%s,'daily_operation',%s,%s,%s,%s,'2026-08-10 08:00:00','draft',%s)", (*base[:3], f"{PREFIX}-PROD-DRAFT", "[测试]巡塘草稿", *base[3:], ids["test-breed-worker"]))
    submitted = _new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,happened_at,status,created_by) VALUES (%s,%s,%s,'sampling',%s,%s,%s,%s,'2026-08-11 08:00:00','submitted',%s)", (*base[:3], f"{PREFIX}-PROD-SUBMITTED", "[测试]抽样待核验", *base[3:], ids["test-breed-worker"]))
    verified = _new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'daily_operation',%s,%s,%s,%s,'2026-08-12 08:00:00','verified',%s,%s,NOW())", (*base[:3], f"{PREFIX}-PROD-VERIFIED", "[测试]已核验巡塘", *base[3:], ids["test-breed-worker"], ids["test-breed-manager"]))
    _new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,happened_at,correction_of_id,note,status,created_by) VALUES (%s,%s,%s,'correction',%s,%s,%s,%s,'2026-08-12 09:00:00',%s,'更正巡塘备注','draft',%s)", (*base[:3], f"{PREFIX}-PROD-CORRECTION", "[测试]巡塘更正草稿", *base[3:], verified, ids["test-breed-worker"]))
    harvest = _new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,quantity,weight_kg,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'harvest',%s,%s,%s,%s,100,100,'2026-08-13 08:00:00','verified',%s,%s,NOW())", (*base[:3], f"{PREFIX}-HARVEST-01", "[测试]草鱼出塘", *base[3:], ids["test-breed-worker"], ids["test-breed-manager"]))
    cursor.execute("INSERT INTO batch_stock_records (organization_id,batch_id,pond_id,source_type,source_id,line_no,quantity_delta,weight_delta_kg,happened_at,posted_by) VALUES (%s,%s,%s,'harvest',%s,1,-100,-100,'2026-08-13 08:00:00',%s)", (ids["org"], batch, ids["pond"], harvest, ids["test-breed-manager"]))
    return {"batch": batch, "submitted": submitted, "verified": verified, "harvest": harvest}


def _purchase_and_warehouse(cursor: Any, ids: dict[str, int]) -> dict[str, int]:
    common = (ids["org"], ids["farm"], ids["area"], ids["supplier"], ids["material"], ids["warehouse"])
    for suffix, status in (("DRAFT", "draft"), ("SUBMITTED", "submitted")):
        _new(cursor, "INSERT INTO purchase_orders (organization_id,farm_id,area_id,supplier_id,material_id,warehouse_id,code,name,quantity,unit_price,total_amount,due_date,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,100,10,1000,'2026-09-30',%s,%s)", (*common, f"{PREFIX}-PO-{suffix}", f"[测试]采购单{suffix}", status, ids["test-purchaser"]))
    _new(cursor, "INSERT INTO purchase_orders (organization_id,farm_id,area_id,supplier_id,material_id,warehouse_id,code,name,quantity,unit_price,total_amount,due_date,status,created_by,approved_by,approved_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,100,10,1000,'2026-09-30','approved',%s,%s,NOW())", (*common, f"{PREFIX}-PO-APPROVED", "[测试]已审批采购单", ids["test-purchaser"], ids["test-finance"]))
    order = _new(cursor, "INSERT INTO purchase_orders (organization_id,farm_id,area_id,supplier_id,material_id,warehouse_id,code,name,quantity,unit_price,total_amount,due_date,status,created_by,approved_by,approved_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,100,10,1000,'2026-09-30','fully_received',%s,%s,NOW())", (*common, f"{PREFIX}-PO-FULFILL", "[测试]全量到货采购单", ids["test-purchaser"], ids["test-finance"]))
    lot = _new(cursor, "INSERT INTO inventory_lots (organization_id,material_id,supplier_id,lot_no,production_date,expiry_date,unit_cost,status) VALUES (%s,%s,%s,%s,'2026-08-01','2027-08-01',10,'available')", (ids["org"], ids["material"], ids["supplier"], f"{PREFIX}-LOT-01"))
    receipt = _new(cursor, "INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,material_id,inventory_lot_id,purchase_order_id,quantity,unit_cost,lot_no,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'receipt',%s,%s,%s,%s,%s,%s,100,10,%s,'2026-08-14 08:00:00','verified',%s,%s,NOW())", (ids["org"], ids["farm"], ids["area"], f"{PREFIX}-WH-RECEIPT", "[测试]采购入库", ids["warehouse"], ids["material"], lot, order, f"{PREFIX}-LOT-01", ids["test-warehouse"], ids["test-breed-manager"]))
    cursor.execute("INSERT INTO inventory_ledger (organization_id,warehouse_id,material_id,inventory_lot_id,source_type,source_id,line_no,quantity_delta,unit_cost,happened_at,posted_by) VALUES (%s,%s,%s,%s,'receipt',%s,1,100,10,'2026-08-14 08:00:00',%s)", (ids["org"], ids["warehouse"], ids["material"], lot, receipt, ids["test-warehouse"]))
    for suffix, doc_type, status in (("DRAFT", "issue_request", "draft"), ("SUBMITTED", "return", "submitted")):
        _new(cursor, "INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,material_id,inventory_lot_id,quantity,unit_cost,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,10,10,%s,%s)", (ids["org"], ids["farm"], ids["area"], doc_type, f"{PREFIX}-WH-{suffix}", f"[测试]仓储单{suffix}", ids["warehouse"], ids["material"], lot, status, ids["test-warehouse"]))
    payable = _new(cursor, "INSERT INTO purchase_payables (organization_id,purchase_order_id,source_receipt_id,supplier_id,idempotency_key,amount,paid_amount,due_date,status) VALUES (%s,%s,%s,%s,%s,1000,400,'2026-09-30','partial')", (ids["org"], order, receipt, ids["supplier"], f"{PREFIX}-PAYABLE-01"))
    for index, (code, amount, reverse) in enumerate((("PAYMENT-01", 400, False), ("PAYMENT-REV", 100, True)), 1):
        payment = _new(cursor, "INSERT INTO purchase_payments (organization_id,payable_id,code,name,amount,paid_at,payment_method,status,created_by) VALUES (%s,%s,%s,%s,%s,'2026-08-15','bank_transfer','draft',%s)", (ids["org"], payable, f"{PREFIX}-{code}", f"[测试]{code}", amount, ids["test-finance"]))
        evidence = _attachment(cursor, ids, "purchase:payment", payment, index)
        cursor.execute("UPDATE purchase_payments SET status='verified',verified_by=%s,verified_at=NOW(),evidence_attachment_ids_json=JSON_ARRAY(%s) WHERE id=%s", (ids["test-admin"], evidence, payment))
        if reverse:
            cursor.execute("INSERT INTO purchase_payment_reversals (organization_id,payment_id,amount,reversal_reason,evidence_attachment_ids_json,created_by) VALUES (%s,%s,%s,'银行退回',JSON_ARRAY(%s),%s)", (ids["org"], payment, amount, evidence, ids["test-admin"]))
    return {"order": order, "receipt": receipt}


def _sales(cursor: Any, ids: dict[str, int], production: dict[str, int]) -> None:
    common = (ids["org"], ids["farm"], ids["area"], ids["pond"], production["batch"], ids["customer"])
    for suffix, status in (("DRAFT", "draft"), ("SUBMITTED", "submitted"), ("APPROVED", "approved")):
        approval = (ids["test-finance"],) if status == "approved" else (None,)
        _new(cursor, "INSERT INTO sales_orders (organization_id,farm_id,area_id,pond_id,batch_id,customer_id,code,name,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,created_by,approved_by,approved_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'草鱼',100,'kg',20,2000,'2026-08-16','2026-09-30',%s,%s,%s,IF(%s IS NULL,NULL,NOW()))", (*common, f"{PREFIX}-SO-{suffix}", f"[测试]销售单{suffix}", status, ids["test-sales"], *approval, *approval))
    order = _new(cursor, "INSERT INTO sales_orders (organization_id,farm_id,area_id,pond_id,batch_id,customer_id,code,name,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,created_by,approved_by,approved_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'草鱼',100,'kg',20,2000,'2026-08-16','2026-09-30','fully_delivered',%s,%s,NOW())", (*common, f"{PREFIX}-SO-FULFILL", "[测试]交付销售单", ids["test-sales"], ids["test-finance"]))
    delivery = _new(cursor, "INSERT INTO sales_deliveries (organization_id,sales_order_id,harvest_document_id,harvest_root_id,code,name,quantity,delivered_at,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,100,'2026-08-17 08:00:00','draft',%s)", (ids["org"], order, production["harvest"], production["harvest"], f"{PREFIX}-DELIVERY-01", "[测试]销售交付", ids["test-sales"]))
    evidence = _attachment(cursor, ids, "sales:delivery", delivery, 3)
    cursor.execute("UPDATE sales_deliveries SET status='verified',verified_by=%s,verified_at=NOW(),evidence_attachment_ids_json=JSON_ARRAY(%s) WHERE id=%s", (ids["test-finance"], evidence, delivery))
    cursor.execute("INSERT INTO sales_delivery_harvest_claims (harvest_root_id,sales_delivery_id) VALUES (%s,%s)", (production["harvest"], delivery))
    receivable = _new(cursor, "INSERT INTO sales_receivables (organization_id,sales_order_id,source_delivery_id,customer_id,idempotency_key,amount,received_amount,due_date,status) VALUES (%s,%s,%s,%s,%s,2000,500,'2026-09-30','partial')", (ids["org"], order, delivery, ids["customer"], f"{PREFIX}-RECEIVABLE-01"))
    for index, (code, amount, reverse) in enumerate((("RECEIPT-01", 500, False), ("RECEIPT-REV", 200, True)), 4):
        receipt = _new(cursor, "INSERT INTO sales_receipts (organization_id,receivable_id,code,name,amount,received_at,receipt_method,status,created_by) VALUES (%s,%s,%s,%s,%s,'2026-08-18','bank_transfer','draft',%s)", (ids["org"], receivable, f"{PREFIX}-{code}", f"[测试]{code}", amount, ids["test-finance"]))
        voucher = _attachment(cursor, ids, "sales:receipt", receipt, index)
        cursor.execute("UPDATE sales_receipts SET status='verified',verified_by=%s,verified_at=NOW(),evidence_attachment_ids_json=JSON_ARRAY(%s) WHERE id=%s", (ids["test-admin"], voucher, receipt))
        if reverse:
            cursor.execute("INSERT INTO sales_receipt_reversals (organization_id,receipt_id,amount,reversal_reason,evidence_attachment_ids_json,created_by) VALUES (%s,%s,%s,'银行退回',JSON_ARRAY(%s),%s)", (ids["org"], receipt, amount, voucher, ids["test-admin"]))


def _cost(cursor: Any, ids: dict[str, int], production: dict[str, int]) -> None:
    common = (ids["org"], ids["farm"], ids["area"], ids["category"])
    for index, status in enumerate(("draft", "submitted"), 1):
        _new(cursor, "INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,target_type,target_id,created_by) VALUES (%s,%s,%s,%s,%s,'2026-07-10','2026-07-01','2026-07-31',%s,'public','manual',%s,'pond',%s,%s)", (*common, index * 50, status, f"{PREFIX}-COST-{status.upper()}", ids["pond"], ids["test-finance"]))
    verified = _new(cursor, "INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,target_type,target_id,created_by) VALUES (%s,%s,%s,%s,70,'2026-07-12','2026-07-01','2026-07-31','draft','public','manual',%s,'pond',%s,%s)", (*common, f"{PREFIX}-COST-VERIFIED", ids["pond"], ids["test-finance"]))
    voucher = _attachment(cursor, ids, "cost:entry", verified, 6)
    cursor.execute("UPDATE cost_entries SET status='verified',verified_by=%s,verified_at=NOW(),evidence_attachment_ids_json=JSON_ARRAY(%s) WHERE id=%s", (ids["test-breed-manager"], voucher, verified))
    confirmed = _new(cursor, "INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,target_type,target_id,created_by,confirmed_by,confirmed_at) VALUES (%s,%s,%s,%s,200,'2026-07-15','2026-07-01','2026-07-31','confirmed','public','warehouse_ledger',%s,'batch',%s,%s,%s,NOW())", (*common, f"{PREFIX}-COST-CONFIRMED", production["batch"], ids["test-finance"], ids["test-admin"]))
    asset = _new(cursor, "INSERT INTO cost_assets (organization_id,farm_id,area_id,code,name,asset_type,category_id,purchase_date,original_value,salvage_value,useful_life_months,depreciation_start_date,allocation_driver,target_type,target_id,status,created_by) VALUES (%s,%s,%s,%s,%s,'equipment',%s,'2026-01-01',12000,1200,60,'2026-02-01','equal','farm',%s,'draft',%s)", (ids["org"], ids["farm"], ids["area"], f"{PREFIX}-ASSET-01", "[测试]增氧机", ids["category"], ids["farm"], ids["test-finance"]))
    asset_voucher = _attachment(cursor, ids, "cost:asset", asset, 7)
    cursor.execute("UPDATE cost_assets SET status='verified',verified_by=%s,verified_at=NOW(),evidence_attachment_ids_json=JSON_ARRAY(%s) WHERE id=%s", (ids["test-breed-manager"], asset_voucher, asset))
    run = _new(cursor, "INSERT INTO cost_allocation_runs (organization_id,farm_id,area_id,period_start,period_end,rule_version_id,result_version,source_total,allocated_total,participant_snapshot_json,status,created_by) VALUES (%s,%s,%s,'2026-07-01','2026-07-31',%s,1,200,200,JSON_OBJECT('pond_id',%s),'completed',%s)", (ids["org"], ids["farm"], ids["area"], ids["rule"], ids["pond"], ids["test-finance"]))
    cursor.execute("INSERT INTO cost_allocation_details (run_id,cost_entry_id,category_id,pond_id,batch_id,amount,driver,driver_value,source_snapshot_json) VALUES (%s,%s,%s,%s,%s,200,'equal',1,JSON_OBJECT('source','manual-test'))", (run, confirmed, ids["category"], ids["pond"], production["batch"]))
    settlement = _new(cursor, "INSERT INTO cost_settlements (organization_id,farm_id,area_id,code,name,period_start,period_end,allocation_run_id,income_amount,cost_amount,profit_amount,status,created_by,verified_by,verified_at,confirmed_by,confirmed_at,reversed_by,reversed_at,reversal_reason) VALUES (%s,%s,%s,%s,%s,'2026-07-01','2026-07-31',%s,2000,200,1800,'reversed',%s,%s,NOW(),%s,NOW(),%s,NOW(),'测试反结算')", (ids["org"], ids["farm"], ids["area"], f"{PREFIX}-SETTLEMENT-01", "[测试]七月结算", run, ids["test-finance"], ids["test-breed-manager"], ids["test-admin"], ids["test-admin"]))
    cursor.executemany("INSERT INTO cost_settlement_sources (settlement_id,direction,source_type,source_id,source_ref,amount,snapshot_json) VALUES (%s,%s,%s,%s,%s,%s,JSON_OBJECT('manual_test',TRUE))", [(settlement, "income", "sales_delivery", None, f"{PREFIX}-DELIVERY-01", 2000), (settlement, "cost", "cost_entry", confirmed, f"{PREFIX}-COST-CONFIRMED", 200)])


def _governance(cursor: Any, ids: dict[str, int], production: dict[str, int]) -> None:
    cursor.execute("INSERT INTO work_items (organization_id,assignee_user_id,module_code,action_code,object_type,object_id,target_version,object_ref,source_key,title,status) VALUES (%s,%s,'production','verify','production:samplings',%s,1,%s,%s,%s,'pending')", (ids["org"], ids["test-breed-manager"], production["submitted"], f"samplings:{production['submitted']}", f"production:samplings:{production['submitted']}:verify", "[测试]待核验抽样"))
    cursor.execute("INSERT INTO work_items (organization_id,assignee_user_id,module_code,action_code,object_type,object_id,target_version,object_ref,source_key,title,status,completed_by,completed_at,completion_note) VALUES (%s,%s,'production','verify','production:daily-operations',%s,1,%s,%s,%s,'completed',%s,NOW(),'核验完成')", (ids["org"], ids["test-breed-manager"], production["verified"], f"daily-operation:{production['verified']}", f"{PREFIX}:production:verified", "[测试]已完成核验巡塘", ids["test-breed-manager"]))
    cursor.execute("INSERT INTO notifications (recipient_user_id,module_code,notification_type,object_type,object_id,object_ref,dedup_key,title,body,status) VALUES (%s,'production','verification_required','production:samplings',%s,%s,%s,%s,%s,'unread')", (ids["test-breed-manager"], production["submitted"], f"sampling:{production['submitted']}", f"{PREFIX}:notification:submitted", "[测试]抽样记录待核验", "请核验测试抽样记录"))
    cursor.executemany(
        "INSERT INTO audit_logs (user_id,action,object_type,result,module_code,action_code,object_ref,actor_name_snapshot,actor_role_snapshot,detail_json) VALUES (%s,%s,'manual_test_dataset','success',%s,%s,%s,%s,%s,JSON_OBJECT('prefix',%s))",
        [
            (ids["test-breed-manager"], f"seed_{module}", module, f"seed_{module}",
             f"manual-test:{module}", "[测试]造数经办人", role, PREFIX)
            for module, role in (("production", "breed_manager"), ("purchase", "purchaser"),
                                 ("sales", "sales_staff"), ("cost", "finance_staff"))
        ],
    )


def seed_business(cursor: Any, _password: str) -> dict[str, object]:
    cursor.execute("SELECT id FROM production_batches WHERE code=%s", (f"{PREFIX}-BATCH-01",))
    if cursor.fetchone():
        return {"status": "existing", "prefix": PREFIX}
    ids = _context(cursor)
    production = _production(cursor, ids)
    _purchase_and_warehouse(cursor, ids)
    _sales(cursor, ids, production)
    _cost(cursor, ids, production)
    _governance(cursor, ids, production)
    return {"status": "created", "prefix": PREFIX, "domains": 8}
