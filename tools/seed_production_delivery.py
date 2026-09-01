from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor


PREFIX = "DELIVERY-20260819"
VOUCHER = b"ADP delivery demo evidence 2026-08-19\n"


def new(cursor: Any, sql: str, params: tuple[object, ...]) -> int:
    cursor.execute(sql, params)
    return int(cursor.lastrowid)


def one(cursor: Any, sql: str, params: tuple[object, ...] = ()) -> int:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"required row not found: {sql}")
    return int(row["id"])


def attachment(cursor: Any, ids: dict[str, int], entity_type: str, entity_id: int, index: int) -> int:
    root_value = os.environ.get("ATTACHMENT_ROOT")
    if not root_value or not Path(root_value).is_absolute():
        raise RuntimeError("ATTACHMENT_ROOT must be an absolute path")
    root = Path(root_value)
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(VOUCHER).hexdigest()
    storage = f"{digest[:24]}{index:08d}"
    path = root / storage
    if not path.exists():
        path.write_bytes(VOUCHER)
    return new(cursor,
        "INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,%s,%s,%s,%s,'delivery-evidence.txt','text/plain',%s,%s)",
        (ids["org"], entity_type, entity_id, digest, storage, len(VOUCHER), ids["actor"]))


def master(cursor: Any, ids: dict[str, int]) -> None:
    for code, area, name in (
        (f"{PREFIX}-GROUP-NORTH", ids["north"], "[交付演示]北区标准组"),
        (f"{PREFIX}-GROUP-SOUTH", ids["south"], "[交付演示]南区标准组"),
    ):
        new(cursor,
            "INSERT INTO pond_groups (organization_id,farm_id,area_id,code,name,description,status,created_by) VALUES (%s,%s,%s,%s,%s,'交付验收专用分组','verified',%s)",
            (ids["org"], ids["farm"], area, code, name, ids["actor"]))
    cursor.execute("SELECT id,area_id FROM pond_groups WHERE code LIKE %s ORDER BY id", (f"{PREFIX}-GROUP-%",))
    groups = {int(row["area_id"]): int(row["id"]) for row in cursor.fetchall()}
    ponds: list[tuple[int, int]] = []
    for index, (area, label) in enumerate(((ids["north"], "北"), (ids["north"], "北"), (ids["south"], "南"), (ids["south"], "南")), 1):
        new(cursor,
            "INSERT INTO ponds (organization_id,farm_id,area_id,pond_group_id,code,name,description,location_text,species,manager_name,capacity_mu,pond_status,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,'交付演示专用塘口',%s,'草鱼','交付验收管理员',%s,'build','verified',%s)",
            (ids["org"], ids["farm"], area, groups[area], f"{PREFIX}-POND-{index:02d}", f"[交付演示]{label}区{index}号塘", f"交付区-{index}", 10 + index, ids["actor"]))
        ponds.append((int(cursor.lastrowid), index))
    for pond_id, index in ponds:
        current_version = 1
        for from_status, to_status in (("build", "stocked"), ("stocked", "farming")):
            cursor.execute(
                "INSERT INTO pond_status_change_requests (organization_id,pond_id,from_status,to_status,reason,status,pond_version,requested_by,verified_by,verified_at) VALUES (%s,%s,%s,%s,%s,'verified',%s,%s,%s,NOW())",
                (ids["org"], pond_id, from_status, to_status, f"交付演示生命周期：第{index}号塘{from_status}->{to_status}", current_version, ids["actor"], ids["reviewer"]),
            )
            cursor.execute("UPDATE ponds SET pond_status=%s,row_version=row_version+1,updated_by=%s WHERE id=%s AND row_version=%s", (to_status, ids["reviewer"], pond_id, current_version))
            if cursor.rowcount != 1:
                raise RuntimeError(f"pond lifecycle update failed: {pond_id}")
            current_version += 1
    supplier = new(cursor,
        "INSERT INTO business_partners (organization_id,farm_id,area_id,partner_type,code,name,contact_name,phone,address,status,created_by) VALUES (%s,%s,%s,'supplier',%s,'[交付演示]水产物资供应商','演示联系人','13900000001','演示地址','verified',%s)",
        (ids["org"], ids["farm"], ids["north"], f"{PREFIX}-SUPPLIER", ids["actor"]))
    new(cursor,
        "INSERT INTO business_partners (organization_id,farm_id,area_id,partner_type,code,name,contact_name,phone,address,status,created_by) VALUES (%s,%s,%s,'customer',%s,'[交付演示]鲜活水产客户','演示采购联系人','13900000002','演示地址','verified',%s)",
        (ids["org"], ids["farm"], ids["north"], f"{PREFIX}-CUSTOMER", ids["actor"]))
    for code, name, category, unit in (
        ("FEED", "草鱼膨化饲料", "饲料", "kg"),
        ("SEED", "草鱼苗种", "苗种", "尾"),
        ("HEALTH", "水产动保物料", "动保", "kg"),
        ("EQUIP", "增氧设备配件", "设备", "件"),
    ):
        new(cursor,
            "INSERT INTO materials (organization_id,farm_id,area_id,code,name,category,unit,safety_stock,default_supplier_id,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,100,%s,'verified',%s)",
            (ids["org"], ids["farm"], ids["north"], f"{PREFIX}-MAT-{code}", f"[交付演示]{name}", category, unit, supplier, ids["actor"]))
    new(cursor,
        "INSERT INTO warehouses (organization_id,farm_id,area_id,code,name,location,status) VALUES (%s,%s,%s,%s,'[交付演示]综合仓库','交付演示养殖场内','active')",
        (ids["org"], ids["farm"], ids["north"], f"{PREFIX}-WAREHOUSE"))


