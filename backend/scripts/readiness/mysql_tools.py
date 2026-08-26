from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pymysql

from backend.scripts.readiness.common import ReadinessFailure


ROOT = Path(__file__).resolve().parents[3]
MIGRATION_DIR = ROOT / "database" / "migrations"


@dataclass(frozen=True)
class DatabaseTools:
    mysql: Path
    mysqldump: Path
    environment: dict[str, str]
    connection: dict[str, Any]


def require_database_tools(env: Mapping[str, str] | None = None) -> DatabaseTools:
    values = dict(os.environ if env is None else env)
    if values.get("ADP_TEST_MYSQL_ALLOW_DISPOSABLE") != "1":
        raise ReadinessFailure("必须显式设置 ADP_TEST_MYSQL_ALLOW_DISPOSABLE=1")
    client_value = values.get("ADP_TEST_MYSQL_CLIENT", "").strip()
    if not client_value:
        raise ReadinessFailure("必须设置 ADP_TEST_MYSQL_CLIENT")
    mysql = Path(client_value).resolve()
    if not mysql.is_file():
        raise ReadinessFailure("MySQL 客户端不存在")
    dump_value = values.get("ADP_TEST_MYSQL_DUMP", "").strip()
    mysqldump = (
        Path(dump_value).resolve()
        if dump_value
        else mysql.with_name("mysqldump.exe" if os.name == "nt" else "mysqldump")
    )
    if not mysqldump.is_file():
        located = shutil.which("mysqldump")
        if not located:
            raise ReadinessFailure("mysqldump 客户端不存在")
        mysqldump = Path(located).resolve()
    process_env = os.environ.copy()
    password = values.get("ADP_TEST_MYSQL_PASSWORD", "")
    if password:
        process_env["MYSQL_PWD"] = password
    return DatabaseTools(
        mysql=mysql,
        mysqldump=mysqldump,
        environment=process_env,
        connection={
            "host": values.get("ADP_TEST_MYSQL_HOST", "127.0.0.1"),
            "port": int(values.get("ADP_TEST_MYSQL_PORT", "3306")),
            "user": values.get("ADP_TEST_MYSQL_USER", "root"),
            "password": password,
        },
    )


def _client_arguments(tools: DatabaseTools) -> list[str]:
    return [
        "--protocol=tcp",
        f"--host={tools.connection['host']}",
        f"--port={tools.connection['port']}",
        f"--user={tools.connection['user']}",
        "--default-character-set=utf8mb4",
    ]


def run_database_command(
    executable: Path,
    arguments: list[str],
    tools: DatabaseTools,
    *,
    stdin: bytes | None = None,
    stdout_file: Path | None = None,
) -> None:
    destination = stdout_file.open("wb") if stdout_file else subprocess.PIPE
    try:
        completed = subprocess.run(
            [str(executable), *_client_arguments(tools), *arguments],
            input=stdin,
            stdout=destination,
            stderr=subprocess.PIPE,
            env=tools.environment,
            check=False,
        )
    finally:
        if stdout_file:
            destination.close()  # type: ignore[union-attr]
    if completed.returncode:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ReadinessFailure(f"数据库命令失败（exit={completed.returncode}）：{message[:500]}")


def execute_sql(tools: DatabaseTools, sql: str, database: str | None = None) -> None:
    arguments = ([f"--database={database}"] if database else []) + [f"--execute={sql}"]
    run_database_command(tools.mysql, arguments, tools)


def apply_sql(tools: DatabaseTools, database: str, path: Path) -> None:
    run_database_command(tools.mysql, [f"--database={database}"], tools, stdin=path.read_bytes())


def connect_database(tools: DatabaseTools, database: str) -> pymysql.Connection:
    return pymysql.connect(
        **tools.connection,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def apply_migrations(tools: DatabaseTools, database: str) -> None:
    migrations = sorted(MIGRATION_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    apply_sql(tools, database, migrations[0])
    connection = connect_database(tools, database)
    try:
        for migration in migrations[1:]:
            checksum = hashlib.sha256(migration.read_bytes()).hexdigest()
            with connection.cursor() as cursor:
                cursor.execute("SELECT checksum FROM schema_migrations WHERE version=%s", (migration.stem,))
                row = cursor.fetchone()
            if row:
                if str(row["checksum"]) != checksum:
                    raise ReadinessFailure(f"迁移校验和漂移：{migration.stem}")
                continue
            connection.commit()
            apply_sql(tools, database, migration)
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO schema_migrations(version,checksum) VALUES (%s,%s)",
                    (migration.stem, checksum),
                )
            connection.commit()
    finally:
        connection.close()
