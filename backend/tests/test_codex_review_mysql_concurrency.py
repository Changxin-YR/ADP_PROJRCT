from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from typing import Any, Callable

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.production.production_store import MySqlProductionStore
from backend.layers.features.warehouse.warehouse_store import MySqlWarehouseStore
from backend.tests.mysql_test_database import disposable_database, settings_for
from test_warehouse_mysql_integration import _seed


def _race(first: Callable[[], Any], second: Callable[[], Any]) -> list[Any]:
    barrier = Barrier(2)

    def run(operation: Callable[[], Any]) -> Any:
        barrier.wait()
        try:
            return operation()
        except DomainError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        return [future.result() for future in (pool.submit(run, first), pool.submit(run, second))]


def test_concurrent_production_losses_cannot_overdraw_same_batch_stock() -> None:
    with disposable_database("adp_prod_race", through=10) as database:
        settings = settings_for(database)
        ids = _seed(settings)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO batch_stock_records (organization_id,batch_id,pond_id,source_type,source_id,line_no,quantity_delta,weight_delta_kg,posted_by) VALUES (%s,%s,%s,'stocking',%s,1,10,10,1)",
                (ids["organization_id"], ids["batch_id"], ids["pond_id"], ids["batch_id"]),
            )
            cursor.executemany(
                "INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,quantity,weight_kg,status,row_version,created_by) VALUES (%s,%s,%s,'loss',%s,%s,%s,%s,7,7,'submitted',1,1)",
                [
                    (ids["organization_id"], ids["farm_id"], ids["area_id"], "LOSS-RACE-1", "并发损耗1", ids["batch_id"], ids["pond_id"]),
                    (ids["organization_id"], ids["farm_id"], ids["area_id"], "LOSS-RACE-2", "并发损耗2", ids["batch_id"], ids["pond_id"]),
                ],
            )
            cursor.execute("SELECT id FROM production_documents WHERE code LIKE 'LOSS-RACE-%' ORDER BY id")
            first_id, second_id = [int(row["id"]) for row in cursor.fetchall()]
            cursor.executemany(
                "INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,'production:losses',%s,%s,%s,%s,'application/pdf',10,1)",
                [
                    (ids["organization_id"], first_id, "1" * 64, "1" * 32, "loss-1.pdf"),
                    (ids["organization_id"], second_id, "2" * 64, "2" * 32, "loss-2.pdf"),
                ],
            )
            cursor.execute("SELECT id FROM attachments WHERE entity_type='production:losses' ORDER BY id")
            first_attachment, second_attachment = [int(row["id"]) for row in cursor.fetchall()]
        store = MySqlProductionStore(settings)
        results = _race(
            lambda: store.set_status("losses", first_id, "verified", expected_version=1, user_id=2, evidence_attachment_ids=[first_attachment]),
            lambda: store.set_status("losses", second_id, "verified", expected_version=1, user_id=2, evidence_attachment_ids=[second_attachment]),
        )
        outcomes = [(type(result).__name__, getattr(result, "code", None), str(result)) for result in results]
        assert sum(isinstance(result, DomainError) and result.code == "BATCH_STOCK_INSUFFICIENT" for result in results) == 1, outcomes
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT SUM(quantity_delta) AS balance FROM batch_stock_records WHERE batch_id=%s", (ids["batch_id"],))
            assert cursor.fetchone()["balance"] == Decimal("3.000")
            cursor.execute("SELECT COUNT(*) AS total FROM production_documents WHERE code LIKE 'LOSS-RACE-%' AND status='verified'")
            assert int(cursor.fetchone()["total"]) == 1


def test_concurrent_warehouse_transfers_cannot_overdraw_same_inventory_lot() -> None:
    with disposable_database("adp_wh_race", through=10) as database:
        settings = settings_for(database)
        ids = _seed(settings)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO inventory_lots (organization_id,material_id,lot_no,unit_cost) VALUES (%s,%s,'RACE-LOT',1)",
                (ids["organization_id"], ids["material_id"]),
            )
            lot_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO inventory_ledger (organization_id,warehouse_id,material_id,inventory_lot_id,source_type,source_id,line_no,quantity_delta,unit_cost,posted_by) VALUES (%s,%s,%s,%s,'receipt',999,1,10,1,1)",
                (ids["organization_id"], ids["warehouse_1"], ids["material_id"], lot_id),
            )
            cursor.executemany(
                "INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,target_warehouse_id,material_id,inventory_lot_id,quantity,status,row_version,created_by) VALUES (%s,%s,%s,'transfer',%s,%s,%s,%s,%s,%s,7,'submitted',1,1)",
                [
                    (ids["organization_id"], ids["farm_id"], ids["area_id"], "TRANSFER-RACE-1", "并发调拨1", ids["warehouse_1"], ids["warehouse_2"], ids["material_id"], lot_id),
                    (ids["organization_id"], ids["farm_id"], ids["area_id"], "TRANSFER-RACE-2", "并发调拨2", ids["warehouse_1"], ids["warehouse_2"], ids["material_id"], lot_id),
                ],
            )
            cursor.execute("SELECT id FROM warehouse_documents WHERE code LIKE 'TRANSFER-RACE-%' ORDER BY id")
            first_id, second_id = [int(row["id"]) for row in cursor.fetchall()]
        store = MySqlWarehouseStore(settings)
        results = _race(
            lambda: store.dispatch_transfer(first_id, expected_version=1, user_id=2),
            lambda: store.dispatch_transfer(second_id, expected_version=1, user_id=2),
        )
        outcomes = [(type(result).__name__, getattr(result, "code", None), str(result)) for result in results]
        assert sum(isinstance(result, DomainError) and result.code == "WAREHOUSE_STOCK_INSUFFICIENT" for result in results) == 1, outcomes
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT SUM(quantity_delta) AS balance FROM inventory_ledger WHERE inventory_lot_id=%s AND warehouse_id=%s", (lot_id, ids["warehouse_1"]))
            assert cursor.fetchone()["balance"] == Decimal("3.000")
            cursor.execute("SELECT COUNT(*) AS total FROM warehouse_documents WHERE code LIKE 'TRANSFER-RACE-%' AND status='in_transit'")
            assert int(cursor.fetchone()["total"]) == 1
