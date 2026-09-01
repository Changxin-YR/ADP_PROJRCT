from __future__ import annotations

import hashlib
from pathlib import Path

import pymysql

from backend.layers.common.db.connection import get_connection
from backend.tests.mysql_test_database import disposable_database, run_mysql, settings_for


REQUIRED_CHECKS = {
    "foreign_key_orphans",
    "duplicate_unique_keys",
    "illegal_workflow_state",
    "negative_inventory",
    "negative_batch_stock",
    "batch_stock_source_mismatch",
    "payable_payment_difference",
    "receivable_receipt_difference",
    "cost_allocation_difference",
    "work_item_state_mismatch",
    "self_approval",
    "missing_required_voucher",
    "immutability_trigger_missing",
    "migration_checksum_drift",
}


def _module():
    from backend.scripts import reconcile_enterprise_data

    return reconcile_enterprise_data


def test_reconciliation_declares_every_enterprise_control():
    assert REQUIRED_CHECKS == set(_module().CHECK_NAMES)


def test_migration_checksums_match_registered_values(tmp_path):
    migration = tmp_path / "001_example.sql"
    migration.write_text("SELECT 1;\n", encoding="utf-8")
    expected = hashlib.sha256(migration.read_bytes()).hexdigest()
    assert _module().compare_migration_checksums({"001_example": expected}, tmp_path) == []
    assert _module().compare_migration_checksums({"001_example": "0" * 64}, tmp_path) == ["001_example: checksum mismatch"]


def test_migration_checksums_treat_lf_and_crlf_as_the_same_sql(tmp_path):
    migration = tmp_path / "001_example.sql"
    migration.write_bytes(b"SELECT 1;\n")
    legacy_crlf = hashlib.sha256(b"SELECT 1;\r\n").hexdigest()

    assert _module().compare_migration_checksums({"001_example": legacy_crlf}, tmp_path) == []


def test_reconciliation_runs_against_disposable_mysql():
    with disposable_database("adp_reconcile", through=20) as database:
        settings = settings_for(database)
        connection = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            migrations = sorted(Path("database/migrations").glob("[0-9][0-9][0-9]_*.sql"))
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO schema_migrations (version,checksum) VALUES (%s,%s)",
                    [(path.stem, hashlib.sha256(path.read_bytes()).hexdigest()) for path in migrations if path.name != "000_schema_migrations.sql"],
                )
            connection.commit()
            result = _module().reconcile(connection, Path("database/migrations"))
        finally:
            connection.close()
    assert result["checks"] == {name: 0 for name in REQUIRED_CHECKS}
    assert result["ok"] is True
    assert result["total_issues"] == 0


def test_self_approval_ignores_the_verifier_as_last_editor():
    with disposable_database("adp_reconcile_self_approval", through=30) as database:
        settings = settings_for(database)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO users (phone,name,password_hash,status) VALUES (%s,%s,'hash','active')",
                [("13910000001", "批次经办",), ("13910000002", "批次核验",)],
            )
            cursor.execute("SELECT id FROM users ORDER BY id")
            creator_id, reviewer_id = [int(row["id"]) for row in cursor.fetchall()]
            cursor.execute("SELECT id,organization_id FROM farms WHERE code='default-farm'")
            farm = cursor.fetchone()
            cursor.execute(
                "INSERT INTO areas (organization_id,farm_id,code,name,status) VALUES (%s,%s,'reconcile-area','对账基地','verified')",
                (farm["organization_id"], farm["id"]),
            )
            area_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO ponds (organization_id,farm_id,area_id,code,name,status,created_by) VALUES (%s,%s,%s,'RECON-POND','对账塘','verified',%s)",
                (farm["organization_id"], farm["id"], area_id, creator_id),
            )
            pond_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO production_batches (organization_id,farm_id,area_id,pond_id,code,name,species,status,created_by,updated_by,verified_by,verified_at) VALUES (%s,%s,%s,%s,'RECON-BATCH','对账批次','草鱼','verified',%s,%s,%s,NOW())",
                (farm["organization_id"], farm["id"], area_id, pond_id, creator_id, reviewer_id, reviewer_id),
            )
            assert _module()._count(cursor, _module().STATIC_CHECKS["self_approval"]) == 0
            cursor.execute(
                "INSERT INTO production_batches (organization_id,farm_id,area_id,pond_id,code,name,species,status,created_by,updated_by,verified_by,verified_at) VALUES (%s,%s,%s,%s,'RECON-SELF','自审批次','草鱼','verified',%s,%s,%s,NOW())",
                (farm["organization_id"], farm["id"], area_id, pond_id, reviewer_id, reviewer_id, reviewer_id),
            )
            assert _module()._count(cursor, _module().STATIC_CHECKS["self_approval"]) == 1


def test_reference_seed_supports_the_current_schema_and_area_lookup():
    from backend.layers.common.db.repositories.review_repository import ReviewRepository

    with disposable_database("adp_reference_seed", through=20) as database:
        seed = Path("database/seed_reference.sql").read_bytes()
        run_mysql(f"--database={database}", sql=seed)
        run_mysql(f"--database={database}", sql=seed)
        settings = settings_for(database)
        connection = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            areas = ReviewRepository().list_areas(connection)
        finally:
            connection.close()

    assert [(row["code"], row["name"]) for row in areas] == [
        ("north-farm", "北区基地"),
        ("south-farm", "南区基地"),
    ]


def test_full_migrations_do_not_seed_placeholder_business_entries():
    with disposable_database("adp_clean_production", through=21) as database:
        settings = settings_for(database)
        connection = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM cost_entries "
                    "WHERE source_type='legacy_import' AND source_ref='LEGACY-INIT-2026'"
                )
                total = int(cursor.fetchone()["total"])
        finally:
            connection.close()

    assert total == 0