def base_context(cursor: Any) -> dict[str, int]:
    ids = {
        "org": one(cursor, "SELECT id FROM organizations WHERE code='default'"),
        "farm": one(cursor, "SELECT id FROM farms WHERE code='default-farm'"),
        "north": one(cursor, "SELECT id FROM areas WHERE code='north-farm'"),
        "south": one(cursor, "SELECT id FROM areas WHERE code='south-farm'"),
        "category": one(cursor, "SELECT id FROM cost_categories WHERE code='other'"),
        "rule": one(cursor, "SELECT id FROM cost_allocation_rule_versions WHERE status='active' ORDER BY version_no DESC LIMIT 1"),
        "actor": one(cursor, "SELECT id FROM users WHERE login_name='adpadmin' AND status='active'"),
        "reviewer": one(cursor, "SELECT id FROM users WHERE login_name='qa_tester' AND status='active'"),
    }
    return ids


def context(cursor: Any) -> dict[str, int]:
    ids = base_context(cursor)
    for key, table, column, code in (
        ("pond", "ponds", "code", f"{PREFIX}-POND-01"),
        ("material", "materials", "code", f"{PREFIX}-MAT-FEED"),
        ("supplier", "business_partners", "code", f"{PREFIX}-SUPPLIER"),
        ("customer", "business_partners", "code", f"{PREFIX}-CUSTOMER"),
        ("warehouse", "warehouses", "code", f"{PREFIX}-WAREHOUSE"),
    ):
        ids[key] = one(cursor, f"SELECT id FROM {table} WHERE {column}=%s", (code,))
    return ids


