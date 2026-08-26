from __future__ import annotations

from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def apply_record_filters(clauses: list[str], values: list[Any], *, pond_id: Any = None, area_id: Any = None) -> None:
    """塘口/区域筛选真实生效（BUG-M1-001）：解析失败 400，与调用方已有数据范围子句叠加。"""
    for key, provided in (("pond_id", pond_id), ("area_id", area_id)):
        if provided in (None, ""):
            continue
        try:
            filter_value = int(provided)
        except (TypeError, ValueError) as exc:
            raise DomainError("PRODUCTION_FILTER_INVALID", f"筛选参数 {key} 无效", 400) from exc
        if filter_value > 0:
            clauses.append(f"{key} = %s")
            values.append(filter_value)
