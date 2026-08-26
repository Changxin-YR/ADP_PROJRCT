from __future__ import annotations

import logging
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Sequence
from uuid import uuid4

import pymysql

from backend.config.settings import Settings
from backend.layers.common.db.connection import get_connection
from backend.layers.common.security.password import hash_password
from backend.scripts.readiness.common import ReadinessFailure, percentile


READ_ENDPOINTS = (
    "/api/v1/workbench/summary",
    "/api/v1/master-data/ponds?page=1&page_size=20",
    "/api/v1/warehouse/receipts?page=1&page_size=20",
    "/api/v1/purchase/orders?page=1&page_size=20",
    "/api/v1/sales/orders?page=1&page_size=20",
)


@dataclass(frozen=True)
class WorkItem:
    method: str
    path: str
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class LoadAssessment:
    total: int
    successes: int
    server_errors: int
    p95: float
    p99: float
    write_expected: int
    write_actual: int
    passed: bool


def generate_workload(total: int, *, stage: int, run_id: str) -> list[WorkItem]:
    if total < 1 or stage < 1 or not run_id.isalnum() or len(run_id) > 16:
        raise ReadinessFailure("压测工作负载参数无效")
    workload: list[WorkItem] = []
    for index in range(total):
        if index % 10 == 0:
            code = f"TEST_LOAD_{run_id}_{stage}_{index:04d}"
            workload.append(
                WorkItem(
                    "POST",
                    "/api/v1/master-data/ponds",
                    {
                        "code": code,
                        "name": f"TEST_LOAD_塘口_{stage}_{index:04d}",
                        "capacity_mu": 1,
                        "pond_status": "build",
                    },
                )
            )
        else:
            workload.append(WorkItem("GET", READ_ENDPOINTS[index % len(READ_ENDPOINTS)]))
    return workload


def assess_load(
    *,
    total: int,
    successes: int,
    latencies: Sequence[float],
    server_errors: int,
    write_expected: int,
    write_actual: int,
    p95_limit: float,
    p99_limit: float,
) -> LoadAssessment:
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    return LoadAssessment(
        total=total,
        successes=successes,
        server_errors=server_errors,
        p95=p95,
        p99=p99,
        write_expected=write_expected,
        write_actual=write_actual,
        passed=(
            total > 0
            and successes == total
            and len(latencies) == total
            and server_errors == 0
            and p95 <= p95_limit
            and p99 <= p99_limit
            and write_actual == write_expected
        ),
    )


def settings_for_load(tools: Any, database: str) -> Settings:
    return Settings.from_env(
        {
            "APP_ENV": "test",
            "FLASK_SECRET_KEY": "readiness-load-flask-secret",
            "CSRF_SECRET_KEY": "readiness-load-csrf-secret",
            "MYSQL_HOST": str(tools.connection["host"]),
            "MYSQL_PORT": str(tools.connection["port"]),
            "MYSQL_DATABASE": database,
            "MYSQL_USER": str(tools.connection["user"]),
            "MYSQL_PASSWORD": str(tools.connection["password"]),
            "SESSION_COOKIE_SECURE": "false",
        }
    )


def seed_load_accounts(settings: Settings, count: int = 20) -> tuple[list[str], str]:
    password = f"Ld-{uuid4().hex}-Aa9!"
    password_hash = hash_password(password)
    identifiers: list[str] = []
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM roles WHERE code='super_admin'")
        role_id = int(cursor.fetchone()["id"])
        cursor.execute("SELECT id FROM data_scopes WHERE code='farm-all'")
        scope_id = int(cursor.fetchone()["id"])
        for index in range(count):
            identifier = f"TEST_LOAD_USER_{index:02d}"
            identifiers.append(identifier)
            cursor.execute(
                "INSERT INTO users(phone,login_name,name,password_hash,status) VALUES (%s,%s,%s,%s,'active')",
                (f"13790000{index:03d}", identifier, f"TEST_LOAD_用户{index:02d}", password_hash),
            )
            user_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO user_roles(user_id,role_id,granted_by) VALUES (%s,%s,%s)",
                (user_id, role_id, user_id),
            )
            cursor.execute(
                "INSERT INTO user_data_scopes(user_id,data_scope_id,granted_by) VALUES (%s,%s,%s)",
                (user_id, scope_id, user_id),
            )
    return identifiers, password


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_health(base_url: str, process: subprocess.Popen[Any], timeout_seconds: float = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ReadinessFailure(f"Flask 压测进程提前退出（exit={process.returncode}）")
        try:
            with urllib.request.urlopen(f"{base_url}/api/v1/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            logging.getLogger(__name__).debug("Flask 健康检查重试中: %s", exc)
        time.sleep(0.1)
    raise ReadinessFailure("Flask 压测进程健康检查超时")


def mysql_global_status(tools: Any) -> dict[str, int]:
    connection = pymysql.connect(
        **tools.connection,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=5,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SHOW GLOBAL STATUS WHERE Variable_name IN ('Threads_connected','Threads_running','Max_used_connections')"
            )
            return {str(row["Variable_name"]): int(row["Value"]) for row in cursor.fetchall()}
    finally:
        connection.close()


def count_stage_writes(settings: Settings, code_prefix: str) -> int:
    with get_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM ponds WHERE code LIKE %s", (f"{code_prefix}%",))
        return int(cursor.fetchone()["total"])
