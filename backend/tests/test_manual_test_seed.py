from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymysql
import pytest
from pymysql.cursors import DictCursor
from werkzeug.security import check_password_hash

from backend.scripts.manual_test_seed import main, validate_target
from backend.tests.mysql_test_database import disposable_database, run_mysql, settings_for


DATABASE_PASSWORD = "sensitive-database-password"
MANUAL_TEST_PASSWORD = "sensitive-manual-test-password"


class FakeCursor:
    def __init__(self, rows: set[str]) -> None:
        self.rows = rows

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeConnection:
    def __init__(self, rows: set[str]) -> None:
        self.rows = rows
        self.events: list[str] = []

    def begin(self) -> None:
        self.events.append("begin")

    def cursor(self) -> FakeCursor:
        self.events.append("cursor")
        return FakeCursor(self.rows)

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")

    def close(self) -> None:
        self.events.append("close")


@pytest.fixture
def manual_test_environment(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MYSQL_DATABASE", "adp_manual_test_20260817")
    monkeypatch.setenv("MYSQL_PASSWORD", DATABASE_PASSWORD)
    monkeypatch.setenv("ADP_MANUAL_TEST_CONFIRM", "CREATE_TEST_DATA")
    monkeypatch.setenv("ADP_MANUAL_TEST_PASSWORD", MANUAL_TEST_PASSWORD)
    return MANUAL_TEST_PASSWORD


def test_validate_target_rejects_production_environment() -> None:
    with pytest.raises(RuntimeError, match="APP_ENV"):
        validate_target("production", "adp_manual_test_20260817", "CREATE_TEST_DATA")


def test_validate_target_rejects_non_manual_test_database() -> None:
    with pytest.raises(RuntimeError, match="adp_manual_test_"):
        validate_target("test", "adp_production_20260817", "CREATE_TEST_DATA")


def test_validate_target_requires_explicit_confirmation() -> None:
    with pytest.raises(RuntimeError, match="ADP_MANUAL_TEST_CONFIRM"):
        validate_target("test", "adp_manual_test_20260817", "")


def test_main_requires_manual_test_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MYSQL_DATABASE", "adp_manual_test_20260817")
    monkeypatch.setenv("ADP_MANUAL_TEST_CONFIRM", "CREATE_TEST_DATA")
    monkeypatch.delenv("ADP_MANUAL_TEST_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="ADP_MANUAL_TEST_PASSWORD"):
        main()


@pytest.mark.parametrize("app_env", ["Test", " test "])
def test_main_rejects_non_exact_raw_app_env_before_connect(
    app_env: str,
    manual_test_environment: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections: list[FakeConnection] = []

    def connection_factory(_settings: object) -> FakeConnection:
        connection = FakeConnection(set())
        connections.append(connection)
        return connection

    monkeypatch.setenv("APP_ENV", app_env)

    with pytest.raises(RuntimeError, match="APP_ENV"):
        main(connection_factory=connection_factory)

    assert connections == []


def test_main_manifest_does_not_expose_password(
    manual_test_environment: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connections: list[FakeConnection] = []
    seed_passwords: list[str] = []

    def connection_factory(_settings: object) -> FakeConnection:
        connection = FakeConnection(set())
        connections.append(connection)
        return connection

    def seed_action(_cursor: FakeCursor, password: str) -> dict[str, object]:
        seed_passwords.append(password)
        return {}

    assert main(connection_factory=connection_factory, seed_action=seed_action) == 0

    output = capsys.readouterr().out
    assert json.loads(output) == {
        "app_env": "test",
        "database": "adp_manual_test_20260817",
        "seed": {},
        "status": "validated",
    }
    assert seed_passwords == [manual_test_environment]
    assert MANUAL_TEST_PASSWORD not in output
    assert DATABASE_PASSWORD not in output
    assert connections[0].events == ["begin", "cursor", "commit", "close"]


def test_main_runs_an_idempotent_seed_twice(
    manual_test_environment: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rows: set[str] = set()
    connections: list[FakeConnection] = []

    def connection_factory(_settings: object) -> FakeConnection:
        connection = FakeConnection(rows)
        connections.append(connection)
        return connection

    def seed_action(cursor: FakeCursor, _password: str) -> dict[str, int]:
        created = int("test-seed" not in cursor.rows)
        cursor.rows.add("test-seed")
        return {"created": created}

    assert main(connection_factory=connection_factory, seed_action=seed_action) == 0
    assert main(connection_factory=connection_factory, seed_action=seed_action) == 0

    manifests = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [manifest["seed"]["created"] for manifest in manifests] == [1, 0]
    assert rows == {"test-seed"}
    assert [connection.events for connection in connections] == [
        ["begin", "cursor", "commit", "close"],
        ["begin", "cursor", "commit", "close"],
    ]


def test_main_rolls_back_without_success_manifest_when_seed_fails(
    manual_test_environment: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connection = FakeConnection(set())

    def fail_seed(_cursor: FakeCursor, _password: str) -> dict[str, int]:
        raise RuntimeError("seed failed")

    with pytest.raises(RuntimeError, match="seed failed"):
        main(connection_factory=lambda _settings: connection, seed_action=fail_seed)

    assert connection.events == ["begin", "cursor", "rollback", "close"]
    assert capsys.readouterr().out == ""


def test_main_uses_complete_seed_by_default(
    manual_test_environment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from backend.scripts import manual_test_seed_accounts, manual_test_seed_business

    passwords: list[str] = []

    def seed_accounts(_cursor: FakeCursor, password: str) -> dict[str, object]:
        passwords.append(password)
        return {"users": 7}

    def seed_business(_cursor: FakeCursor, password: str) -> dict[str, object]:
        passwords.append(password)
        return {"domains": 8}

    monkeypatch.setattr(manual_test_seed_accounts, "seed_accounts", seed_accounts)
    monkeypatch.setattr(manual_test_seed_business, "seed_business", seed_business)
    assert main(connection_factory=lambda _settings: FakeConnection(set())) == 0
    assert passwords == [manual_test_environment, manual_test_environment]
    assert json.loads(capsys.readouterr().out)["seed"] == {
        "accounts": {"users": 7}, "business": {"domains": 8},
    }


def test_manual_test_accounts_and_master_data_are_idempotent() -> None:
    from backend.scripts.manual_test_seed_accounts import seed_accounts

    password = "manual-test-password"
    with disposable_database("adp_manual_test_seed", through=21) as database:
        reference_seed = Path(__file__).parents[2] / "database/seed_reference.sql"
        run_mysql(f"--database={database}", sql=reference_seed.read_bytes())
        settings = settings_for(database)
        connection = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=database,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
        )
        try:
            with connection.cursor() as cursor:
                seed_accounts(cursor, password)
            connection.commit()
            with connection.cursor() as cursor:
                first = _account_seed_snapshot(cursor)
                cursor.execute(
                    "SELECT u.login_name,r.code FROM users u JOIN user_roles ur ON ur.user_id=u.id "
                    "JOIN roles r ON r.id=ur.role_id WHERE u.login_name LIKE 'test-%'"
                )
                roles = {row["login_name"]: row["code"] for row in cursor.fetchall()}
                cursor.execute(
                    "SELECT password_hash FROM users WHERE login_name LIKE 'test-%' ORDER BY login_name"
                )
                hashes = [row["password_hash"] for row in cursor.fetchall()]
                seed_accounts(cursor, password)
            connection.commit()
            with connection.cursor() as cursor:
                second = _account_seed_snapshot(cursor)
        finally:
            connection.close()

    assert first == second == {
        "areas": 2,
        "customers": 1,
        "farms": 1,
        "materials": 4,
        "organizations": 1,
        "ponds": 4,
        "role_grants": 7,
        "scope_grants": 7,
        "suppliers": 1,
        "users": 7,
        "warehouses": 1,
    }
    assert roles == {
        "test-admin": "super_admin", "test-breed-manager": "breed_manager",
        "test-breed-worker": "breed_worker", "test-finance": "finance_staff",
        "test-purchaser": "purchaser", "test-sales": "sales_staff",
        "test-warehouse": "warehouse_manager",
    }
    assert len(hashes) == 7
    assert all(check_password_hash(value, password) for value in hashes)


def _account_seed_snapshot(cursor: Any) -> dict[str, int]:
    statements = {
        "areas": "SELECT COUNT(*) AS total FROM areas WHERE code LIKE 'TEST-20260817-AREA-%' AND status='verified'",
        "customers": "SELECT COUNT(*) AS total FROM business_partners WHERE code='TEST-20260817-CUSTOMER' AND partner_type='customer' AND status='verified'",
        "farms": "SELECT COUNT(*) AS total FROM farms WHERE code='TEST-20260817-FARM' AND status='verified'",
        "materials": "SELECT COUNT(*) AS total FROM materials WHERE code LIKE 'TEST-20260817-MAT-%' AND status='verified'",
        "organizations": "SELECT COUNT(*) AS total FROM organizations WHERE code='TEST-20260817-ORG'",
        "ponds": "SELECT COUNT(*) AS total FROM ponds WHERE code LIKE 'TEST-20260817-POND-%' AND status='verified'",
        "role_grants": "SELECT COUNT(*) AS total FROM user_roles ur JOIN users u ON u.id=ur.user_id WHERE u.login_name LIKE 'test-%'",
        "scope_grants": "SELECT COUNT(DISTINCT uds.user_id) AS total FROM user_data_scopes uds JOIN users u ON u.id=uds.user_id WHERE u.login_name LIKE 'test-%'",
        "suppliers": "SELECT COUNT(*) AS total FROM business_partners WHERE code='TEST-20260817-SUPPLIER' AND partner_type='supplier' AND status='verified'",
        "users": "SELECT COUNT(*) AS total FROM users WHERE login_name LIKE 'test-%' AND status='active'",
        "warehouses": "SELECT COUNT(*) AS total FROM warehouses WHERE code='TEST-20260817-WAREHOUSE'",
    }
    result: dict[str, int] = {}
    for name, statement in statements.items():
        cursor.execute(statement)
        result[name] = int(cursor.fetchone()["total"])
    return result
