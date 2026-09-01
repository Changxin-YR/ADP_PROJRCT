from __future__ import annotations

from decimal import Decimal
from typing import Any

import pymysql
import pytest

from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.cost_store import MySqlCostStore
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.cost.cost_enterprise_service import CostEnterpriseService
from backend.tests.mysql_test_database import disposable_database, settings_for


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
            [("13940000001", "成本经办"), ("13940000002", "成本核验"), ("13940000003", "成本确认")],
        )
        cursor.execute("SELECT id AS organization_id FROM organizations WHERE code='default'")
        ids = dict(cursor.fetchone())
        cursor.execute("SELECT id AS farm_id FROM farms WHERE code='default-farm'")
        ids.update(cursor.fetchone())
        cursor.execute("INSERT INTO areas (organization_id,farm_id,code,name,status,created_by) VALUES (%s,%s,'CA','成本区','verified',1)", (ids["organization_id"], ids["farm_id"]))
        ids["area_id"] = int(cursor.lastrowid)
        for index in range(1, 4):
            cursor.execute("INSERT INTO ponds (organization_id,farm_id,area_id,code,name,capacity_mu,status,created_by,created_at) VALUES (%s,%s,%s,%s,%s,0,'verified',1,'2026-08-01')", (ids["organization_id"], ids["farm_id"], ids["area_id"], f"CP{index}", f"成本塘{index}"))
            ids[f"pond_{index}"] = int(cursor.lastrowid)
        cursor.execute("INSERT INTO business_partners (organization_id,farm_id,area_id,partner_type,code,name,status,created_by) VALUES (%s,%s,%s,'customer','CC1','成本测试客户','verified',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"])); ids["customer_id"] = int(cursor.lastrowid)
        cursor.execute("INSERT INTO production_batches (organization_id,farm_id,area_id,pond_id,code,name,species,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,%s,'CB1','成本批次','鲈鱼','verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["pond_1"])); ids["batch_id"] = int(cursor.lastrowid)
        cursor.execute("INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,quantity,weight_kg,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'harvest','CH1','成本测试出塘',%s,%s,10,10,'2026-08-18','verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["batch_id"], ids["pond_1"])); ids["harvest_id"] = int(cursor.lastrowid)
        cursor.execute("INSERT INTO sales_orders (organization_id,farm_id,area_id,pond_id,batch_id,customer_id,code,name,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,created_by,approved_by,approved_at) VALUES (%s,%s,%s,%s,%s,%s,'CSO1','成本测试销售','鲈鱼',10,'kg',26,260,'2026-08-17','2026-09-17','approved',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["pond_1"], ids["batch_id"], ids["customer_id"])); ids["sales_order_id"] = int(cursor.lastrowid)
        cursor.execute("INSERT INTO sales_deliveries (organization_id,sales_order_id,harvest_document_id,harvest_root_id,code,name,quantity,delivered_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,%s,'CSD1','成本测试交付',10,'2026-08-18','verified',1,2,NOW())", (ids["organization_id"], ids["sales_order_id"], ids["harvest_id"], ids["harvest_id"]))
        ids["delivery_id"] = int(cursor.lastrowid)
        for index in range(1, 4):
            cursor.execute("INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,'unbound',1,%s,%s,%s,'application/pdf',12,1)", (ids["organization_id"], str(index) * 64, format(index + 10, "x") * 32, f"cost-{index}.pdf"))
            ids[f"attachment_{index}"] = int(cursor.lastrowid)
    return ids


def expense(ids: dict[str, int], code: str = "EXP-REAL-1") -> dict[str, Any]:
    return {
        "organization_id": ids["organization_id"], "farm_id": ids["farm_id"], "area_id": ids["area_id"],
        "category_code": "electricity", "amount": "120.00", "occurred_on": "2026-08-10",
        "period_start": "2026-08-01", "period_end": "2026-08-31", "source_type": "expense", "source_ref": code,
        "target_type": "area", "target_id": ids["area_id"],
    }


def completed_allocation(settings: Any, ids: dict[str, int], area_id: int, pond_id: int, source_ref: str) -> int:
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,created_by,confirmed_by,confirmed_at) SELECT %s,%s,%s,id,10,'2026-08-10','2026-08-01','2026-08-31','confirmed','public','expense',%s,1,3,NOW() FROM cost_categories WHERE code='electricity'", (ids["organization_id"], ids["farm_id"], area_id, source_ref)); entry_id = int(cursor.lastrowid)
        cursor.execute("SELECT COALESCE(MAX(result_version),0)+1 AS version FROM cost_allocation_runs WHERE organization_id=%s AND farm_id=%s AND area_id=%s AND period_start='2026-08-01' AND period_end='2026-08-31'", (ids["organization_id"], ids["farm_id"], area_id))
        result_version = int(cursor.fetchone()["version"])
        cursor.execute("INSERT INTO cost_allocation_runs (organization_id,farm_id,area_id,period_start,period_end,rule_version_id,result_version,source_total,allocated_total,participant_snapshot_json,created_by) SELECT %s,%s,%s,'2026-08-01','2026-08-31',id,%s,10,10,JSON_ARRAY(),1 FROM cost_allocation_rule_versions WHERE status='active' ORDER BY version_no DESC LIMIT 1", (ids["organization_id"], ids["farm_id"], area_id, result_version)); run_id = int(cursor.lastrowid)
        cursor.execute("INSERT INTO cost_allocation_details (run_id,cost_entry_id,category_id,pond_id,amount,driver,driver_value,source_snapshot_json) SELECT %s,%s,category_id,%s,10,'equal',1,JSON_OBJECT('source_ref',source_ref) FROM cost_entries WHERE id=%s", (run_id, entry_id, pond_id, entry_id))
        return run_id


def test_settlement_uses_effective_corrected_delivery_quantity() -> None:
    with disposable_database("adp_cost_sales_correction", through=15) as database:
        settings = settings_for(database); ids = seed(settings); run_id = completed_allocation(settings, ids, ids["area_id"], ids["pond_1"], "EXP-CORRECTION")
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,quantity,weight_kg,happened_at,correction_of_id,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'harvest','CH1-C','更正出塘',%s,%s,8,8,'2026-08-18',%s,'verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["batch_id"], ids["pond_1"], ids["harvest_id"])); corrected_harvest = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_deliveries (organization_id,sales_order_id,harvest_document_id,harvest_root_id,code,name,quantity,delivered_at,correction_of_id,correction_reason,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,%s,'CSD1-C','更正交付',8,'2026-08-18',%s,'复核为8','verified',1,2,NOW())", (ids["organization_id"], ids["sales_order_id"], corrected_harvest, ids["harvest_id"], ids["delivery_id"]))
        maker = actor(1, "cost.view", "cost.settlement.manage"); maker["data_scopes"] = [{"scope_type": "area", "area_id": ids["area_id"]}]
        settlement = CostEnterpriseService(MySqlCostStore(settings)).create_settlement(maker, {"period_start": "2026-08-01", "period_end": "2026-08-31", "allocation_run_id": run_id})
        assert settlement["income_amount"] == "208.00"


def test_depreciation_assigns_final_cent_and_rejects_out_of_life_period() -> None:
    with disposable_database("adp_cost_depreciation", through=15) as database:
        settings = settings_for(database); ids = seed(settings)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO cost_assets (organization_id,farm_id,area_id,code,name,asset_type,category_id,purchase_date,original_value,salvage_value,useful_life_months,depreciation_start_date,allocation_driver,target_type,target_id,status,created_by,confirmed_by,confirmed_at) SELECT %s,%s,%s,'ASSET-ROUND','测试设备','equipment',id,'2026-08-01',100,0,3,'2026-09-01','equal','area',%s,'confirmed',1,3,NOW() FROM cost_categories WHERE code='equipment'", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["area_id"])); asset_id = int(cursor.lastrowid)
        maker = actor(1, "cost.asset.manage"); maker["data_scopes"] = [{"scope_type": "area", "area_id": ids["area_id"]}]
        service = CostEnterpriseService(MySqlCostStore(settings))
        amounts = [service.depreciate_asset(maker, asset_id, {"period": period})["amount"] for period in ("2026-09", "2026-10", "2026-11")]
        assert amounts == ["33.33", "33.33", "33.34"]
        with pytest.raises(DomainError, match="DEPRECIATION_PERIOD_INVALID"):
            service.depreciate_asset(maker, asset_id, {"period": "2026-12"})


def test_settlement_codes_are_unique_across_areas() -> None:
    with disposable_database("adp_cost_settlement_codes", through=15) as database:
        settings = settings_for(database); ids = seed(settings)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO areas (organization_id,farm_id,code,name,status,created_by) VALUES (%s,%s,'CC','结算二区','verified',1)", (ids["organization_id"], ids["farm_id"])); other_area = int(cursor.lastrowid)
            cursor.execute("INSERT INTO ponds (organization_id,farm_id,area_id,code,name,status,created_by) VALUES (%s,%s,%s,'CCP1','结算二区塘','verified',1)", (ids["organization_id"], ids["farm_id"], other_area)); other_pond = int(cursor.lastrowid)
        first_run = completed_allocation(settings, ids, ids["area_id"], ids["pond_1"], "EXP-CODE-1"); second_run = completed_allocation(settings, ids, other_area, other_pond, "EXP-CODE-2")
        service = CostEnterpriseService(MySqlCostStore(settings)); maker = actor(1, "cost.settlement.manage")
        maker["data_scopes"] = [{"scope_type": "area", "area_id": ids["area_id"]}]
        first = service.create_settlement(maker, {"period_start": "2026-08-01", "period_end": "2026-08-31", "allocation_run_id": first_run})
        maker["data_scopes"] = [{"scope_type": "area", "area_id": other_area}]
        second = service.create_settlement(maker, {"period_start": "2026-08-01", "period_end": "2026-08-31", "allocation_run_id": second_run})
        assert first["code"] != second["code"]


def test_real_mysql_cost_asset_allocation_settlement_chain() -> None:
    with disposable_database("adp_cost_enterprise", through=15) as database:
        settings = settings_for(database); ids = seed(settings); service = CostEnterpriseService(MySqlCostStore(settings))
        maker = actor(1, "cost.view", "cost.entry.manage", "cost.asset.manage", "cost.allocation.manage", "cost.settlement.manage")
        reviewer = actor(2, "cost.entry.verify", "cost.asset.verify", "cost.settlement.verify")
        approver = actor(3, "cost.entry.confirm", "cost.asset.confirm", "cost.entry.reverse", "cost.settlement.confirm", "cost.settlement.reverse")
        for current in (maker, reviewer, approver):
            current["data_scopes"] = [{"scope_type": "area", "area_id": ids["area_id"]}]

        row = service.create_expense(maker, expense(ids)); row = service.submit_expense(maker, row["id"], {"expected_version": row["version"]})
        row = service.update_expense(maker, row["id"], {**expense(ids), "amount": "150.00", "expected_version": row["version"]})
        task = one(settings, "SELECT target_version FROM work_items WHERE source_key=%s", (f"cost:entry:{row['id']}:verify",))
        assert task["target_version"] == row["version"]
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_type='cost:entry',entity_id=%s WHERE id=%s", (row["id"], ids["attachment_1"]))
        row = service.verify_expense(reviewer, row["id"], {"expected_version": row["version"], "evidence_attachment_ids": [ids["attachment_1"]]})
        row = service.confirm_expense(approver, row["id"], {"expected_version": row["version"], "evidence_attachment_ids": [ids["attachment_1"]]})
        assert row["status"] == "confirmed"
        late = service.create_expense(maker, expense(ids, "EXP-LATE")); late = service.submit_expense(maker, late["id"], {"expected_version": late["version"]})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_type='cost:entry',entity_id=%s WHERE id=%s", (late["id"], ids["attachment_2"]))
            cursor.execute("INSERT INTO areas (organization_id,farm_id,code,name,status,created_by) VALUES (%s,%s,'CB','其他成本区','verified',1)", (ids["organization_id"], ids["farm_id"]))
            other_area_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO cost_entries (organization_id,farm_id,area_id,category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,created_by,confirmed_by,confirmed_at) SELECT %s,%s,%s,id,900,'2026-08-10','2026-08-01','2026-08-31','confirmed','public','expense','EXP-OTHER-AREA',1,2,NOW() FROM cost_categories WHERE code='electricity'", (ids["organization_id"], ids["farm_id"], other_area_id))
        late = service.verify_expense(reviewer, late["id"], {"expected_version": late["version"], "evidence_attachment_ids": [ids["attachment_2"]]})

        run = service.run_allocation(maker, {"period_start": "2026-08-01", "period_end": "2026-08-31", "farm_id": ids["farm_id"], "area_id": ids["area_id"]})
        assert run["source_total"] == run["allocated_total"] == "150.00"
        assert [detail["amount"] for detail in run["details"]] == ["50.00", "50.00", "50.00"]
        assert all(detail["fallback_used"] for detail in run["details"])

        asset = service.create_asset(maker, {
            "organization_id": ids["organization_id"], "farm_id": ids["farm_id"], "area_id": ids["area_id"],
            "code": "ASSET-1", "name": "增氧机", "asset_type": "equipment", "category_code": "equipment",
            "purchase_date": "2026-08-01", "original_value": "1200.00", "salvage_value": "0.00",
            "useful_life_months": 12, "depreciation_start_date": "2026-09-01", "allocation_driver": "equal",
            "target_type": "area", "target_id": ids["area_id"],
        })
        asset = service._transition(maker, asset["id"], {"expected_version": asset["version"]}, kind="asset", before="draft", after="submitted", permission="cost.asset.manage")
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_type='cost:asset',entity_id=%s WHERE id=%s", (asset["id"], ids["attachment_3"]))
        asset = service._transition(reviewer, asset["id"], {"expected_version": asset["version"], "evidence_attachment_ids": [ids["attachment_3"]]}, kind="asset", before="submitted", after="verified", permission="cost.asset.verify")
        service._transition(approver, asset["id"], {"expected_version": asset["version"], "evidence_attachment_ids": [ids["attachment_3"]]}, kind="asset", before="verified", after="confirmed", permission="cost.asset.confirm")
        depreciation = service.depreciate_asset(maker, asset["id"], {"period": "2026-09"})
        assert depreciation["amount"] == "100.00"
        with pytest.raises(DomainError, match="DEPRECIATION_PERIOD_EXISTS"):
            service.depreciate_asset(maker, asset["id"], {"period": "2026-09"})

        settlement = service.create_settlement(maker, {"period_start": "2026-08-01", "period_end": "2026-08-31", "allocation_run_id": run["id"]})
        assert (settlement["income_amount"], settlement["cost_amount"], settlement["profit_amount"]) == ("260.00", "150.00", "110.00")
        assert {source["direction"] for source in settlement["sources"]} == {"income", "cost"}
        settlement = service.update_settlement(maker, settlement["id"], {"name": "八月正式结算", "expected_version": settlement["version"]})
        assert settlement["name"] == "八月正式结算"
        settlement = service.submit_settlement(maker, settlement["id"], {"expected_version": settlement["version"]})
        settlement = service.verify_settlement(reviewer, settlement["id"], {"expected_version": settlement["version"]})
        settlement = service.confirm_settlement(approver, settlement["id"], {"expected_version": settlement["version"]})
        with pytest.raises(DomainError, match="COST_PERIOD_LOCKED"):
            service.create_expense(maker, expense(ids, "EXP-LOCKED"))
        with pytest.raises(DomainError, match="COST_PERIOD_LOCKED"):
            service.confirm_expense(approver, late["id"], {"expected_version": late["version"], "evidence_attachment_ids": [ids["attachment_2"]]})
        service.reverse_settlement(approver, settlement["id"], {"expected_version": settlement["version"], "reason": "发现期末漏单，重新结算"})
        assert service.net_report(maker, {"period_start": "2026-08-01", "period_end": "2026-08-31"})["profit_amount"] == "0.00"
        reversal = service.reverse_expense(approver, row["id"], {"reason": "原费用录入错误"})
        assert reversal["reversal_of_id"] == row["id"]
        with pytest.raises(DomainError, match="COST_REVERSAL_EXISTS"):
            service.reverse_expense(approver, row["id"], {"reason": "重复冲销"})
        with pytest.raises(DomainError, match="COST_REVERSAL_NOT_ALLOWED"):
            service.reverse_expense(approver, reversal["id"], {"reason": "禁止冲销冲销单"})
        with pytest.raises(pymysql.OperationalError, match="formal cost asset"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE cost_assets SET original_value=1 WHERE id=%s", (asset["id"],))
        with pytest.raises(pymysql.OperationalError, match="formal cost asset"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE cost_assets SET purchase_date='2026-08-02' WHERE id=%s", (asset["id"],))
        with pytest.raises(pymysql.OperationalError, match="formal cost entry"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE cost_entries SET evidence_attachment_ids_json=JSON_ARRAY(999) WHERE id=%s", (row["id"],))
        with pytest.raises(pymysql.OperationalError, match="formal cost settlement"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE cost_settlements SET name='篡改名称' WHERE id=%s", (settlement["id"],))
        with pytest.raises(pymysql.OperationalError, match="allocation details are immutable"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("DELETE FROM cost_allocation_details WHERE run_id=%s LIMIT 1", (run["id"],))
        with pytest.raises(pymysql.OperationalError, match="settlement sources are immutable"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE cost_settlement_sources SET amount=1 WHERE settlement_id=%s LIMIT 1", (settlement["id"],))

        # A reversed settlement creates a new confirmed reversal entry; use a
        # fresh allocation result for the next settlement lifecycle.
        run_id = completed_allocation(settings, ids, ids["area_id"], ids["pond_1"], "EXP-REOPEN")
        draft = service.create_settlement(maker, {"period_start": "2026-08-01", "period_end": "2026-08-31", "allocation_run_id": run_id})
        service.delete_settlement(maker, draft["id"])
        assert one(settings, "SELECT COUNT(*) AS total FROM cost_settlements WHERE id=%s", (draft["id"],))["total"] == 0
        repeated = service.create_settlement(maker, {"period_start": "2026-08-01", "period_end": "2026-08-31", "allocation_run_id": run_id})
        repeated = service.submit_settlement(maker, repeated["id"], {"expected_version": repeated["version"]})
        repeated = service.verify_settlement(reviewer, repeated["id"], {"expected_version": repeated["version"]})
        repeated = service.confirm_settlement(approver, repeated["id"], {"expected_version": repeated["version"]})
        repeated = service.reverse_settlement(approver, repeated["id"], {"expected_version": repeated["version"], "reason": "第二轮重算仍有差异"})
        assert repeated["status"] == "reversed"