def production(cursor: Any, ids: dict[str, int]) -> dict[str, int]:
    batch = new(cursor,
        "INSERT INTO production_batches (organization_id,farm_id,area_id,pond_id,code,name,species,initial_quantity,initial_weight_kg,stocked_at,batch_status,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,%s,%s,'[交付演示]草鱼养殖批次','草鱼',1000,1000,'2026-08-01 08:00:00','farming','verified',%s,%s,NOW())",
        (ids["org"], ids["farm"], ids["north"], ids["pond"], f"{PREFIX}-BATCH-01", ids["actor"], ids["reviewer"]))
    cursor.execute("INSERT INTO batch_stock_records (organization_id,batch_id,pond_id,source_type,source_id,quantity_delta,weight_delta_kg,happened_at,posted_by) VALUES (%s,%s,%s,'stocking',%s,1000,1000,'2026-08-01 08:00:00',%s)", (ids["org"], batch, ids["pond"], batch, ids["reviewer"]))
    base = (ids["org"], ids["farm"], ids["north"], batch, ids["pond"])
    new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,happened_at,status,created_by) VALUES (%s,%s,%s,'daily_operation',%s,'[交付演示]巡塘草稿',%s,%s,'2026-08-10 08:00:00','draft',%s)", (*base[:3], f"{PREFIX}-PROD-DRAFT", *base[3:], ids["actor"]))
    submitted = new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,happened_at,status,created_by) VALUES (%s,%s,%s,'sampling',%s,'[交付演示]抽样待核验',%s,%s,'2026-08-11 08:00:00','submitted',%s)", (*base[:3], f"{PREFIX}-PROD-SUBMITTED", *base[3:], ids["actor"]))
    verified = new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'daily_operation',%s,'[交付演示]已核验巡塘',%s,%s,'2026-08-12 08:00:00','verified',%s,%s,NOW())", (*base[:3], f"{PREFIX}-PROD-VERIFIED", *base[3:], ids["actor"], ids["reviewer"]))
    new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,happened_at,correction_of_id,note,status,created_by) VALUES (%s,%s,%s,'correction',%s,'[交付演示]巡塘更正草稿',%s,%s,'2026-08-12 09:00:00',%s,'更正演示备注','draft',%s)", (*base[:3], f"{PREFIX}-PROD-CORRECTION", *base[3:], verified, ids["actor"]))
    harvest = new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,quantity,weight_kg,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'harvest',%s,'[交付演示]草鱼出塘',%s,%s,100,100,'2026-08-13 08:00:00','verified',%s,%s,NOW())", (*base[:3], f"{PREFIX}-HARVEST-01", *base[3:], ids["actor"], ids["reviewer"]))
    cursor.execute("INSERT INTO batch_stock_records (organization_id,batch_id,pond_id,source_type,source_id,quantity_delta,weight_delta_kg,happened_at,posted_by) VALUES (%s,%s,%s,'harvest',%s,-100,-100,'2026-08-13 08:00:00',%s)", (ids["org"], batch, ids["pond"], harvest, ids["reviewer"]))
    return {"batch": batch, "submitted": submitted, "verified": verified, "harvest": harvest}


