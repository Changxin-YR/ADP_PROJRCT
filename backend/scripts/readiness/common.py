from __future__ import annotations

import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


class ReadinessFailure(RuntimeError):
    """A readiness gate failed without exposing credentials or internal secrets."""


_SENSITIVE_FRAGMENTS = (
    "password",
    "token",
    "secret",
    "cookie",
    "csrf",
    "credential",
    "private_key",
    "api_key",
)
_DATABASE_NAME = re.compile(
    r"adp_readiness_(?:source|restore|load|export)_[a-f0-9]{12}"
)


def percentile(samples: Sequence[float], value: int) -> float:
    ordered = sorted(float(sample) for sample in samples)
    if not ordered:
        raise ReadinessFailure("没有可计算的延迟样本")
    if value < 0 or value > 100:
        raise ReadinessFailure("百分位必须在 0 到 100 之间")
    index = max(0, math.ceil(len(ordered) * value / 100) - 1)
    return ordered[index]


def _redact(value: Any, *, key: str | None = None) -> Any:
    normalized = (key or "").lower().replace("-", "_")
    if normalized and any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _redact(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def evidence(probe: str, metrics: dict[str, Any], *, passed: bool) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "probe": probe,
        "status": "PASS" if passed else "FAIL",
        "started_at": now,
        "finished_at": now,
        "metrics": _redact(metrics),
    }


def require_disposable_database_name(name: str) -> str:
    if _DATABASE_NAME.fullmatch(name) is None:
        raise ReadinessFailure("拒绝操作非 readiness 一次性数据库")
    return name


def safe_remove_tree(target: Path, *, allowed_parent: Path) -> None:
    resolved_target = target.resolve()
    resolved_parent = allowed_parent.resolve()
    if (
        resolved_target == resolved_parent
        or resolved_parent not in resolved_target.parents
        or not resolved_target.name.startswith("adp-readiness-")
    ):
        raise ReadinessFailure("拒绝清理未经授权的目录")
    if resolved_target.exists():
        shutil.rmtree(resolved_target)
