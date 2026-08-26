from __future__ import annotations

import asyncio
import threading
import time
from collections import Counter
from dataclasses import asdict
from typing import Any

from backend.config.settings import Settings
from backend.scripts.readiness.common import ReadinessFailure
from backend.scripts.readiness.load_support import (
    WorkItem,
    assess_load,
    count_stage_writes,
    generate_workload,
    mysql_global_status,
)
from backend.scripts.readiness.mysql_tools import require_database_tools


async def _login_sessions(base_url: str, identifiers: list[str], password: str) -> list[tuple[Any, str]]:
    import aiohttp

    result: list[tuple[Any, str]] = []
    try:
        for index, identifier in enumerate(identifiers):
            client = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True),
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": f"ADP-Readiness-Load/{index:02d}"},
            )
            try:
                async with client.get(f"{base_url}/api/v1/auth/csrf") as response:
                    body = await response.json(content_type=None)
                    if response.status != 200:
                        raise ReadinessFailure(f"CSRF 初始化失败（status={response.status}）")
                    csrf_token = str(body["data"]["csrf_token"])
                async with client.post(
                    f"{base_url}/api/v1/auth/login",
                    json={"identifier": identifier, "password": password},
                    headers={"X-CSRF-Token": csrf_token},
                ) as response:
                    body = await response.json(content_type=None)
                    if response.status != 200:
                        code = str((body.get("error") or {}).get("code") or "UNKNOWN")
                        raise ReadinessFailure(f"压测账号登录失败（status={response.status}, code={code}）")
                result.append((client, csrf_token))
            except Exception:
                await client.close()
                raise
        return result
    except Exception:
        await asyncio.gather(*(client.close() for client, _token in result), return_exceptions=True)
        raise


async def _request_one(
    base_url: str,
    item: WorkItem,
    client: Any,
    csrf_token: str,
    start: asyncio.Event,
    stage_started: float,
) -> dict[str, Any]:
    await start.wait()
    launched = time.perf_counter()
    try:
        headers = {"X-CSRF-Token": csrf_token} if item.method == "POST" else None
        async with client.request(
            item.method, f"{base_url}{item.path}", json=item.payload, headers=headers
        ) as response:
            try:
                body = await response.json(content_type=None)
            except Exception:
                body = {}
            expected_status = 201 if item.method == "POST" else 200
            error = body.get("error") if isinstance(body, dict) else None
            return {
                "status": response.status,
                "success": response.status == expected_status,
                "latency": time.perf_counter() - launched,
                "launch_offset": launched - stage_started,
                "error_code": str((error or {}).get("code") or "") if isinstance(error, dict) else "",
            }
    except asyncio.TimeoutError:
        error_code = "CLIENT_TIMEOUT"
    except Exception as exc:
        error_code = type(exc).__name__
    return {
        "status": 0,
        "success": False,
        "latency": time.perf_counter() - launched,
        "launch_offset": launched - stage_started,
        "error_code": error_code,
    }


async def _run_stage(
    *,
    base_url: str,
    clients: list[tuple[Any, str]],
    settings: Settings,
    backend_pid: int,
    total: int,
    run_id: str,
    p95_limit: float,
    p99_limit: float,
) -> dict[str, Any]:
    import psutil

    workload = generate_workload(total, stage=total, run_id=run_id)
    code_prefix = f"TEST_LOAD_{run_id}_{total}_"
    stop_sampling = threading.Event()
    process = psutil.Process(backend_pid)
    process.cpu_percent(None)
    process_metrics = {"rss_peak_bytes": process.memory_info().rss, "cpu_peak_percent": 0.0}

    def sample_process() -> None:
        while not stop_sampling.wait(0.05):
            try:
                process_metrics["rss_peak_bytes"] = max(
                    process_metrics["rss_peak_bytes"], process.memory_info().rss
                )
                process_metrics["cpu_peak_percent"] = max(
                    process_metrics["cpu_peak_percent"], process.cpu_percent(None)
                )
            except (psutil.Error, OSError):
                return

    sampler = threading.Thread(target=sample_process, name="readiness-load-sampler", daemon=True)
    sampler.start()
    mysql_before = mysql_global_status(require_database_tools())
    start = asyncio.Event()
    stage_started = time.perf_counter()
    tasks = [
        asyncio.create_task(
            _request_one(
                base_url,
                item,
                clients[index % len(clients)][0],
                clients[index % len(clients)][1],
                start,
                stage_started,
            )
        )
        for index, item in enumerate(workload)
    ]
    await asyncio.sleep(0)
    stage_started = time.perf_counter()
    start.set()
    results = await asyncio.gather(*tasks)
    wall_seconds = time.perf_counter() - stage_started
    stop_sampling.set()
    sampler.join(timeout=2)
    mysql_after = mysql_global_status(require_database_tools())

    latencies = [float(item["latency"]) for item in results]
    successes = sum(bool(item["success"]) for item in results)
    server_errors = sum(int(item["status"]) >= 500 for item in results)
    write_expected = sum(item.method == "POST" for item in workload)
    write_actual = count_stage_writes(settings, code_prefix)
    assessment = assess_load(
        total=total,
        successes=successes,
        latencies=latencies,
        server_errors=server_errors,
        write_expected=write_expected,
        write_actual=write_actual,
        p95_limit=p95_limit,
        p99_limit=p99_limit,
    )
    statuses = Counter(str(item["status"]) for item in results)
    errors = Counter(str(item["error_code"]) for item in results if item["error_code"])
    return {
        **asdict(assessment),
        "p95": round(assessment.p95, 4),
        "p99": round(assessment.p99, 4),
        "max_latency": round(max(latencies), 4),
        "wall_seconds": round(wall_seconds, 4),
        "launch_spread_seconds": round(max(float(item["launch_offset"]) for item in results), 4),
        "requests_per_second": round(total / wall_seconds, 2),
        "statuses": dict(statuses),
        "error_codes": dict(errors),
        "backend_process": process_metrics,
        "mysql_before": mysql_before,
        "mysql_after": mysql_after,
    }


async def execute_stages(
    *,
    base_url: str,
    identifiers: list[str],
    password: str,
    settings: Settings,
    backend_pid: int,
    levels: list[int],
    run_id: str,
    p95_limit: float,
    p99_limit: float,
) -> list[dict[str, Any]]:
    clients = await _login_sessions(base_url, identifiers, password)
    try:
        return [
            await _run_stage(
                base_url=base_url,
                clients=clients,
                settings=settings,
                backend_pid=backend_pid,
                total=level,
                run_id=run_id,
                p95_limit=p95_limit,
                p99_limit=p99_limit,
            )
            for level in levels
        ]
    finally:
        await asyncio.gather(*(client.close() for client, _token in clients), return_exceptions=True)
