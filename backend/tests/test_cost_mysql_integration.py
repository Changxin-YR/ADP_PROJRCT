from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path
from uuid import uuid4

import pymysql
import pytest
from pymysql.cursors import DictCursor

from backend.config.settings import Settings
from backend.layers.common.db.repositories.cost_repository import CostRepository
from backend.layers.common.db.repositories.cost_store import MySqlCostStore
from backend.layers.features.cost.calculation import summarize_costs


MYSQL_CLIENT = os.environ.get("ADP_TEST_MYSQL_CLIENT")
DISPOSABLE_ALLOWED = os.environ.get("ADP_TEST_MYSQL_ALLOW_DISPOSABLE") == "1"


def _mysql(*args: str, sql: bytes | None = None) -> str:
    if not MYSQL_CLIENT or not DISPOSABLE_ALLOWED:
        pytest.skip("set the MySQL client and ADP_TEST_MYSQL_ALLOW_DISPOSABLE=1 for the disposable database test")
    environment = os.environ.copy()
    password = environment.get("ADP_TEST_MYSQL_PASSWORD", "")
    if password:
        environment["MYSQL_PWD"] = password
    command = [
        MYSQL_CLIENT,
        "--protocol=tcp",
        f"--host={environment.get('ADP_TEST_MYSQL_HOST', '127.0.0.1')}",
        f"--port={environment.get('ADP_TEST_MYSQL_PORT', '3306')}",
        f"--user={environment.get('ADP_TEST_MYSQL_USER', 'root')}",
        "--default-character-set=utf8mb4",
        "--batch",
        "--skip-column-names",
        *args,
    ]
    completed = subprocess.run(command, input=sql, capture_output=True, env=environment, check=False)
    if completed.returncode:
        raise AssertionError(completed.stderr.decode("utf-8", errors="replace"))
    return completed.stdout.decode("utf-8", errors="replace").strip()


def _settings(database: str) -> Settings:
    return Settings.from_env({
        "APP_ENV": "test",
        "FLASK_SECRET_KEY": "mysql-integration-flask",
        "CSRF_SECRET_KEY": "mysql-integration-csrf",
        "MYSQL_HOST": os.environ.get("ADP_TEST_MYSQL_HOST", "127.0.0.1"),
        "MYSQL_PORT": os.environ.get("ADP_TEST_MYSQL_PORT", "3306"),
        "MYSQL_DATABASE": database,
        "MYSQL_USER": os.environ.get("ADP_TEST_MYSQL_USER", "root"),
        "MYSQL_PASSWORD": os.environ.get("ADP_TEST_MYSQL_PASSWORD", ""),
        "SESSION_COOKIE_SECURE": "false",
    })


def _first_day_after(value: date) -> date:
    return date(value.year + (1 if value.month == 12 else 0), 1 if value.month == 12 else value.month + 1, 1)


def test_cost_migrations_are_idempotent_and_preserve_entry_level_nature() -> None:
    if not MYSQL_CLIENT or not DISPOSABLE_ALLOWED:
        pytest.skip("set the MySQL client and ADP_TEST_MYSQL_ALLOW_DISPOSABLE=1 for the disposable database test")
    database = f"adp_cost_test_{uuid4().hex[:12]}"
    migrations = Path("database/migrations")
    _mysql(f"--execute=CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    try:
        for migration in ("000_schema_migrations.sql", "001_initial_auth.sql", "002_roles_and_scopes_expansion.sql", "003_cost_accounting_foundation.sql"):
            _mysql(f"--database={database}", sql=(migrations / migration).read_bytes())
        _mysql(f"--database={database}", sql=(migrations / "003_cost_accounting_foundation.sql").read_bytes())
        _mysql(f"--database={database}", sql=(migrations / "004_enterprise_governance_foundation.sql").read_bytes())

        initialized = _mysql(
            f"--database={database}",
            "--execute=SELECT CONCAT((SELECT COUNT(*) FROM cost_categories WHERE status='active'),'|',(SELECT CAST(SUM(amount) AS CHAR) FROM cost_entries WHERE status='confirmed'),'|',(SELECT COUNT(*) FROM cost_allocation_rule_versions),'|',(SELECT COUNT(*) FROM cost_allocation_rules))",
        )
        assert initialized == "9|672000.00|1|9"

        _mysql(
            f"--database={database}",
            "--execute=INSERT INTO cost_entries (category_id,amount,occurred_on,period_start,period_end,status,cost_nature,source_type,source_ref,confirmed_at) SELECT id,10.00,'2026-08-16','2026-01-01','2026-08-16','confirmed','direct','integration_test','MIXED-NATURE',CURRENT_TIMESTAMP FROM cost_categories WHERE code='other'",
        )
        nature_totals = _mysql(
            f"--database={database}",
            "--execute=SELECT CONCAT(CAST(SUM(amount) AS CHAR),'|',CAST(SUM(CASE WHEN cost_nature='direct' THEN amount ELSE 0 END) AS CHAR),'|',CAST(SUM(CASE WHEN cost_nature='public' THEN amount ELSE 0 END) AS CHAR)) FROM cost_entries WHERE status='confirmed'",
        )
        assert nature_totals == "672010.00|250010.00|422000.00"

        settings = _settings(database)
        connection = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8mb4",
            cursorclass=DictCursor,
        )
        try:
            rows = CostRepository().list_category_totals(
                connection,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 8, 16),
            )
        finally:
            connection.close()
        structure = summarize_costs(rows)
        assert structure["categories"][0]["id"] == rows[0]["id"]
        assert structure["direct_amount"] == "250010.00"

        store = MySqlCostStore(settings)
        effective_v2 = max(_first_day_after(date.today()), date(2026, 2, 1))
        rules = [
            {"category_id": row["id"], "driver": row["allocation_driver"], "manual_ratio_json": None}
            for row in rows
        ]
        version = store.create_rule_version(
            user_id=None,
            ip_address="127.0.0.1",
            effective_from=effective_v2,
            change_reason="真实 MySQL 仓储集成测试",
            rules=rules,
        )
        assert version["version_no"] == 2
        committed = _mysql(
            f"--database={database}",
            "--execute=SELECT CONCAT((SELECT COUNT(*) FROM cost_allocation_rule_versions),'|',(SELECT COUNT(*) FROM cost_allocation_rules),'|',(SELECT COUNT(*) FROM audit_logs WHERE action='update_cost_allocation_rules'))",
        )
        assert committed == "2|18|1"

        class FailingAudit:
            def write(self, *_args, **_kwargs):
                raise RuntimeError("audit failure injection")

        store.audit = FailingAudit()
        with pytest.raises(RuntimeError, match="audit failure injection"):
            store.create_rule_version(
                user_id=None,
                ip_address="127.0.0.1",
                effective_from=_first_day_after(effective_v2),
                change_reason="必须整体回滚",
                rules=rules,
            )
        rolled_back = _mysql(
            f"--database={database}",
            "--execute=SELECT CONCAT((SELECT COUNT(*) FROM cost_allocation_rule_versions),'|',(SELECT COUNT(*) FROM cost_allocation_rules),'|',(SELECT COUNT(*) FROM audit_logs WHERE action='update_cost_allocation_rules'))",
        )
        assert rolled_back == "2|18|1"
    finally:
        _mysql(f"--execute=DROP DATABASE IF EXISTS `{database}`")