def purchase_warehouse(cursor: Any, ids: dict[str, int]) -> dict[str, int]:
    common = (ids["org"], ids["farm"], ids["north"], ids["supplier"], ids["material"], ids["warehouse"])
    for suffix, status in (("DRAFT", "draft"), ("SUBMITTED", "submitted")):
        new(cursor, "INSERT INTO purchase_orders (organization_id,farm_id,area_id,supplier_id,material_id,warehouse_id,code,name,quantity,unit_price,total_amount,due_date,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,100,10,1000,'2026-09-30',%s,%s)", (*common, f"{PREFIX}-PO-{suffix}", f"[交付演示]采购单{suffix}", status, ids["actor"]))
    order = new(cursor, "INSERT INTO purchase_orders (organization_id,farm_id,area_id,supplier_id,material_id,warehouse_id,code,name,quantity,unit_price,total_amount,due_date,status,created_by,approved_by,approved_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,100,10,1000,'2026-09-30','fully_received',%s,%s,NOW())", (*common, f"{PREFIX}-PO-APPROVED", "[交付演示]已审批采购单", ids["actor"], ids["reviewer"]))
    lot = new(cursor, "INSERT INTO inventory_lots (organization_id,material_id,supplier_id,lot_no,production_date,expiry_date,unit_cost,status) VALUES (%s,%s,%s,%s,'2026-08-01','2027-08-01',10,'available')", (ids["org"], ids["material"], ids["supplier"], f"{PREFIX}-LOT-01"))
    receipt = new(cursor, "INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,material_id,inventory_lot_id,purchase_order_id,quantity,unit_cost,lot_no,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'receipt',%s,'[交付演示]采购入库',%s,%s,%s,%s,100,10,%s,'2026-08-14 08:00:00','verified',%s,%s,NOW())", (ids["org"], ids["farm"], ids["north"], f"{PREFIX}-WH-RECEIPT", ids["warehouse"], ids["material"], lot, order, f"{PREFIX}-LOT-01", ids["actor"], ids["reviewer"]))
    cursor.execute("INSERT INTO inventory_ledger (organization_id,warehouse_id,material_id,inventory_lot_id,source_type,source_id,line_no,quantity_delta,unit_cost,happened_at,posted_by) VALUES (%s,%s,%s,%s,'receipt',%s,1,100,10,'2026-08-14 08:00:00',%s)", (ids["org"], ids["warehouse"], ids["material"], lot, receipt, ids["reviewer"]))
    for suffix, doc_type, status in (("DRAFT", "issue_request", "draft"), ("SUBMITTED", "return", "submitted")):
        new(cursor, "INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,material_id,inventory_lot_id,quantity,unit_cost,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,10,10,%s,%s)", (ids["org"], ids["farm"], ids["north"], doc_type, f"{PREFIX}-WH-{suffix}", f"[交付演示]仓储单{suffix}", ids["warehouse"], ids["material"], lot, status, ids["actor"]))
    payable = new(cursor, "INSERT INTO purchase_payables (organization_id,purchase_order_id,source_receipt_id,supplier_id,idempotency_key,amount,paid_amount,due_date,status) VALUES (%s,%s,%s,%s,%s,1000,400,'2026-09-30','partial')", (ids["org"], order, receipt, ids["supplier"], f"{PREFIX}-PAYABLE-01"))
    payment = new(cursor, "INSERT INTO purchase_payments (organization_id,payable_id,code,name,amount,paid_at,payment_method,status,created_by) VALUES (%s,%s,%s,'[交付演示]付款凭证',400,'2026-08-15','bank_transfer','draft',%s)", (ids["org"], payable, f"{PREFIX}-PAYMENT-01", ids["actor"]))
    evidence = attachment(cursor, ids, "purchase:payment", payment, 1)
    cursor.execute("UPDATE purchase_payments SET status='verified',verified_by=%s,verified_at=NOW(),evidence_attachment_ids_json=JSON_ARRAY(%s) WHERE id=%s", (ids["reviewer"], evidence, payment))
    reversal = new(cursor, "INSERT INTO purchase_payments (organization_id,payable_id,code,name,amount,paid_at,payment_method,status,created_by) VALUES (%s,%s,%s,'[交付演示]冲销付款',100,'2026-08-15','bank_transfer','draft',%s)", (ids["org"], payable, f"{PREFIX}-PAYMENT-REV", ids["actor"]))
    evidence = attachment(cursor, ids, "purchase:payment_reversal", reversal, 2)
    cursor.execute("UPDATE purchase_payments SET status='verified',verified_by=%s,verified_at=NOW(),evidence_attachment_ids_json=JSON_ARRAY(%s) WHERE id=%s", (ids["reviewer"], evidence, reversal))
    cursor.execute("INSERT INTO purchase_payment_reversals (organization_id,payment_id,amount,reversal_reason,evidence_attachment_ids_json,created_by) VALUES (%s,%s,100,'银行退回',JSON_ARRAY(%s),%s)", (ids["org"], reversal, evidence, ids["actor"]))
    return {"order": order, "receipt": receipt}


