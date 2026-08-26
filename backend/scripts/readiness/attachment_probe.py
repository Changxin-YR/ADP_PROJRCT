from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.layers.common.files.malware_scanner import CommandMalwareScanner, MalwareDetected
from backend.scripts.readiness.common import ReadinessFailure, evidence


def _defender_status() -> dict[str, Any]:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        raise ReadinessFailure("未找到 PowerShell，无法读取 Defender 状态")
    command = (
        "$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new();"
        "Get-MpComputerStatus | Select-Object AntivirusEnabled,"
        "RealTimeProtectionEnabled,AMServiceEnabled,AntivirusSignatureVersion,"
        "AntivirusSignatureLastUpdated | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
        shell=False,
    )
    if completed.returncode:
        raise ReadinessFailure("无法读取 Windows Defender 状态")
    try:
        status = json.loads(completed.stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReadinessFailure("Windows Defender 状态输出无效") from exc
    return status


def _signature_timestamp(raw_value: object) -> datetime | None:
    match = re.search(r"Date\((\d+)\)", str(raw_value))
    if not match:
        return None
    return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc)


def _defender_executable() -> Path:
    platform = Path(r"C:\ProgramData\Microsoft\Windows Defender\Platform")
    candidates = list(platform.glob("*/MpCmdRun.exe")) + list(platform.glob("*/X86/MpCmdRun.exe"))
    if not candidates:
        raise ReadinessFailure("未找到 Windows Defender 命令行扫描器")
    return max(candidates, key=lambda path: path.stat().st_mtime).resolve()


def _eicar_test_content() -> bytes:
    # Deliberately assembled at runtime so the harmless antivirus test signature is not stored in source.
    return b"".join(
        (
            b"X5O!P%@AP[4",
            bytes((92,)),
            b"PZX54(P^)7CC)7}$",
            b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!",
            b"$H+H*",
        )
    )


def run_probe(output: Path) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    passed = False
    temporary_root = Path(tempfile.gettempdir()).resolve()
    before = {path.resolve() for path in temporary_root.glob("adp-scan-*")}
    try:
        status = _defender_status()
        executable = _defender_executable()
        signature_at = _signature_timestamp(status.get("AntivirusSignatureLastUpdated"))
        signature_age_hours = (
            (datetime.now(timezone.utc) - signature_at).total_seconds() / 3600
            if signature_at
            else None
        )
        scanner = CommandMalwareScanner(
            (
                str(executable),
                "-Scan",
                "-ScanType",
                "3",
                "-File",
                "{path}",
                "-DisableRemediation",
            ),
            timeout_seconds=30,
            threat_exit_codes=(2,),
        )
        detected = False
        try:
            scanner.scan(content=_eicar_test_content(), original_name="antivirus-test.txt")
        except MalwareDetected:
            detected = True

        after = {path.resolve() for path in temporary_root.glob("adp-scan-*")}
        leftovers = sorted(str(path.name) for path in after - before)
        cleanup = not leftovers
        metrics.update(
            antivirus_enabled=bool(status.get("AntivirusEnabled")),
            realtime_enabled=bool(status.get("RealTimeProtectionEnabled")),
            service_enabled=bool(status.get("AMServiceEnabled")),
            signature_version=str(status.get("AntivirusSignatureVersion") or ""),
            signature_updated_at=signature_at.isoformat() if signature_at else None,
            signature_age_hours=round(signature_age_hours, 2) if signature_age_hours is not None else None,
            platform_version=executable.parent.parent.name if executable.parent.name == "X86" else executable.parent.name,
            detected=detected,
            cleanup=cleanup,
            cleanup_leftovers=leftovers,
        )
        passed = all(
            (
                metrics["antivirus_enabled"],
                metrics["realtime_enabled"],
                metrics["service_enabled"],
                bool(metrics["signature_version"]),
                signature_age_hours is not None and signature_age_hours <= 72,
                detected,
                cleanup,
            )
        )
    except Exception as exc:
        metrics["error_type"] = type(exc).__name__
        metrics["error"] = str(exc)
    result = evidence("attachment-security", metrics, passed=passed)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="ADP Windows Defender attachment readiness probe")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_probe(args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
