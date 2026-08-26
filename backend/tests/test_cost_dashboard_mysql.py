from __future__ import annotations

from datetime import date

from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.cost_store import MySqlCostStore
from backend.layers.features.cost.cost_service import CostService
from backend.tests.mysql_test_database import disposable_database, settings_for
from backend.tests.test_cost_enterprise_mysql import actor, seed


def test_dashboard_reconciles_confirmed_cross_domain_facts_without_double_counting_purchase() -> None:
    with disposable_database("adp_cost_dashboard", through=16) as database:
        settings = settings_for(database)
        ids = seed(settings)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO business_partners (organization_id,farm_id,area_id,partner_type,code,name,status,created_by) VALUES (%s,%s,%s,'supplier','COST-SUP','成本供应商','verified',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"])); supplier_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO materials (organization_id,farm_id,area_id,code,name,category,unit,status,created_by) VALUES (%s,%s,%s,'COST-FEED','测试饲料','饲料','kg','verified',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"])); material_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO warehouses (organization_id,farm_id,area_id,code,name,status) VALUES (%s,%s,%s,'COST-WH','成本仓','active')", (ids["organization_id"], ids["farm_id"], ids["area_id"])); warehouse_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO purchase_orders (organization_id,farm_id,area_id,code,name,supplier_id,material_id,warehouse_id,quantity,unit_price,total_amount,due_date,status,created_by,approved_by,approved_at) VALUES (%s,%s,%s,'COST-PO','饲料采购',%s,%s,%s,10,5,50,'2026-09-30','approved',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], supplier_id, material_id, warehouse_id)); order_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO inventory_lots (organization_id,material_id,supplier_id,lot_no,unit_cost,status) VALUES (%s,%s,%s,'COST-LOT',5,'available')", (ids["organization_id"], material_id, supplier_id)); lot_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,material_id,inventory_lot_id,purchase_order_id,quantity,unit_cost,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'receipt','COST-IN','采购入库',%s,%s,%s,%s,10,5,'2026-08-20','verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], warehouse_id, material_id, lot_id, order_id)); receipt_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO purchase_payables (organization_id,purchase_order_id,source_receipt_id,supplier_id,idempotency_key,amount,due_date) VALUES (%s,%s,%s,%s,'cost-dashboard-receipt',50,'2026-09-30')", (ids["organization_id"], order_id, receipt_id, supplier_id))
            cursor.execute("INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,material_id,pond_id,batch_id,quantity,unit_cost,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'issue','COST-OUT','饲料领用',%s,%s,%s,%s,4,5,'2026-08-21','verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], warehouse_id, material_id, ids["pond_1"], ids["batch_id"])); issue_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,material_id,inventory_lot_id,source_document_id,pond_id,batch_id,quantity,unit_cost,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'return','COST-RETURN','饲料退库',%s,%s,%s,%s,%s,%s,1,5,'2026-08-22','verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], warehouse_id, material_id, lot_id, issue_id, ids["pond_1"], ids["batch_id"])); return_id = int(cursor.lastrowid)
            cursor.executemany("INSERT INTO inventory_ledger (organization_id,warehouse_id,material_id,inventory_lot_id,source_type,source_id,line_no,quantity_delta,unit_cost,pond_id,batch_id,happened_at,posted_by) VALUES (%s,%s,%s,%s,%s,%s,1,%s,5,%s,%s,%s,2)", [(ids["organization_id"], warehouse_id, material_id, lot_id, "receipt", receipt_id, 10, None, None, "2026-08-20"), (ids["organization_id"], warehouse_id, material_id, lot_id, "issue", issue_id, -4, ids["pond_1"], ids["batch_id"], "2026-08-21"), (ids["organization_id"], warehouse_id, material_id, lot_id, "return", return_id, 1, ids["pond_1"], ids["batch_id"], "2026-08-22")])
            cursor.execute("INSERT INTO batch_stock_records (organization_id,batch_id,pond_id,source_type,source_id,line_no,quantity_delta,weight_delta_kg,happened_at,posted_by) VALUES (%s,%s,%s,'harvest',%s,1,-10,-10,'2026-08-18',2)", (ids["organization_id"], ids["batch_id"], ids["pond_1"], ids["harvest_id"]))
            cursor.execute("INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,created_by,confirmed_by,confirmed_at) SELECT %s,%s,%s,id,10,'2026-08-23','2026-08-17','2026-08-31','confirmed','public','expense','COST-EXP',1,3,NOW() FROM cost_categories WHERE code='electricity'", (ids["organization_id"], ids["farm_id"], ids["area_id"]))
            cursor.execute("INSERT INTO cost_assets (organization_id,farm_id,area_id,code,name,asset_type,category_id,purchase_date,original_value,salvage_value,useful_life_months,depreciation_start_date,status,created_by,confirmed_by,confirmed_at) SELECT %s,%s,%s,'COST-ASSET','测试设备','equipment',id,'2026-08-01',36,0,12,'2026-08-01','confirmed',1,3,NOW() FROM cost_categories WHERE code='equipment'", (ids["organization_id"], ids["farm_id"], ids["area_id"])); asset_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,created_by,confirmed_by,confirmed_at) SELECT %s,%s,%s,id,3,'2026-08-31','2026-08-01','2026-08-31','confirmed','public','asset_depreciation','DEP-COST-ASSET-2026-08',1,3,NOW() FROM cost_categories WHERE code='equipment'", (ids["organization_id"], ids["farm_id"], ids["area_id"])); depreciation_entry_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO cost_depreciation_entries (organization_id,asset_id,period_start,period_end,amount,cost_entry_id,created_by) VALUES (%s,%s,'2026-08-01','2026-08-31',3,%s,1)", (ids["organization_id"], asset_id, depreciation_entry_id))

        viewer = actor(1, "cost.view")
        viewer["data_scopes"] = [{"scope_type": "area", "area_id": ids["area_id"]}]
        result = CostService(MySqlCostStore(settings)).structure(viewer, period_start=date(2026, 8, 17), period_end=date(2026, 8, 31))

        assert result["total_amount"] == "28.00"
        assert next(item for item in result["categories"] if item["code"] == "feed")["amount"] == "15.00"
        assert result["confirmed_output_weight_jin"] == "20.000"
        assert result["unit_production_cost"] == "1.4000"
        assert result["confirmed_income_amount"] == "260.00"
        assert result["confirmed_profit_amount"] == "232.00"
        assert result["source_fact_counts"] == {"warehouse": 2, "purchase": 1, "production": 1, "expense": 1, "asset": 1, "sales": 1}

        entries = CostService(MySqlCostStore(settings)).entries(
            viewer, category_code="feed", period_start=date(2026, 8, 17), period_end=date(2026, 8, 31),
            page=1, page_size=20, status="confirmed",
        )
        assert entries["total"] == 2
        assert [item["amount"] for item in entries["items"]] == ["-5.00", "20.00"]
        assert {item["source_ref"] for item in entries["items"]} == {"COST-OUT", "COST-RETURN"}
        assert all(item["source_detail_json"]["purchase_order_id"] == order_id for item in entries["items"])