def sales(cursor: Any, ids: dict[str, int], prod: dict[str, int]) -> None:
    common = (ids["org"], ids["farm"], ids["north"], ids["pond"], prod["batch"], ids["customer"])
    for suffix, status in (("DRAFT", "draft"), ("SUBMITTED", "submitted"), ("APPROVED", "approved")):
        approval = (ids["reviewer"],) if status == "approved" else (None,)
        new(cursor, "INSERT INTO sales_orders (organization_id,farm_id,area_id,pond_id,batch_id,customer_id,code,name,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,created_by,approved_by,approved_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'草鱼',100,'kg',20,2000,'2026-08-16','2026-09-30',%s,%s,%s,IF(%s IS NULL,NULL,NOW()))", (*common, f"{PREFIX}-SO-{suffix}", f"[交付演示]销售单{suffix}", status, ids["actor"], *approval, *approval))
    order = new(cursor, "INSERT INTO sales_orders (organization_id,farm_id,area_id,pond_id,batch_id,customer_id,code,name,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,created_by,approved_by,approved_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'草鱼',100,'kg',20,2000,'2026-08-16','2026-09-30','fully_delivered',%s,%s,NOW())", (*common, f"{PREFIX}-SO-FULFILL", "[交付演示]交付销售单", ids["actor"], ids["reviewer"]))
    delivery = new(cursor, "INSERT INTO sales_deliveries (organization_id,sales_order_id,harvest_document_id,harvest_root_id,code,name,quantity,delivered_at,status,created_by) VALUES (%s,%s,%s,%s,%s,'[交付演示]销售交付',100,'2026-08-17 08:00:00','draft',%s)", (ids["org"], order, prod["harvest"], prod["harvest"], f"{PREFIX}-DELIVERY-01", ids["actor"]))
    evidence = attachment(cursor, ids, "sales:delivery", delivery, 3)
    cursor.execute("UPDATE sales_deliveries SET status='verified',verified_by=%s,verified_at=NOW(),evidence_attachment_ids_json=JSON_ARRAY(%s) WHERE id=%s", (ids["reviewer"], evidence, delivery))
    cursor.execute("INSERT INTO sales_delivery_harvest_claims (harvest_root_id,sales_delivery_id) VALUES (%s,%s)", (prod["harvest"], delivery))
    receivable = new(cursor, "INSERT INTO sales_receivables (organization_id,sales_order_id,source_delivery_id,customer_id,idempotency_key,amount,received_amount,due_date,status) VALUES (%s,%s,%s,%s,%s,2000,500,'2026-09-30','partial')", (ids["org"], order, delivery, ids["customer"], f"{PREFIX}-RECEIVABLE-01"))
    for index, (code, amount, reversal) in enumerate((("RECEIPT-01", 500, False), ("RECEIPT-REV", 200, True)), 4):
        receipt = new(cursor, "INSERT INTO sales_receipts (organization_id,receivable_id,code,name,amount,received_at,receipt_method,status,created_by) VALUES (%s,%s,%s,%s,%s,'2026-08-18','bank_transfer','draft',%s)", (ids["org"], receivable, f"{PREFIX}-{code}", f"[交付演示]{code}", amount, ids["actor"]))
        evidence = attachment(cursor, ids, "sales:receipt_reversal" if reversal else "sales:receipt", receipt, index)
        cursor.execute("UPDATE sales_receipts SET status='verified',verified_by=%s,verified_at=NOW(),evidence_attachment_ids_json=JSON_ARRAY(%s) WHERE id=%s", (ids["reviewer"], evidence, receipt))
        if reversal:
            cursor.execute("INSERT INTO sales_receipt_reversals (organization_id,receipt_id,amount,reversal_reason,evidence_attachment_ids_json,created_by) VALUES (%s,%s,%s,'银行退回',JSON_ARRAY(%s),%s)", (ids["org"], receipt, amount, evidence, ids["actor"]))


