"""写工具落地：把「智能体已经动手了」这件事描述成业务人话。

``prepare_tool`` 在直连模式下会调用这里的 :func:`describe_success`；失败路径仍由网关
统一收口（审计 + 确认记录状态），保证与人工确认流程一致的可追溯性。
"""

from __future__ import annotations

from typing import Any

from backend.layers.features.agent import agent_humanize


def execution_payload(tool: Any, arguments: dict[str, Any], body: Any) -> dict[str, Any]:
    """把一次成功的写调用翻译成前端可直接显示的结构。"""
    title = agent_humanize.action_noun(
        tool.method,
        tool.path_template,
        resource=agent_humanize.resource_code(tool.path_template, arguments),
    )
    detail = agent_humanize.summarize(body, title=title)
    rows = agent_humanize.change_rows(arguments)
    return {
        "title": title,
        "detail": detail,
        "summary": detail,
        "changes": rows,
        "rows_changed": _rows_changed(body),
    }


def describe_success(tool: Any, arguments: dict[str, Any], body: Any) -> str:
    """一句人话，作为对话气泡的正文。"""
    return execution_payload(tool, arguments, body)["detail"]


def _rows_changed(body: Any) -> int | None:
    if isinstance(body, list):
        return len(body)
    if not isinstance(body, dict):
        return None
    for key in ("items", "records", "rows"):
        value = body.get(key)
        if isinstance(value, list):
            return len(value)
    return 1 if body else None
