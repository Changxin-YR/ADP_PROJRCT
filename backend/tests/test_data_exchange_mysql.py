from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pymysql
import pytest
from openpyxl import Workbook

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.data_exchange.data_exchange_service import DataExchangeService
from backend.layers.features.data_exchange.data_exchange_store import MySqlDataExchangeStore
from backend.layers.features.production.production_store import MySqlProductionStore
from backend.tests.mysql_test_database import disposable_database, settings_for


def workbook(rows: list[list[Any]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(["code", "name", "category", "unit"])
    for row in rows:
        sheet.append(row)
    output = BytesIO(); book.save(output)
    return output.getvalue()


def actor() -> dict[str, Any]:
    return {
        "id": 1, "name": "数据管理员",
        "permissions": ["data_exchange.view", "data_exchange.import", "data_exchange.export", "attachment.manage"],
        "data_scopes": [],
    }


def scalar(settings: Any, sql: str, params: tuple[Any, ...] = ()) -> int:
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return int(next(iter(cursor.fetchone().values())))


def test_real_mysql_import_preview_catches_conflicts_and_confirm_still_rolls_back_races(tmp_path: Path) -> None:
    with disposable_database("adp_data_exchange", through=17) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO users (phone,name,password_hash,status) VALUES ('13980000001','数据管理员','hash','active')")
            cursor.execute("SELECT id FROM organizations WHERE code='default'")
            organization_id = int(cursor.fetchone()["id"])
        service = DataExchangeService(MySqlDataExchangeStore(settings), tmp_path)
        user = actor()

        ready = service.preview(user, organization_id=organization_id, template_code="materials", file_name="valid.xlsx", content=workbook([["MAT-IMPORT-1", "一号饲料", "饲料", "kg"]]))
        assert ready["status"] == "ready"
        imported = service.confirm(user, ready["id"])
        assert imported["status"] == "imported"
        assert scalar(settings, "SELECT COUNT(*) AS total FROM materials WHERE code='MAT-IMPORT-1' AND status='draft'") == 1

        # BUG-008：确认阶段才出现的编号冲突必须提前到预览阶段。
        duplicate = service.preview(user, organization_id=organization_id, template_code="materials", file_name="conflict.xlsx", content=workbook([["MAT-IMPORT-2", "二号饲料", "饲料", "kg"], ["MAT-IMPORT-1", "重复饲料", "饲料", "kg"]]))
        assert duplicate["status"] == "invalid"
        assert any("业务编号已存在" in item["message"] for item in duplicate["errors"])
        with pytest.raises(DomainError, match="IMPORT_NOT_READY"):
            service.confirm(user, duplicate["id"])

        # 预览通过后、确认前被他人抢注同一编号：确认阶段仍然整批回滚。
        race = service.preview(user, organization_id=organization_id, template_code="materials", file_name="race.xlsx", content=workbook([["MAT-IMPORT-3", "三号饲料", "饲料", "kg"]]))
        assert race["status"] == "ready"
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO materials (organization_id,code,name,category,unit,created_by) VALUES (%s,'MAT-IMPORT-3','抢注饲料','饲料','kg',1)", (organization_id,))
        with pytest.raises(DomainError, match="IMPORT_RECORD_CONFLICT"):
            service.confirm(user, race["id"])
        assert scalar(settings, "SELECT COUNT(*) AS total FROM data_import_batches WHERE id=%s AND status='ready'", (race["id"],)) == 1

        content, export_id = service.export(user, organization_id=organization_id, resource="materials", file_format="xlsx", filters={"status": "draft"}, request_id="mysql-export")
        assert content.startswith(b"PK") and export_id > 0
        with pytest.raises(pymysql.OperationalError, match="append-only"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE data_export_audits SET row_count=0 WHERE id=%s", (export_id,))
        with pytest.raises(pymysql.OperationalError, match="append-only"):
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("DELETE FROM data_export_audits WHERE id=%s", (export_id,))


def workbook_with(header: list[str], rows: list[list[Any]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    output = BytesIO(); book.save(output)
    return output.getvalue()


def test_real_mysql_revoke_deletes_drafts_and_blocks_referenced_batches(tmp_path: Path) -> None:
    with disposable_database("adp_data_exchange_revoke", through=17) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO users (phone,name,password_hash,status) VALUES ('13980000001','数据管理员','hash','active')")
            cursor.execute("SELECT id FROM organizations WHERE code='default'")
            organization_id = int(cursor.fetchone()["id"])
        service = DataExchangeService(MySqlDataExchangeStore(settings), tmp_path)
        user = actor()

        ready = service.preview(user, organization_id=organization_id, template_code="materials", file_name="revoke.xlsx", content=workbook([["MAT-REVOKE-1", "可撤销饲料", "饲料", "kg"]]))
        imported = service.confirm(user, ready["id"])
        assert imported["status"] == "imported"
        assert scalar(settings, "SELECT COUNT(*) AS total FROM materials WHERE code='MAT-REVOKE-1' AND status='draft'") == 1

        undone = service.revoke(user, ready["id"])
        assert undone["status"] == "undone" and undone["imported_count"] == 0
        assert scalar(settings, "SELECT COUNT(*) AS total FROM materials WHERE code='MAT-REVOKE-1'") == 0
        assert scalar(settings, "SELECT COUNT(*) AS total FROM data_import_items WHERE import_batch_id=%s", (ready["id"],)) == 0
        assert scalar(settings, "SELECT COUNT(*) AS total FROM audit_logs WHERE action='revoke_import' AND object_id=%s", (ready["id"],)) == 1

        # 被后续业务引用（已提交核验）的批次不能撤销 → 409。
        referenced = service.preview(user, organization_id=organization_id, template_code="materials", file_name="referenced.xlsx", content=workbook([["MAT-REVOKE-2", "被引用饲料", "饲料", "kg"]]))
        service.confirm(user, referenced["id"])
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE materials SET status='submitted' WHERE code='MAT-REVOKE-2'")
        with pytest.raises(DomainError, match="IMPORT_REVOKE_REFERENCED"):
            service.revoke(user, referenced["id"])
        assert scalar(settings, "SELECT COUNT(*) AS total FROM materials WHERE code='MAT-REVOKE-2' AND status='submitted'") == 1
        assert scalar(settings, "SELECT COUNT(*) AS total FROM data_import_batches WHERE id=%s AND status='imported'", (referenced["id"],)) == 1


def test_real_mysql_production_templates_preview_and_import_drafts(tmp_path: Path) -> None:
    with disposable_database("adp_data_exchange_prod", through=17) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO users (phone,name,password_hash,status) VALUES ('13980000001','数据管理员','hash','active')")
            cursor.execute("SELECT id FROM organizations WHERE code='default'")
            organization_id = int(cursor.fetchone()["id"])
            cursor.execute("SELECT id FROM farms WHERE organization_id=%s ORDER BY id LIMIT 1", (organization_id,))
            farm_id = int(cursor.fetchone()["id"])
            cursor.execute("INSERT INTO areas (organization_id,farm_id,code,name,status,row_version,created_by) VALUES (%s,%s,'AREA-IMP-1','导入区域','verified',1,1)", (organization_id, farm_id))
            area_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO ponds (organization_id,farm_id,area_id,code,name,capacity_mu,status,row_version,created_by) VALUES (%s,%s,%s,'POND-IMP-1','导入塘口',3.5,'verified',1,1)", (organization_id, farm_id, area_id))
            pond_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO materials (organization_id,code,name,category,unit,status,row_version,created_by) VALUES (%s,'FEED-IMP-1','导入饲料','饲料','kg','verified',1,1)", (organization_id,))
            material_id = int(cursor.lastrowid)
        service = DataExchangeService(MySqlDataExchangeStore(settings), tmp_path)
        user = actor()

        # 批次模板：正确文件可预览可确认，形成草稿批次。
        batches = service.preview(user, organization_id=organization_id, template_code="batches", file_name="batches.xlsx", content=workbook_with(["code", "species", "pond_id", "happened_at", "quantity"], [["BATCH-IMP-1", "草鱼", pond_id, "2026-08-17", 1000]]))
        assert batches["status"] == "ready", batches["errors"]
        imported = service.confirm(user, batches["id"])
        assert imported["status"] == "imported"
        assert scalar(settings, "SELECT COUNT(*) AS total FROM production_batches WHERE code='BATCH-IMP-1' AND status='draft'") == 1

        # 投苗导入必须形成可撤销、待核验的更正草稿，不能直接写正式存塘流水。
        batch_id = scalar(settings, "SELECT id FROM production_batches WHERE code='BATCH-IMP-1'")
        service.upload_attachment(user, organization_id=organization_id, entity_type="production:batches", entity_id=batch_id, file_name="batch.pdf", media_type="application/pdf", content=b"%PDF-1.4\n%%EOF\n")
        with pytest.raises(DomainError, match="ATTACHMENT_DUPLICATE"):
            service.upload_attachment(user, organization_id=organization_id, entity_type="production:batches", entity_id=batch_id, file_name="batch-copy.pdf", media_type="application/pdf", content=b"%PDF-1.4\n%%EOF\n")
        assert scalar(settings, "SELECT COUNT(*) AS total FROM attachments WHERE entity_type='production:batches' AND entity_id=%s", (batch_id,)) == 1
        production = MySqlProductionStore(settings)
        production.set_status("batches", batch_id, "submitted", expected_version=1, user_id=1)
        production.set_status("batches", batch_id, "verified", expected_version=2, user_id=1)
        stocking = service.preview(user, organization_id=organization_id, template_code="stocking", file_name="stocking.xlsx", content=workbook_with(["code", "batch_id", "quantity", "happened_at"], [["STOCK-IMP-1", batch_id, 200, "2026-08-18"]]))
        assert stocking["status"] == "ready", stocking["errors"]
        imported_stocking = service.confirm(user, stocking["id"])
        assert imported_stocking["status"] == "imported"
        assert scalar(settings, "SELECT SUM(quantity_delta) AS total FROM batch_stock_records WHERE batch_id=%s", (batch_id,)) == 1000
        assert scalar(settings, "SELECT COUNT(*) AS total FROM production_batches WHERE correction_of_id=%s AND code='STOCK-IMP-1' AND status='draft'", (batch_id,)) == 1
        service.revoke(user, stocking["id"])
        assert scalar(settings, "SELECT COUNT(*) AS total FROM production_batches WHERE correction_of_id=%s", (batch_id,)) == 0
        stocking2 = service.preview(user, organization_id=organization_id, template_code="stocking", file_name="stocking-verified.xlsx", content=workbook_with(["code", "batch_id", "quantity", "happened_at"], [["STOCK-IMP-2", batch_id, 200, "2026-08-18"]]))
        imported_stocking2 = service.confirm(user, stocking2["id"])
        correction_id = scalar(settings, "SELECT id FROM production_batches WHERE correction_of_id=%s", (batch_id,))
        production.set_status("batches", correction_id, "submitted", expected_version=1, user_id=1)
        production.set_status("batches", correction_id, "verified", expected_version=2, user_id=1)
        assert scalar(settings, "SELECT SUM(quantity_delta) AS total FROM batch_stock_records WHERE batch_id=%s", (batch_id,)) == 1200
        with pytest.raises(DomainError, match="IMPORT_REVOKE_REFERENCED"):
            service.revoke(user, imported_stocking2["id"])

        # 错误文件：不存在的塘口 + 文件内重复编号，预览阶段全部给出中文逐行错误。
        bad = service.preview(user, organization_id=organization_id, template_code="batches", file_name="bad-batches.xlsx", content=workbook_with(["code", "species", "pond_id", "happened_at", "quantity"], [["BATCH-BAD-1", "草鱼", 99999, "2026-08-17", 10], ["BATCH-BAD-1", "草鱼", pond_id, "2026-08-17", 10]]))
        assert bad["status"] == "invalid"
        messages = [(item["row"], item["column"], item["message"]) for item in bad["errors"]]
        assert any("塘口不存在" in message for _row, _column, message in messages)
        assert any("文件内业务编号重复" in message for _row, _column, message in messages)
        with pytest.raises(DomainError, match="IMPORT_NOT_READY"):
            service.confirm(user, bad["id"])

        # 喂养记录模板：关联批次/塘口/物料写入草稿单据。
        feed = service.preview(user, organization_id=organization_id, template_code="feed-logs", file_name="feed-logs.xlsx", content=workbook_with(["code", "pond_id", "material_id", "quantity", "happened_at"], [["FEEDLOG-IMP-1", pond_id, material_id, 25, "2026-08-18"]]))
        assert feed["status"] == "ready", feed["errors"]
        imported_feed = service.confirm(user, feed["id"])
        assert imported_feed["status"] == "imported"
        assert scalar(settings, "SELECT COUNT(*) AS total FROM production_documents WHERE code='FEEDLOG-IMP-1' AND document_type='feed_log' AND status='draft'") == 1

        # 撤销后生产草稿一并删除。
        undone = service.revoke(user, imported_feed["id"])
        assert undone["status"] == "undone"
        assert scalar(settings, "SELECT COUNT(*) AS total FROM production_documents WHERE code='FEEDLOG-IMP-1'") == 0

        # 新增导出资源（batches / feed-logs）可用。
        content, _export_id = service.export(user, organization_id=organization_id, resource="batches", file_format="xlsx", filters={}, request_id="prod-export")
        assert content.startswith(b"PK")


def test_real_mysql_purchase_and_sales_order_imports_confirm_drafts(tmp_path: Path) -> None:
    with disposable_database("adp_exchange_orders", through=17) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO users (phone,name,password_hash,status) VALUES ('13980000001','数据管理员','hash','active')")
            cursor.execute("SELECT id FROM organizations WHERE code='default'")
            organization_id = int(cursor.fetchone()["id"])
            cursor.execute("SELECT id FROM farms WHERE organization_id=%s ORDER BY id LIMIT 1", (organization_id,))
            farm_id = int(cursor.fetchone()["id"])
            cursor.execute("INSERT INTO areas (organization_id,farm_id,code,name,status,row_version,created_by) VALUES (%s,%s,'AREA-ORDER','订单区域','verified',1,1)", (organization_id, farm_id))
            area_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO warehouses (organization_id,farm_id,area_id,code,name) VALUES (%s,%s,%s,'WH-ORDER','订单仓')", (organization_id, farm_id, area_id))
            warehouse_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO materials (organization_id,code,name,category,unit,status,row_version,created_by) VALUES (%s,'MAT-ORDER','订单物料','饲料','kg','verified',1,1)", (organization_id,))
            material_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO business_partners (organization_id,partner_type,code,name,status,row_version,created_by) VALUES (%s,'supplier','SUP-ORDER','订单供应商','verified',1,1),(%s,'customer','CUS-ORDER','订单客户','verified',1,1)", (organization_id, organization_id))
            supplier_id = int(cursor.lastrowid)
            customer_id = supplier_id + 1
            cursor.execute("INSERT INTO ponds (organization_id,farm_id,area_id,code,name,status,row_version,created_by) VALUES (%s,%s,%s,'POND-ORDER','订单塘','verified',1,1)", (organization_id, farm_id, area_id))
            pond_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO production_batches (organization_id,farm_id,area_id,pond_id,code,name,species,initial_quantity,batch_status,status,row_version,created_by) VALUES (%s,%s,%s,%s,'BATCH-ORDER','订单批次','鲈鱼',100,'farming','verified',1,1)", (organization_id, farm_id, area_id, pond_id))
            batch_id = int(cursor.lastrowid)
        service = DataExchangeService(MySqlDataExchangeStore(settings), tmp_path)
        user = actor()
        purchase = service.preview(user, organization_id=organization_id, template_code="purchase-orders", file_name="purchase.xlsx", content=workbook_with(
            ["code", "supplier_id", "material_id", "warehouse_id", "quantity", "unit_price"],
            [["PO-IMPORT-REAL", supplier_id, material_id, warehouse_id, 2, 3]],
        ))
        assert purchase["status"] == "ready", purchase["errors"]
        service.confirm(user, purchase["id"])
        assert scalar(settings, "SELECT COUNT(*) AS total FROM purchase_orders WHERE code='PO-IMPORT-REAL' AND total_amount=6 AND status='draft'") == 1
        sale = service.preview(user, organization_id=organization_id, template_code="sales-orders", file_name="sale.xlsx", content=workbook_with(
            ["code", "customer_id", "batch_id", "quantity", "unit_price"],
            [["SO-IMPORT-REAL", customer_id, batch_id, 2, 3]],
        ))
        assert sale["status"] == "ready", sale["errors"]
        service.confirm(user, sale["id"])
        assert scalar(settings, "SELECT COUNT(*) AS total FROM sales_orders WHERE code='SO-IMPORT-REAL' AND total_amount=6 AND status='draft'") == 1