def cost(cursor: Any, ids: dict[str, int], prod: dict[str, int]) -> None:
    common = (ids["org"], ids["farm"], ids["north"], ids["category"])
    for amount, status in ((50, "draft"), (100, "submitted")):
        new(cursor, "INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,target_type,target_id,created_by) VALUES (%s,%s,%s,%s,%s,'2026-07-10','2026-07-01','2026-07-31',%s,'public','manual',%s,'pond',%s,%s)", (*common, amount, status, f"{PREFIX}-COST-{status.upper()}", ids["pond"], ids["actor"]))
    verified = new(cursor, "INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,target_type,target_id,created_by) VALUES (%s,%s,%s,%s,70,'2026-07-12','2026-07-01','2026-07-31','draft','public','manual',%s,'pond',%s,%s)", (*common, f"{PREFIX}-COST-VERIFIED", ids["pond"], ids["actor"]))
    evidence = attachment(cursor, ids, "cost:entry", verified, 6)
    cursor.execute("UPDATE cost_entries SET status='verified',verified_by=%s,verified_at=NOW(),evidence_attachment_ids_json=JSON_ARRAY(%s) WHERE id=%s", (ids["reviewer"], evidence, verified))
    confirmed = new(cursor, "INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,target_type,target_id,created_by,confirmed_by,confirmed_at) VALUES (%s,%s,%s,%s,200,'2026-07-15','2026-07-01','2026-07-31','confirmed','public','warehouse_ledger',%s,'batch',%s,%s,%s,NOW())", (*common, f"{PREFIX}-COST-CONFIRMED", prod["batch"], ids["actor"], ids["actor"]))
    asset = new(cursor, "INSERT INTO cost_assets (organization_id,farm_id,area_id,code,name,asset_type,category_id,purchase_date,original_value,salvage_value,useful_life_months,depreciation_start_date,allocation_driver,target_type,target_id,status,created_by) VALUES (%s,%s,%s,%s,'[交付演示]增氧机','equipment',%s,'2026-01-01',12000,1200,60,'2026-02-01','equal','farm',%s,'draft',%s)", (ids["org"], ids["farm"], ids["north"], f"{PREFIX}-ASSET-01", ids["category"], ids["farm"], ids["actor"]))
    evidence = attachment(cursor, ids, "cost:asset", asset, 7)
    cursor.execute("UPDATE cost_assets SET status='verified',verified_by=%s,verified_at=NOW(),evidence_attachment_ids_json=JSON_ARRAY(%s) WHERE id=%s", (ids["reviewer"], evidence, asset))
    run = new(cursor, "INSERT INTO cost_allocation_runs (organization_id,farm_id,area_id,period_start,period_end,rule_version_id,result_version,source_total,allocated_total,participant_snapshot_json,status,created_by) VALUES (%s,%s,%s,'2026-07-01','2026-07-31',%s,1,200,200,JSON_OBJECT('pond_id',%s),'completed',%s)", (ids["org"], ids["farm"], ids["north"], ids["rule"], ids["pond"], ids["actor"]))
    cursor.execute("INSERT INTO cost_allocation_details (run_id,cost_entry_id,category_id,pond_id,batch_id,amount,driver,driver_value,source_snapshot_json) VALUES (%s,%s,%s,%s,%s,200,'equal',1,JSON_OBJECT('source','delivery'))", (run, confirmed, ids["category"], ids["pond"], prod["batch"]))
    settlement = new(cursor, "INSERT INTO cost_settlements (organization_id,farm_id,area_id,code,name,period_start,period_end,allocation_run_id,income_amount,cost_amount,profit_amount,status,created_by,verified_by,verified_at,confirmed_by,confirmed_at,reversed_by,reversed_at,reversal_reason) VALUES (%s,%s,%s,%s,'[交付演示]七月结算','2026-07-01','2026-07-31',%s,2000,200,1800,'reversed',%s,%s,NOW(),%s,NOW(),%s,NOW(),'交付演示反结算')", (ids["org"], ids["farm"], ids["north"], f"{PREFIX}-SETTLEMENT-01", run, ids["actor"], ids["reviewer"], ids["actor"], ids["actor"]))
    delivery_id = one(cursor, "SELECT id FROM sales_deliveries WHERE code=%s", (f"{PREFIX}-DELIVERY-01",))
    cursor.executemany("INSERT INTO cost_settlement_sources (settlement_id,direction,source_type,source_id,source_ref,amount,snapshot_json) VALUES (%s,%s,%s,%s,%s,%s,JSON_OBJECT('delivery',TRUE))", [(settlement, "income", "sales_delivery", delivery_id, f"{PREFIX}-DELIVERY-01", 2000), (settlement, "cost", "cost_entry", confirmed, f"{PREFIX}-COST-CONFIRMED", 200)])


def governance(cursor: Any, ids: dict[str, int], prod: dict[str, int]) -> None:
    cursor.execute("INSERT INTO work_items (organization_id,assignee_user_id,module_code,action_code,object_type,object_id,target_version,object_ref,source_key,title,status) VALUES (%s,%s,'production','verify','production:samplings',%s,1,%s,%s,'[交付演示]待核验抽样','pending')", (ids["org"], ids["reviewer"], prod["submitted"], f"samplings:{prod['submitted']}", f"{PREFIX}:sampling:verify"))
    cursor.execute("INSERT INTO work_items (organization_id,assignee_user_id,module_code,action_code,object_type,object_id,target_version,object_ref,source_key,title,status,completed_by,completed_at,completion_note) VALUES (%s,%s,'production','verify','production:daily-operations',%s,1,%s,%s,'[交付演示]已完成核验巡塘','completed',%s,NOW(),'交付演示核验完成')", (ids["org"], ids["reviewer"], prod["verified"], f"daily-operation:{prod['verified']}", f"{PREFIX}:daily:verified", ids["reviewer"]))
    cursor.execute("INSERT INTO notifications (recipient_user_id,module_code,notification_type,object_type,object_id,object_ref,dedup_key,title,body,status) VALUES (%s,'production','verification_required','production:samplings',%s,%s,%s,'[交付演示]抽样记录待核验','请核验交付演示抽样记录','unread')", (ids["reviewer"], prod["submitted"], f"sampling:{prod['submitted']}", f"{PREFIX}:notification:submitted"))
    for module in ("master", "production", "warehouse", "purchase", "sales", "cost"):
        cursor.execute("INSERT INTO audit_logs (user_id,action,object_type,result,module_code,action_code,object_ref,actor_name_snapshot,actor_role_snapshot,detail_json) VALUES (%s,%s,'delivery_demo_dataset','success',%s,%s,%s,'系统管理员','super_admin',JSON_OBJECT('prefix',%s))", (ids["actor"], f"seed_{module}", module, f"seed_{module}", f"{PREFIX}:{module}", PREFIX))


