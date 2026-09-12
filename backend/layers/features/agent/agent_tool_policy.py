"""把 ADP 的 HTTP 操作映射为 Agent 工具所需的策略层。

这里只回答「一个 (path, method) 应该对应什么权限、什么风险等级、是否受数据范围
约束」，不涉及 OpenAPI 解析与工具注册，因此可以独立测试与复用。

本模块由 ``agent_tool_registry`` 使用；拆出来的目的是让工具注册表保持单一职责，
并把文件控制在项目 `tools/audit_source.py --strict` 的 300 行上限之内。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from backend.layers.features.agent.agent_permission_mapping import specialized_permission

if TYPE_CHECKING:  # 仅用于类型标注，避免与注册表互相导入
    from backend.layers.features.agent.agent_tool_registry import AgentTool

Risk = Literal["read", "write", "human_only"]
Method = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]

_DOMAIN_PERMISSIONS = {
    "cost": "cost",
    "data-exchange": "data_exchange",
    "master-data": "master_data",
    "production": "production",
    "purchase": "purchase",
    "sales": "sales",
    "warehouse": "warehouse",
    "workbench": "work_item",
}
_VERIFY_PATH_MARKERS = {
    "approve", "reject", "verify", "dispatch", "receive", "cancel",
}


def domain(path: str) -> str:
    segments = path.strip("/").split("/")
    return segments[2] if len(segments) > 2 else ""


def schema_for(method: str, path: str = "") -> dict[str, Any]:
    if method == "GET":
        schema = {
            "page": {"type": "integer", "minimum": 1},
            "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
            "keyword": {"type": "string", "maxLength": 100},
            "status": {"type": "string"},
        }
        if path == "/api/v1/production/{resource}":
            schema["uninspected_on"] = {"type": "string", "description": "只读未巡检塘口查询日期，使用 today 或 YYYY-MM-DD"}
        return schema
    schema = {
        "payload": {"type": "object", "required": True},
        "expected_version": {"type": "integer", "minimum": 1},
    }
    if method in {"PUT", "PATCH"} and "{record_id}" in path:
        schema["expected_version"]["required"] = True
    return schema


def permission_action(path: str, method: str) -> str:
    if method == "GET":
        return "view"
    last_segments = {segment for segment in path.strip("/").split("/") if not segment.startswith("{")}
    if last_segments & _VERIFY_PATH_MARKERS:
        return "verify"
    return "manage"


def permission_for(path: str, method: str) -> str | None:
    if path == "/api/v1/workbench/summary":
        return "workbench.enter"
    name = domain(path)
    if name in {"work-items", "notifications"}:
        return "work_item.view" if method == "GET" else "work_item.manage"
    if name == "admin":
        if "/roles" in path:
            return "auth.role.manage"
        if "/applications" in path:
            return "auth.review"
        if "/audit-logs" in path:
            return "audit.view"
        return "auth.user.manage"
    specialized = specialized_permission(path, method, name)
    if specialized is not None:
        return specialized
    prefix = _DOMAIN_PERMISSIONS.get(name)
    if prefix is None:
        return None
    return f"{prefix}.{permission_action(path, method)}"


def risk_for(method: str, path: str) -> Risk:
    # Authentication/session lifecycle must remain outside the delegated agent
    # because those endpoints create or replace the identity the agent inherits.
    if domain(path) == "auth" and method != "GET":
        return "human_only"
    # File uploads are multipart-only; the Agent gateway intentionally accepts
    # JSON and must not advertise a non-executable binary write tool.
    if method == "POST" and path == "/api/v1/data-exchange/attachments":
        return "human_only"
    if method == "GET":
        return "read"
    return "write"


def required_role_for(path: str) -> str | None:
    return "super_admin" if domain(path) == "admin" else None


def permission_namespace_for(path: str) -> str | None:
    return _DOMAIN_PERMISSIONS.get(domain(path))


def resource_argument_for(path: str) -> str | None:
    if "{resource}" in path and domain(path) in {"master-data", "production", "warehouse"}:
        return "resource"
    return None


def requires_data_scope(path: str) -> bool:
    return domain(path) not in {"admin", "auth", "health"}


def permission_options(tool: "AgentTool", arguments: dict[str, Any]) -> tuple[str, ...]:
    """Return every permission that may authorize this concrete operation.

    This mirrors business-service alternatives for generic resource routes.
    The business endpoint remains the final authorization authority.
    """
    options: list[str] = []
    if tool.required_permission:
        options.append(tool.required_permission)

    if tool.permission_namespace and tool.permission_action and tool.resource_argument:
        payload = arguments.get("payload") if isinstance(arguments.get("payload"), dict) else {}
        resource = arguments.get(tool.resource_argument, payload.get(tool.resource_argument))
        if isinstance(resource, str) and resource.strip():
            resource_code = resource.strip().replace("-", "_")
            if tool.permission_namespace in {"master_data", "production"}:
                options.append(f"{tool.permission_namespace}.{resource_code}.{tool.permission_action}")
            if tool.permission_namespace == "warehouse" and resource.strip() == "issue-requests":
                options.append(f"production.{tool.permission_action}")

    # Return services accept both their fine-grained permission and the legacy
    # domain-wide permission; keep the agent pre-check equivalent to the API.
    if "/purchase/returns" in tool.path_template:
        if tool.required_permission == "purchase.return.manage":
            options.append("purchase.manage")
        elif tool.required_permission == "purchase.return.verify":
            options.append("purchase.verify")
    if "/sales/returns" in tool.path_template:
        if tool.required_permission == "sales.return.manage":
            options.append("sales.manage")
        elif tool.required_permission == "sales.return.verify":
            options.append("sales.verify")

    # Preserve order for predictable diagnostics while removing duplicates.
    return tuple(dict.fromkeys(options))
