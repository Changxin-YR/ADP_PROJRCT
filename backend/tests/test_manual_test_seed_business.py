from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from backend.scripts.manual_test_seed_accounts import seed_accounts
from backend.tests.mysql_test_database import disposable_database, run_mysql, settings_for


ROOT = Path(__file__).parents[2]
TABLES = (
    "production_batches", "production_documents", "warehouse_documents",
    "purchase_orders", "purchase_payments", "sales_orders", "sales_deliveries",
    "sales_receipts", "cost_entries", "cost_assets", "cost_settlements",
    "work_items", "notifications", "audit_logs",
)


def _count(cursor: Any, sql: str) -> int:
    cursor.execute(sql)
    return int(cursor.fetchone()["total"])


def _snapshot(cursor: Any) -> dict[str, int]:
    return {table: _count(cursor, f"SELECT COUNT(*) AS total FROM {table}") for table in TABLES}


def _register_migrations(cursor: Any) -> None:
    rows = []
    for path in sorted((ROOT / "database/migrations").glob("[0-9][0-9][0-9]_*.sql")):
        if path.name != "000_schema_migrations.sql":
            rows.append((path.stem, hashlib.sha256(path.read_bytes()).hexdigest()))
    cursor.executemany(
        "INSERT INTO schema_migrations (version,checksum) VALUES (%s,%s)", rows
    )


def test_manual_business_seed_is_complete_idempotent_and_reconciled(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    from backend.scripts.manual_test_seed_business import seed_business
    from backend.scripts.reconcile_enterprise_data import reconcile

    attachment_dir = tmp_path / "attachments"
    monkeypatch.setenv("ADP_MANUAL_TEST_ATTACHMENT_DIR", str(attachment_dir))
    with disposable_database("adp_manual_test_business", through=21) as database:
        run_mysql(f"--database={database}", sql=(ROOT / "database/seed_reference.sql").read_bytes())
        settings = settings_for(database)
        connection = pymysql.connect(
            host=settings.mysql_host, port=settings.mysql_port, user=settings.mysql_user,
            password=settings.mysql_password, database=database, charset="utf8mb4",
            cursorclass=DictCursor, autocommit=False,
        )
        try:
            with connection.cursor() as cursor:
                _register_migrations(cursor)
                seed_accounts(cursor, "manual-test-password")
                seed_business(cursor, "manual-test-password")
            connection.commit()
            with connection.cursor() as cursor:
                first = _snapshot(cursor)
                seed_business(cursor, "manual-test-password")
            connection.commit()
            with connection.cursor() as cursor:
                second = _snapshot(cursor)
                _assert_lifecycle(cursor)
                cursor.execute(
                    "SELECT sha256,storage_name FROM attachments "
                    "WHERE original_name='manual-test-voucher.txt' LIMIT 1"
                )
                attachment = cursor.fetchone()
            reconciliation = reconcile(connection, ROOT / "database/migrations")
        finally:
            connection.close()

    assert first == second
    assert all(first[table] > 0 for table in TABLES)
    assert reconciliation["ok"] is True
    assert reconciliation["total_issues"] == 0
    evidence = attachment_dir / attachment["storage_name"]
    assert evidence.is_file()
    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == attachment["sha256"]


def _assert_lifecycle(cursor: Any) -> None:
    for table in ("production_documents", "warehouse_documents"):
        for status in ("draft", "submitted", "verified"):
            assert _count(cursor, f"SELECT COUNT(*) AS total FROM {table} WHERE status='{status}'") > 0
    for table in ("purchase_orders", "sales_orders"):
        for status in ("draft", "submitted", "approved"):
            assert _count(cursor, f"SELECT COUNT(*) AS total FROM {table} WHERE status='{status}'") > 0
    for table in ("purchase_payments", "sales_deliveries", "sales_receipts"):
        assert _count(cursor, f"SELECT COUNT(*) AS total FROM {table} WHERE status='verified'") > 0
    assert _count(cursor, "SELECT COUNT(*) AS total FROM cost_entries WHERE status IN ('draft','submitted','verified','confirmed')") >= 4
    assert _count(cursor, "SELECT COUNT(*) AS total FROM cost_assets WHERE status='verified'") > 0
    assert _count(cursor, "SELECT COUNT(*) AS total FROM cost_settlements WHERE status='reversed'") > 0
    assert _count(cursor, "SELECT COUNT(*) AS total FROM production_documents WHERE correction_of_id IS NOT NULL") > 0
    assert _count(cursor, "SELECT COUNT(*) AS total FROM purchase_payment_reversals") > 0
    assert _count(cursor, "SELECT COUNT(*) AS total FROM sales_receipt_reversals") > 0
    assert _count(cursor, "SELECT COUNT(*) AS total FROM work_items WHERE status='pending'") > 0
    assert _count(cursor, "SELECT COUNT(*) AS total FROM work_items WHERE status='completed'") > 0
    cursor.execute(
        "SELECT d.id,d.row_version,w.target_version,w.source_key FROM production_documents d "
        "JOIN work_items w ON w.object_type='production:samplings' AND w.object_id=d.id "
        "WHERE d.code='TEST-20260817-PROD-SUBMITTED'"
    )
    pending = cursor.fetchone()
    assert pending["source_key"] == f"production:samplings:{pending['id']}:verify"
    assert pending["target_version"] == pending["row_version"]