def activity(cursor: Any, ids: dict[str, int]) -> None:
    """Add non-empty daily-farming and high-risk draft/submitted records."""
    pond_two = one(cursor, "SELECT id FROM ponds WHERE code=%s", (f"{PREFIX}-POND-02",))
    batch = one(cursor, "SELECT id FROM production_batches WHERE code=%s", (f"{PREFIX}-BATCH-01",))
    material = ids["material"]
    lot = one(cursor, "SELECT id FROM inventory_lots WHERE lot_no=%s", (f"{PREFIX}-LOT-01",))
    cursor.execute("SELECT id FROM warehouse_documents WHERE code=%s", (f"{PREFIX}-WH-ISSUE-REQUEST",))
    issue_row = cursor.fetchone()
    if issue_row:
        issue_request = int(issue_row["id"])
    else:
        issue_request = new(cursor, "INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,material_id,pond_id,batch_id,quantity,unit_cost,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'issue_request',%s,'[交付演示]已核验领料申请',%s,%s,%s,%s,12,10,'verified',%s,%s,NOW())", (ids["org"], ids["farm"], ids["north"], f"{PREFIX}-WH-ISSUE-REQUEST", ids["warehouse"], material, ids["pond"], batch, ids["actor"], ids["reviewer"]))
    cursor.execute("SELECT id FROM warehouse_documents WHERE code=%s", (f"{PREFIX}-WH-ISSUE",))
    if not cursor.fetchone():
        issue = new(cursor, "INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,material_id,inventory_lot_id,source_document_id,pond_id,batch_id,quantity,unit_cost,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'issue',%s,'[交付演示]已核验领料出库',%s,%s,%s,%s,%s,%s,12,10,'verified',%s,%s,NOW())", (ids["org"], ids["farm"], ids["north"], f"{PREFIX}-WH-ISSUE", ids["warehouse"], material, lot, issue_request, ids["pond"], batch, ids["actor"], ids["reviewer"]))
        cursor.execute("INSERT INTO inventory_ledger (organization_id,warehouse_id,material_id,inventory_lot_id,source_type,source_id,line_no,quantity_delta,unit_cost,pond_id,batch_id,happened_at,posted_by) VALUES (%s,%s,%s,%s,'issue',%s,1,-12,10,%s,%s,'2026-08-19 09:00:00',%s)", (ids["org"], ids["warehouse"], material, lot, issue, ids["pond"], batch, ids["reviewer"]))
    for doc_type, code, name in (("stocktake", f"{PREFIX}-WH-STOCKTAKE", "[交付演示]库存盘点草稿"), ("scrap", f"{PREFIX}-WH-SCRAP", "[交付演示]报损报废草稿"), ("transfer", f"{PREFIX}-WH-TRANSFER", "[交付演示]仓间调拨草稿")):
        cursor.execute("SELECT id FROM warehouse_documents WHERE code=%s", (code,))
        if not cursor.fetchone():
            new(cursor, "INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,target_warehouse_id,material_id,inventory_lot_id,quantity,unit_cost,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,10,'draft',%s)", (ids["org"], ids["farm"], ids["north"], doc_type, code, name, ids["warehouse"], ids["warehouse"], material, lot, ids["actor"]))
    records = [
        ("transfer", f"{PREFIX}-TRANSFER-DRAFT", "[交付演示]转塘草稿", ids["pond"], pond_two, 50, 50, None, None, None, "draft"),
        ("transfer", f"{PREFIX}-TRANSFER-SUBMITTED", "[交付演示]待核验转塘", ids["pond"], pond_two, 50, 50, None, None, None, "submitted"),
        ("loss", f"{PREFIX}-LOSS-SUBMITTED", "[交付演示]待核验损耗", ids["pond"], None, 10, 10, None, None, None, "submitted"),
        ("feed_plan", f"{PREFIX}-FEED-PLAN-VERIFIED", "[交付演示]草鱼日投喂计划", ids["pond"], None, 0, 0, None, None, '{"times_per_day":2,"standard_amount_kg":12}', "verified"),
    ]
    for doc_type, code, name, pond, target, quantity, weight, feed_plan_id, feed_task_id, payload, status in records:
        cursor.execute("SELECT id FROM production_documents WHERE code=%s", (code,))
        if cursor.fetchone():
            continue
        if status == "verified":
            new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,target_pond_id,quantity,weight_kg,payload_json,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'2026-08-19 08:00:00',%s,%s,%s,NOW())", (ids["org"], ids["farm"], ids["north"], doc_type, code, name, batch, pond, target, quantity, weight, payload, status, ids["actor"], ids["reviewer"]))
        else:
            new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,target_pond_id,quantity,weight_kg,happened_at,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'2026-08-19 08:00:00',%s,%s)", (ids["org"], ids["farm"], ids["north"], doc_type, code, name, batch, pond, target, quantity, weight, status, ids["actor"]))
    cursor.execute("SELECT id FROM production_documents WHERE code=%s", (f"{PREFIX}-FEED-PLAN-VERIFIED",))
    feed_plan = int(cursor.fetchone()["id"])
    task_code = f"{PREFIX}-FEED-TASK-SUBMITTED"
    cursor.execute("SELECT id FROM production_documents WHERE code=%s", (task_code,))
    task_row = cursor.fetchone()
    task = int(task_row["id"]) if task_row else new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,material_id,feed_plan_id,assigned_user_id,quantity,planned_at,status,created_by) VALUES (%s,%s,%s,'feed_task',%s,'[交付演示]待执行投喂任务',%s,%s,%s,%s,%s,12,'2026-08-20 06:30:00','submitted',%s)", (ids["org"], ids["farm"], ids["north"], task_code, batch, ids["pond"], material, feed_plan, ids["actor"], ids["actor"]))
    log_code = f"{PREFIX}-FEED-LOG-SUBMITTED"
    cursor.execute("SELECT id FROM production_documents WHERE code=%s", (log_code,))
    if not cursor.fetchone():
        new(cursor, "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,material_id,feed_task_id,material_issue_request_id,quantity,weight_kg,payload_json,happened_at,status,created_by) VALUES (%s,%s,%s,'feed_log',%s,'[交付演示]待核验投喂记录',%s,%s,%s,%s,%s,12,12,%s,'2026-08-20 06:45:00','submitted',%s)", (ids["org"], ids["farm"], ids["north"], log_code, batch, ids["pond"], material, task, issue_request, '{"appetite":"normal","weather":"sunny"}', ids["actor"]))


