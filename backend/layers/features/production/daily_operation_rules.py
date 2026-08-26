from __future__ import annotations

from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError

# 日常作业类型化（BUG-012 最小方案）：作业类型 -> 必填关键参数（缺失 → 400）。
# 与 ADP 功能文档 §11.1 对齐：巡塘 / 换水 / 用药 / 增氧 / 水质检测 / 设备维护 / 其他。
DAILY_OPERATION_TYPES = {
    "patrol": (("water_quality", "水质观察结果"), ("fish_activity", "鱼群活动情况")),
    "water_change": (("volume_m3", "换水数量"), ("water_source", "水源")),
    "medicine": (("medicine_name", "药品名称"), ("dosage", "用量"), ("usage_method", "使用方式"), ("safety_interval_days", "安全间隔")),
    "aeration": (("equipment_name", "增氧设备"), ("runtime_hours", "运行时长"), ("reason", "开启原因")),
    "water_quality": (("temperature_c", "水温"), ("ph", "pH"), ("dissolved_oxygen_mg_l", "溶解氧")),
    "equipment_maintenance": (("equipment_name", "设备名称"), ("fault_description", "故障描述"), ("repair_content", "维修内容")),
    "other": (("description", "作业说明"),),
}
DAILY_OPERATION_TYPE_LABELS = {
    "patrol": "巡塘", "water_change": "换水", "medicine": "用药",
    "aeration": "增氧", "water_quality": "水质检测", "equipment_maintenance": "设备维护", "other": "其他",
}
DAILY_OPERATION_PAYLOAD_KEYS = {"operation_type", "source_detail"}


def normalize_daily_operation_payload(clean: dict[str, Any], current_payload: dict[str, Any] | None) -> None:
    """校验并归一化作业类型与关键参数，落 payload_json 统一结构：

    {"operation_type": <枚举>, "source_detail": {参数: 值}}

    未提供任何类型化字段时保持通用表单行为不变（向后兼容既有记录）。
    """
    merged = dict(current_payload or {})
    if isinstance(clean.get("payload"), dict):
        merged.update(clean["payload"])
    provided_type = clean.pop("operation_type", None)
    if provided_type is None and not merged and "payload" not in clean:
        return
    operation_type = str(provided_type or merged.get("operation_type") or "other")
    if operation_type not in DAILY_OPERATION_TYPES:
        raise DomainError(
            "DAILY_OP_TYPE_INVALID",
            "作业类型必须是 patrol、water_change、medicine、aeration、water_quality、equipment_maintenance 或 other",
            400,
        )
    source_detail = merged.get("source_detail") if isinstance(merged.get("source_detail"), dict) else {}
    # 允许平铺传参：除保留键外全部并入 source_detail。
    for key, value in list(merged.items()):
        if key not in DAILY_OPERATION_PAYLOAD_KEYS and key not in source_detail:
            source_detail[key] = value
    missing = [
        label
        for key, label in DAILY_OPERATION_TYPES[operation_type]
        if not str(source_detail.get(key) or "").strip()
    ]
    if missing:
        raise DomainError(
            "DAILY_OP_PARAM_REQUIRED",
            f"{DAILY_OPERATION_TYPE_LABELS[operation_type]}作业缺少关键参数：{'、'.join(missing)}",
            400,
        )
    positive_fields = {
        "water_change": ("volume_m3",),
        "medicine": ("dosage",),
        "aeration": ("runtime_hours",),
        "water_quality": ("temperature_c", "dissolved_oxygen_mg_l"),
    }.get(operation_type, ())
    for key in positive_fields:
        try:
            value = float(source_detail[key])
        except (TypeError, ValueError) as exc:
            raise DomainError("DAILY_OP_PARAM_INVALID", f"{key} 必须是有效数字", 400) from exc
        if not isfinite(value):
            raise DomainError("DAILY_OP_PARAM_INVALID", f"{key} 必须是有效数字", 400)
        if value <= 0:
            raise DomainError("DAILY_OP_PARAM_INVALID", f"{key} 必须大于 0", 400)
    if operation_type == "medicine":
        try:
            raw_interval = Decimal(str(source_detail["safety_interval_days"]))
            if not raw_interval.is_finite() or raw_interval != raw_interval.to_integral_value():
                raise InvalidOperation
            interval = int(raw_interval)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise DomainError("DAILY_OP_PARAM_INVALID", "安全间隔必须是非负整数", 400) from exc
        if interval < 0:
            raise DomainError("DAILY_OP_PARAM_INVALID", "安全间隔必须是非负整数", 400)
    if operation_type == "water_quality":
        try:
            ph = float(source_detail["ph"])
        except (TypeError, ValueError) as exc:
            raise DomainError("DAILY_OP_PARAM_INVALID", "pH 必须是有效数字", 400) from exc
        if not isfinite(ph):
            raise DomainError("DAILY_OP_PARAM_INVALID", "pH 必须是有效数字", 400)
        if not 0 <= ph <= 14:
            raise DomainError("DAILY_OP_PARAM_INVALID", "pH 必须在 0 到 14 之间", 400)
    clean["payload"] = {"operation_type": operation_type, "source_detail": source_detail}
