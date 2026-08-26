from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from werkzeug.security import generate_password_hash

from backend.scripts.readiness.common import (
    ReadinessFailure,
    evidence,
    require_disposable_database_name,
)
from backend.scripts.reconcile_enterprise_data import reconcile
from backend.scripts.readiness.mysql_tools import (
    DatabaseTools,
    apply_migrations,
    apply_sql,
    connect_database,
    execute_sql,
    require_database_tools,
    run_database_command,
)


ROOT = Path(__file__).resolve().parents[3]
MIGRATION_DIR = ROOT / "database" / "migrations"
SEED_FILES = (ROOT / "database" / "seed_reference.sql", ROOT / "database" / "seed_dev.sql")
CRITICAL_TABLES = (
    "organizations",
    "farms",
    "areas",
    "ponds",
    "users",
    "roles",
    "permissions",
    "business_settings",
    "inventory_ledger",
    "batch_stock_records",
    "purchase_payables",
    "sales_receivables",
    "cost_entries",
    "audit_logs",
)


@dataclass(frozen=True)
class DatabaseSnapshot:
    migrations: dict[str, str]
    table_counts: dict[str, int]
    aggregates: dict[str, str]


def dump_arguments(database: str) -> list[str]:
    return [
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--set-gtid-purged=OFF",
        database,
    ]


def _mapping_differences(prefix: str, source: Mapping[str, Any], restored: Mapping[str, Any]) -> list[str]:
    differences: list[str] = []
    for key in sorted(set(source) | set(restored)):
        before, after = source.get(key), restored.get(key)
        if before != after:
            differences.append(f"{prefix}.{key}: source={before} restore={after}")
    return differences


def compare_snapshots(source: DatabaseSnapshot, restored: DatabaseSnapshot) -> list[str]:
    return [
        *_mapping_differences("migrations", source.migrations, restored.migrations),
        *_mapping_differences("table_counts", source.table_counts, restored.table_counts),
        *_mapping_differences("aggregates", source.aggregates, restored.aggregates),
    ]


def _seed_traceable_record(tools: DatabaseTools, database: str) -> None:
    connection = connect_database(tools, database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users(phone,login_name,name,password_hash,status) VALUES "
                "('13999999990','TEST_READINESS_BACKUP','TEST_READINESS_备份恢复',%s,'active')",
                (generate_password_hash(uuid4().hex, method="scrypt"),),
            )
            user_id = int(cursor.lastrowid)
            cursor.execute("SELECT id FROM organizations ORDER BY id LIMIT 1")
            organization_id = int(cursor.fetchone()["id"])
            cursor.execute("SELECT id FROM farms WHERE organization_id=%s ORDER BY id LIMIT 1", (organization_id,))
            farm_id = int(cursor.fetchone()["id"])
            cursor.execute("SELECT id FROM areas WHERE organization_id=%s ORDER BY id LIMIT 1", (organization_id,))
            area_id = int(cursor.fetchone()["id"])
            cursor.execute(
                "INSERT INTO business_settings(organization_id,farm_id,area_id,code,name,group_code,value_text,status,created_by) "
                "VALUES (%s,%s,%s,'TEST_READINESS_BACKUP','TEST_READINESS_备份恢复','readiness','snapshot','draft',%s)",
                (organization_id, farm_id, area_id, user_id),
            )
        connection.commit()
    finally:
        connection.close()


def _scalar(cursor: Any, sql: str) -> str:
    cursor.execute(sql)
    value = next(iter((cursor.fetchone() or {"value": 0}).values()))
    return str(value if value is not None else 0)


