"""把 ADP 的工具调用翻译成业务人员看得懂的中文。

智能体对外只说「人话」：不说 ``api.production_create_...``、``POST``、``JSON``、
``weight_kg`` 这类机器标识。词典在 :mod:`agent_labels`，本模块只负责组合：

* :func:`action_title` —— 这次调用做了什么（新增投喂记录 / 核验销售单）；
* :func:`summarize` —— 结果用一句话讲清楚；
* :func:`change_rows` —— 参数翻译成「字段名 → 值」供确认卡片与完成提示使用。

只做展示层翻译，绝不改变业务语义，也绝不吞掉错误信息。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.features.agent.agent_labels import (
    FIELD_LABELS,
    PATH_ACTIONS,
    PATH_TAILS,
    RESOURCE_LABELS,
    VERB_ACTIONS,
)

_LIST_KEYS = ("items", "records", "rows", "list", "results", "data")
_COUNT_KEYS = ("total", "count", "total_count")
_NAME_KEYS = ("name", "pond_name", "material_name", "title")
_MISSING = object()


def resource_code(path: str, arguments: dict[str, Any] | None = None) -> str:
    """从路径（或 arguments.resource）取出资源代码，用于查中文名。"""
    payload = arguments if isinstance(arguments, dict) else {}
    explicit = payload.get("resource") or payload.get("resource_type")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    segments = [segment for segment in str(path or "").strip("/").split("/") if segment]
    for segment in segments[3:]:
        if not segment.startswith("{") and segment not in PATH_TAILS:
            return segment
    return ""


def resource_label(resource: str) -> str:
    code = str(resource or "").strip()
    if not code:
        return "业务数据"
    # 未登记的资源不把英文 code 甩给用户，退回一个中性的业务说法。
    return RESOURCE_LABELS.get(code) or RESOURCE_LABELS.get(code.replace("_", "-")) or "该业务对象"


def action_title(method: str, path: str, *, resource: str = "", record_id: Any = None) -> str:
    """一句话动作标题：优先精确路径，其次按资源 + 动词。"""
    verb = str(method or "").upper()
    exact = PATH_ACTIONS.get((verb, path))
    if exact:
        return exact
    label = resource_label(resource or resource_code(path))
    tail = str(path or "").strip("/").split("/")[-1]
    if tail in PATH_TAILS:
        return f"{PATH_TAILS[tail]}{label}"
    if record_id is not None and verb == "POST":
        return f"更正{label}"
    return f"{VERB_ACTIONS.get(verb, '处理')}{label}"


def target_label(path: str, arguments: dict[str, Any] | None) -> str:
    """这次操作影响的对象：能拿到名称/编码就带上，否则退回资源名。

    前端确认卡片显示「影响对象：塘口档案 一号塘」，而不是把动作名重复一遍。
    """
    payload = arguments if isinstance(arguments, dict) else {}
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    label = resource_label(resource_code(path, payload))
    for source in (body, payload):
        for key in ("pond_name", "batch_name", "material_name", "name", "title"):
            value = source.get(key)
            if value not in (None, ""):
                return f"{label} {value}"
        for key in ("pond_code", "batch_code", "code", "order_no", "entry_no", "doc_no"):
            value = source.get(key)
            if value not in (None, ""):
                return f"{label} {value}"
    return label


def action_noun(method: str, path: str, *, resource: str = "", record_id: Any = None) -> str:
    """写入完成时说的名词短语（与 :func:`action_title` 同义，保留语义位）。"""
    return action_title(method, path, resource=resource, record_id=record_id)


def _first(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key, _MISSING)
        if value is not _MISSING and value not in (None, ""):
            return value
    return None


def _count_of(payload: dict[str, Any]) -> int | None:
    for key in _COUNT_KEYS:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    for key in _LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def _number_text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if decimal == decimal.to_integral_value():
        return f"{int(decimal):,}"
    # 字符串型数字（"1234.50"）也要带千分位，否则和 int/Decimal 的输出口径不一致。
    return f"{decimal.normalize():,f}"


def describe_record(row: dict[str, Any]) -> str:
    """把一条业务记录讲成一句短话：优先「名称」，其次「编码」，再退回数量。"""
    name = _first(row, _NAME_KEYS)
    code = row.get("code")
    weight = _first(row, ("weight_kg",))
    quantity = _first(row, ("quantity",))
    parts: list[str] = []
    if name is not None:
        parts.append(f"「{name}」")
    elif code is not None:
        parts.append(f"编码 {code}")
    if weight is not None:
        number = _number_text(weight)
        if number:
            parts.append(f"{number} kg")
    elif quantity is not None:
        number = _number_text(quantity)
        if number:
            parts.append(f"{number} 尾")
    return "，".join(parts) if parts else "一条记录"


def summarize(data: Any, *, title: str = "") -> str:
    """把工具返回的数据讲成一句中文（不出现 JSON、字段名或接口名）。"""
    if data is None:
        return f"{title}已完成。" if title else "操作已完成。"
    if isinstance(data, bool):
        if title:
            return f"{title}{'成功' if data else '未成功'}。"
        return "操作成功。" if data else "操作未成功。"
    if isinstance(data, str):
        text = data.strip()
        return text or (f"{title}已完成。" if title else "操作已完成。")
    if isinstance(data, list):
        prefix = f"{title}完成，" if title else ""
        if not data:
            return f"{prefix}没有符合条件的记录。"
        rows = [describe_record(row) for row in data[:5] if isinstance(row, dict)]
        return f"{prefix}共 {len(data)} 条：{'；'.join(rows)}。"
    if not isinstance(data, dict):
        return f"{title}已完成。" if title else "操作已完成。"

    for key in _LIST_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return summarize(value, title=title)
    record = _first(data, ("record", "row", "result"))
    if isinstance(record, dict):
        return summarize(record, title=title)

    pieces: list[str] = []
    label = _first(data, _NAME_KEYS)
    code = data.get("code")
    if label is not None:
        pieces.append(f"「{label}」")
        if code is not None:
            pieces.append(f"编码 {code}")
    elif code is not None:
        pieces.append(f"编码 {code}")
    for key, unit in (("quantity", "尾"), ("weight_kg", "kg"), ("amount", "元")):
        number = _number_text(data.get(key))
        if number:
            pieces.append(f"{number}{unit}")
    head = f"{title}完成" if title else "已完成"
    if pieces:
        return f"{head}：{'，'.join(pieces)}。"
    count = _count_of(data)
    if isinstance(count, int):
        return f"{head}，共 {count} 条。"
    return f"{head}。"


def _humanize_key(key: str) -> str:
    """未知字段的可读兜底：a_b_c → A B C，避免暴露 snake_case。"""
    return str(key).replace("_", " ").strip() or str(key)


def change_rows(arguments: dict[str, Any] | None) -> list[dict[str, str]]:
    """把参数翻译成「字段名 → 值」，供确认卡片与完成提示展示。"""
    payload = arguments if isinstance(arguments, dict) else {}
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    merged: dict[str, Any] = {}
    for source in (body, payload):
        for key, value in source.items():
            if key in {"payload", "expected_version", "raw_instruction"}:
                continue
            if value in (None, "", [], {}):
                continue
            merged.setdefault(str(key), value)

    rows: list[dict[str, str]] = []
    for key, value in merged.items():
        label = FIELD_LABELS.get(key, _humanize_key(key))
        if key in {"resource", "resource_type"}:
            # 面向业务人员说「投喂记录」，不要说 feed-logs。
            value = resource_label(str(value))
        if isinstance(value, list):
            text = "、".join(str(item) for item in value) or "（空）"
        elif isinstance(value, dict):
            text = "、".join(
                f"{FIELD_LABELS.get(str(inner_key), _humanize_key(str(inner_key)))} {inner_value}"
                for inner_key, inner_value in value.items()
            )
        else:
            text = str(value)
        rows.append({"label": label, "value": text[:120]})
    # 「对象类型」是解释性字段，放在最后，读起来更像业务说明而不是参数表。
    return sorted(rows, key=lambda row: row["label"] == "对象类型")