def run() -> dict[str, object]:
    required = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError(f"missing environment: {','.join(missing)}")
    if os.environ["MYSQL_DATABASE"] != "adp_production_20260821_codex":
        raise RuntimeError("refusing non-production delivery target")
    connection = pymysql.connect(host=os.environ["MYSQL_HOST"], port=int(os.environ["MYSQL_PORT"]), user=os.environ["MYSQL_USER"], password=os.environ["MYSQL_PASSWORD"], database=os.environ["MYSQL_DATABASE"], charset="utf8mb4", cursorclass=DictCursor, autocommit=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM pond_groups WHERE code=%s", (f"{PREFIX}-GROUP-NORTH",))
            if cursor.fetchone():
                ids = context(cursor)
                cursor.execute("UPDATE materials SET area_id=%s WHERE code LIKE %s", (ids["north"], f"{PREFIX}-MAT-%"))
                cursor.execute("UPDATE business_partners SET area_id=%s WHERE code LIKE %s", (ids["north"], f"{PREFIX}-%"))
                activity(cursor, ids)
                connection.commit()
                return {"status": "existing", "prefix": PREFIX, "activity": "ensured"}
            ids = base_context(cursor)
            master(cursor, ids)
            ids = context(cursor)
            prod = production(cursor, ids)
            warehouse = purchase_warehouse(cursor, ids)
            sales(cursor, ids, prod)
            cost(cursor, ids, prod)
            governance(cursor, ids, prod)
            activity(cursor, ids)
        connection.commit()
        return {"status": "created", "prefix": PREFIX, "domains": 8, "production": prod, "purchase": warehouse}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
