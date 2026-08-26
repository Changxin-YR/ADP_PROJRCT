from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.scripts.readiness.common import ReadinessFailure, evidence, require_disposable_database_name
from backend.scripts.readiness.database_drill import SEED_FILES
from backend.scripts.readiness.load_http import execute_stages
from backend.scripts.readiness.load_support import (
    assess_load,
    free_port,
    generate_workload,
    seed_load_accounts,
    settings_for_load,
    wait_for_health,
)
from backend.scripts.readiness.mysql_tools import apply_migrations, apply_sql, execute_sql, require_database_tools


ROOT = Path(__file__).resolve().parents[3]


def run_probe(output: Path, *, levels: list[int], p95_limit: float, p99_limit: float) -> dict[str, Any]:
    if levels != sorted(set(levels)) or any(level < 1 or level % 10 for level in levels) or 500 not in levels:
        raise ReadinessFailure("压测阶梯必须升序、去重、为 10 的倍数且包含 500")
    tools = require_database_tools()
    database = require_disposable_database_name(f"adp_readiness_load_{uuid4().hex[:12]}")
    run_id = uuid4().hex[:12]
    metrics: dict[str, Any] = {
        "database": database,
        "levels": levels,
        "p95_limit_seconds": p95_limit,
        "p99_limit_seconds": p99_limit,
        "environment_note": "Windows 本地 Flask/MySQL 候选基线；不替代 Linux Gunicorn 生产压测",
    }
    cleanup_errors: list[str] = []
    created = False
    server: subprocess.Popen[Any] | None = None
    server_log_handle: Any = None
    attachment_directory: tempfile.TemporaryDirectory[str] | None = None
    passed = False
    try:
        execute_sql(tools, f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        created = True
        apply_migrations(tools, database)
        for seed in SEED_FILES:
            apply_sql(tools, database, seed)
        settings = settings_for_load(tools, database)
        identifiers, password = seed_load_accounts(settings)
        attachment_directory = tempfile.TemporaryDirectory(prefix="adp-load-attachments-")
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        server_env = os.environ.copy()
        server_env.update(
            APP_ENV="test",
            FLASK_SECRET_KEY="readiness-load-flask-secret",
            CSRF_SECRET_KEY="readiness-load-csrf-secret",
            MYSQL_HOST=str(tools.connection["host"]),
            MYSQL_PORT=str(tools.connection["port"]),
            MYSQL_DATABASE=database,
            MYSQL_USER=str(tools.connection["user"]),
            MYSQL_PASSWORD=str(tools.connection["password"]),
            SESSION_COOKIE_SECURE="false",
            ATTACHMENT_ROOT=attachment_directory.name,
            PYTHONUNBUFFERED="1",
        )
        server_log = output.parent / "load-server.log"
        server_log_handle = server_log.open("w", encoding="utf-8")
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "flask",
                "--app",
                "backend.app",
                "run",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-debugger",
                "--no-reload",
            ],
            cwd=ROOT,
            env=server_env,
            stdin=subprocess.DEVNULL,
            stdout=server_log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )
        wait_for_health(base_url, server)
        stages = asyncio.run(
            execute_stages(
                base_url=base_url,
                identifiers=identifiers,
                password=password,
                settings=settings,
                backend_pid=server.pid,
                levels=levels,
                run_id=run_id,
                p95_limit=p95_limit,
                p99_limit=p99_limit,
            )
        )
        metrics.update(
            server_pid=server.pid,
            server_log=server_log.name,
            authenticated_sessions=len(identifiers),
            stages=stages,
        )
        hard_gate = next(stage for stage in stages if int(stage["total"]) == 500)
        passed = bool(hard_gate["passed"]) and all(bool(stage["passed"]) for stage in stages)
    except Exception as exc:
        metrics["error_type"] = type(exc).__name__
        metrics["error"] = str(exc)
    finally:
        if server is not None and server.poll() is None:
            try:
                server.terminate()
                server.wait(timeout=10)
            except Exception:
                try:
                    server.kill()
                    server.wait(timeout=5)
                except Exception as exc:
                    cleanup_errors.append(f"server: {type(exc).__name__}")
        if server_log_handle is not None:
            server_log_handle.close()
        if attachment_directory is not None:
            try:
                attachment_directory.cleanup()
            except OSError as exc:
                cleanup_errors.append(f"attachments: {type(exc).__name__}")
        if created:
            try:
                require_disposable_database_name(database)
                execute_sql(tools, f"DROP DATABASE IF EXISTS `{database}`")
            except Exception as exc:
                cleanup_errors.append(f"{database}: {type(exc).__name__}")
        metrics["cleanup_errors"] = cleanup_errors
        metrics["cleanup"] = not cleanup_errors
        passed = passed and not cleanup_errors

    result = evidence("http-load", metrics, passed=passed)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="ADP HTTP concurrency readiness probe")
    parser.add_argument("--levels", default="10,50,100,500")
    parser.add_argument("--p95", type=float, default=3)
    parser.add_argument("--p99", type=float, default=5)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    levels = [int(item.strip()) for item in args.levels.split(",") if item.strip()]
    result = run_probe(args.output.resolve(), levels=levels, p95_limit=args.p95, p99_limit=args.p99)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
