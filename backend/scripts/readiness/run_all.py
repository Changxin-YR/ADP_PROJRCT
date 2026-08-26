from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


REQUIRED_PROBES = (
    "database-drill",
    "attachment-security",
    "large-export",
    "http-load",
)


def summarize_results(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_probe = {str(item.get("probe")): item for item in results}
    statuses = {
        probe: str((by_probe.get(probe) or {}).get("status") or "NOT_RUN")
        for probe in REQUIRED_PROBES
    }
    passed = all(status == "PASS" for status in statuses.values())
    return {
        "probe": "readiness-summary",
        "status": "PASS" if passed else "FAIL",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "probe_statuses": statuses,
            "required_probes": list(REQUIRED_PROBES),
            "environment_limitations": [
                "数据库、导出和并发结果来自一次性本地 MySQL，不等同于生产数据已恢复",
                "500 并发来自 Windows 本地 Flask 候选基线，不替代 Linux Gunicorn/反向代理压测",
                "恶意内容探针验证本机 Windows Defender；生产必须配置实际部署环境扫描器",
            ],
        },
    }


def _not_run(probe: str, reason: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "probe": probe,
        "status": "NOT_RUN",
        "started_at": now,
        "finished_at": now,
        "metrics": {"reason": reason},
    }


def _run_probe(module: str, probe: str, path: Path, arguments: list[str], timeout: int) -> dict[str, Any]:
    path.unlink(missing_ok=True)
    completed = subprocess.run(
        [sys.executable, "-m", module, "--output", str(path), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if path.is_file():
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result = {}
        if result.get("probe") == probe and result.get("status") in {"PASS", "FAIL"}:
            return result
    now = datetime.now(timezone.utc).isoformat()
    return {
        "probe": probe,
        "status": "FAIL",
        "started_at": now,
        "finished_at": now,
        "metrics": {
            "runner_exit_code": completed.returncode,
            "error": "探针未生成有效证据文件",
        },
    }


def _write_json(path: Path, result: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_markdown(path: Path, summary: dict[str, Any]) -> None:
    statuses = summary["metrics"]["probe_statuses"]
    labels = {
        "database-drill": "迁移/备份/恢复/对账",
        "attachment-security": "附件结构与 Defender 恶意内容扫描",
        "large-export": "10 万行 XLSX/PDF 导出",
        "http-load": "10→500 HTTP 并发",
    }
    lines = [
        "# Enterprise readiness summary",
        "",
        f"总状态：**{summary['status']}**",
        "",
        "| 探针 | 状态 |",
        "|---|---|",
        *[f"| {labels[probe]} | {statuses[probe]} |" for probe in REQUIRED_PROBES],
        "",
        "## 适用边界",
        "",
        *[f"- {item}" for item in summary["metrics"]["environment_limitations"]],
        "",
    ]
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(path)


def run_all(output_directory: Path) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    database = _run_probe(
        "backend.scripts.readiness.database_drill",
        "database-drill",
        output_directory / "database-drill.json",
        [],
        180,
    )
    results.append(database)
    results.append(
        _run_probe(
            "backend.scripts.readiness.attachment_probe",
            "attachment-security",
            output_directory / "attachment-security.json",
            [],
            60,
        )
    )
    if database["status"] == "PASS":
        results.append(
            _run_probe(
                "backend.scripts.readiness.export_probe",
                "large-export",
                output_directory / "large-export.json",
                [],
                240,
            )
        )
        results.append(
            _run_probe(
                "backend.scripts.readiness.load_probe",
                "http-load",
                output_directory / "http-load.json",
                ["--levels", "10,50,100,500", "--p95", "3", "--p99", "5"],
                240,
            )
        )
    else:
        for probe, filename in (("large-export", "large-export.json"), ("http-load", "http-load.json")):
            result = _not_run(probe, "数据库 readiness 探针未通过")
            results.append(result)
            _write_json(output_directory / filename, result)

    summary = summarize_results(results)
    _write_json(output_directory / "readiness-summary.json", summary)
    _write_markdown(output_directory / "readiness-summary.md", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all ADP enterprise readiness probes")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    summary = run_all(args.output_dir.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