def snapshot(tools: DatabaseTools, database: str) -> DatabaseSnapshot:
    connection = connect_database(tools, database)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version,checksum FROM schema_migrations ORDER BY version")
            migrations = {str(row["version"]): str(row["checksum"]) for row in cursor.fetchall()}
            table_counts = {
                table: int(_scalar(cursor, f"SELECT COUNT(*) AS value FROM `{table}`"))
                for table in CRITICAL_TABLES
            }
            aggregates = {
                "inventory_quantity": _scalar(cursor, "SELECT COALESCE(SUM(quantity_delta),0) AS value FROM inventory_ledger"),
                "batch_quantity": _scalar(cursor, "SELECT COALESCE(SUM(quantity_delta),0) AS value FROM batch_stock_records"),
                "payable_amount": _scalar(cursor, "SELECT COALESCE(SUM(amount),0) AS value FROM purchase_payables"),
                "payable_paid": _scalar(cursor, "SELECT COALESCE(SUM(paid_amount),0) AS value FROM purchase_payables"),
                "receivable_amount": _scalar(cursor, "SELECT COALESCE(SUM(amount),0) AS value FROM sales_receivables"),
                "receivable_received": _scalar(cursor, "SELECT COALESCE(SUM(received_amount),0) AS value FROM sales_receivables"),
                "confirmed_cost": _scalar(cursor, "SELECT COALESCE(SUM(amount),0) AS value FROM cost_entries WHERE status='confirmed'"),
            }
        return DatabaseSnapshot(migrations=migrations, table_counts=table_counts, aggregates=aggregates)
    finally:
        connection.close()


def run_drill(output: Path, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    tools = require_database_tools(env)
    source = require_disposable_database_name(f"adp_readiness_source_{uuid4().hex[:12]}")
    restored = require_disposable_database_name(f"adp_readiness_restore_{uuid4().hex[:12]}")
    dump_path = output.parent / f"adp-readiness-{uuid4().hex[:12]}.sql"
    created: list[str] = []
    cleanup_errors: list[str] = []
    metrics: dict[str, Any] = {"source_database": source, "restore_database": restored}
    passed = False
    try:
        for database in (source, restored):
            execute_sql(tools, f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            created.append(database)
            if database == source:
                break
        apply_migrations(tools, source)
        for seed in SEED_FILES:
            apply_sql(tools, source, seed)
        _seed_traceable_record(tools, source)
        source_snapshot = snapshot(tools, source)
        source_connection = connect_database(tools, source)
        try:
            source_reconciliation = reconcile(source_connection, MIGRATION_DIR)
        finally:
            source_connection.close()

        run_database_command(tools.mysqldump, dump_arguments(source), tools, stdout_file=dump_path)
        metrics["dump_bytes"] = dump_path.stat().st_size
        metrics["dump_sha256"] = hashlib.sha256(dump_path.read_bytes()).hexdigest()
        execute_sql(tools, f"CREATE DATABASE `{restored}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        created.append(restored)
        run_database_command(tools.mysql, [f"--database={restored}"], tools, stdin=dump_path.read_bytes())
        restored_snapshot = snapshot(tools, restored)
        restored_connection = connect_database(tools, restored)
        try:
            restored_reconciliation = reconcile(restored_connection, MIGRATION_DIR)
        finally:
            restored_connection.close()

        differences = compare_snapshots(source_snapshot, restored_snapshot)
        apply_migrations(tools, restored)
        for seed in SEED_FILES:
            apply_sql(tools, restored, seed)
        idempotent_snapshot = snapshot(tools, restored)
        idempotency_differences = compare_snapshots(restored_snapshot, idempotent_snapshot)
        metrics.update(
            source_snapshot=asdict(source_snapshot),
            restored_snapshot=asdict(restored_snapshot),
            snapshot_differences=differences,
            idempotency_differences=idempotency_differences,
            source_reconciliation=source_reconciliation,
            restored_reconciliation=restored_reconciliation,
        )
        passed = not differences and not idempotency_differences and source_reconciliation["ok"] and restored_reconciliation["ok"]
    except Exception as exc:
        metrics["error"] = str(exc)
    finally:
        for database in reversed(created):
            try:
                require_disposable_database_name(database)
                execute_sql(tools, f"DROP DATABASE IF EXISTS `{database}`")
            except Exception as exc:
                cleanup_errors.append(f"{database}: {exc}")
        if dump_path.exists():
            dump_path.unlink()
        metrics["cleanup_errors"] = cleanup_errors
        metrics["cleanup"] = not cleanup_errors and not dump_path.exists()
        passed = passed and bool(metrics["cleanup"])
    result = evidence("database-drill", metrics, passed=passed)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="ADP disposable database backup/restore readiness drill")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_drill(args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
