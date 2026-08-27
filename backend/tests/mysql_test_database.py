from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import pytest

from backend.config.settings import Settings


ROOT = Path(__file__).parents[2]


def mysql_command() -> tuple[list[str], dict[str, str]]:
    client = os.environ.get("ADP_TEST_MYSQL_CLIENT")
    if os.environ.get("ADP_TEST_MYSQL_ALLOW_DISPOSABLE") != "1" or not client:
        pytest.skip("set ADP_TEST_MYSQL_CLIENT and ADP_TEST_MYSQL_ALLOW_DISPOSABLE=1")
    environment = os.environ.copy()
    if environment.get("ADP_TEST_MYSQL_PASSWORD"):
        environment["MYSQL_PWD"] = environment["ADP_TEST_MYSQL_PASSWORD"]
    return [
        client,
        "--protocol=tcp",
        f"--host={environment.get('ADP_TEST_MYSQL_HOST', '127.0.0.1')}",
        f"--port={environment.get('ADP_TEST_MYSQL_PORT', '3306')}",
        f"--user={environment.get('ADP_TEST_MYSQL_USER', 'root')}",
        "--default-character-set=utf8mb4",
        "--batch",
    ], environment


def run_mysql(*args: str, sql: bytes | None = None) -> None:
    command, environment = mysql_command()
    completed = subprocess.run([*command, *args], input=sql, capture_output=True, env=environment, check=False)
    if completed.returncode:
        raise AssertionError(completed.stderr.decode("utf-8", errors="replace"))


def grant_database_access(database: str) -> None:
    test_user = os.environ.get("ADP_TEST_MYSQL_USER", "root").strip()
    if not test_user or test_user == "root":
        return
    if not test_user.replace("_", "").replace("-", "").isalnum():
        raise AssertionError("ADP_TEST_MYSQL_USER contains unsupported characters")
    run_mysql(f"--execute=GRANT ALL PRIVILEGES ON `{database}`.* TO '{test_user}'@'127.0.0.1'")


@contextmanager
def disposable_database(prefix: str, *, through: int) -> Iterator[str]:
    database = f"{prefix}_{uuid4().hex[:12]}"
    run_mysql(f"--execute=CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    try:
        grant_database_access(database)
        migrations = sorted((ROOT / "database/migrations").glob("[0-9][0-9][0-9]_*.sql"))
        for migration in migrations:
            if int(migration.name[:3]) <= through:
                run_mysql(f"--database={database}", sql=migration.read_bytes())
        yield database
    finally:
        run_mysql(f"--execute=DROP DATABASE IF EXISTS `{database}`")


def settings_for(database: str) -> Settings:
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
