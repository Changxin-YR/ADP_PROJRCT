from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Literal
from backend.layers.features.agent.agent_permission_mapping import specialized_permission
Risk = Literal["read", "write", "human_only"]
Method = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
ToolExecutor = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    method: Method
    path_template: str
    parameters: dict[str, Any]
    required_permission: str | None
    risk: Risk
    execute: ToolExecutor | None = None
    required_role: str | None = None
    permission_namespace: str | None = None
    permission_action: str | None = None
    resource_argument: str | None = None
    requires_data_scope: bool = True
class AgentToolRegistry:
    def __init__(self, tools: tuple[AgentTool, ...]) -> None:
        self.tools = tools
        self._by_name = {tool.name: tool for tool in tools}
        self._by_operation = {(tool.method, tool.path_template): tool for tool in tools}
        if len(self._by_name) != len(tools):
            raise ValueError("duplicate agent tool names are not allowed")
        if len(self._by_operation) != len(tools):
            raise ValueError("duplicate agent tool operations are not allowed")
    def get(self, name: str) -> AgentTool:
        return self._by_name[name]
    def require(self, name: str) -> AgentTool:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise KeyError(f"unknown agent tool: {name}") from exc
    def find_operation(self, method: str, path_template: str) -> AgentTool | None:
        return self._by_operation.get((method.upper(), path_template))
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
def _domain(path: str) -> str:
    segments = path.strip("/").split("/")
    return segments[2] if len(segments) > 2 else ""
def _schema_for(method: str) -> dict[str, Any]:
    if method == "GET":
        return {
            "page": {"type": "integer", "minimum": 1},
            "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
            "keyword": {"type": "string", "maxLength": 100},
            "status": {"type": "string"},
        }
    return {
        "payload": {"type": "object", "required": True},
        "expected_version": {"type": "integer", "minimum": 1},
    }
def _permission_action(path: str, method: str) -> str:
    if method == "GET":
        return "view"
    last_segments = {segment for segment in path.strip("/").split("/") if not segment.startswith("{")}
    if last_segments & _VERIFY_PATH_MARKERS:
        return "verify"
    return "manage"
def _permission_for(path: str, method: str) -> str | None:
    if path == "/api/v1/workbench/summary": return "workbench.enter"
    domain = _domain(path)
    if domain in {"work-items", "notifications"}:
        return "work_item.view" if method == "GET" else "work_item.manage"
    if domain == "admin":
        if "/roles" in path:
            return "auth.role.manage"
        if "/applications" in path:
            return "auth.review"
        if "/audit-logs" in path:
            return "audit.view"
        return "auth.user.manage"
    specialized = specialized_permission(path, method, domain)
    if specialized is not None:
        return specialized
    prefix = _DOMAIN_PERMISSIONS.get(domain)
    if prefix is None:
        return None
    return f"{prefix}.{_permission_action(path, method)}"
def _risk_for(method: str, path: str) -> Risk:
    # Authentication/session lifecycle must remain outside the delegated agent
    # because those endpoints create or replace the identity the agent inherits.
    if _domain(path) == "auth" and method != "GET":
        return "human_only"
    if method == "GET":
        return "read"
    return "write"
def _required_role_for(path: str) -> str | None:
    return "super_admin" if _domain(path) == "admin" else None
def _permission_namespace_for(path: str) -> str | None:
    domain = _domain(path)
    return _DOMAIN_PERMISSIONS.get(domain)
def _resource_argument_for(path: str) -> str | None:
    if "{resource}" in path and _domain(path) in {"master-data", "production", "warehouse"}:
        return "resource"
    return None
def _requires_data_scope(path: str) -> bool:
    return _domain(path) not in {"admin", "auth", "health"}
def permission_options(tool: AgentTool, arguments: dict[str, Any]) -> tuple[str, ...]:
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
def _tool_name(operation_id: str, method: str, path: str) -> str:
    if operation_id.startswith("master_data_list_records_"):
        return "master_data.list_records"
    if operation_id.startswith("master_data_create_record_"):
        return "master_data.create_record"
    if operation_id.startswith("master_data_get_record_"):
        return "master_data.get_record"
    if operation_id.startswith("production_records_") or operation_id.startswith("production_records_get"):
        return "production.list_records"
    if operation_id.startswith("warehouse_records_"):
        return "warehouse.list_records"
    if operation_id.startswith("purchase_orders_"):
        return "purchase.list_orders"
    if operation_id.startswith("sales_orders_"):
        return "sales.list_orders"
    if operation_id.startswith("cost_entries_"):
        return "cost.list_entries"
    if ":" not in operation_id and operation_id.startswith("data_exchange_preview_"):
        return "data_exchange.preview_import"
    if "/work-items" in path:
        return "workbench.list_work_items" if method == "GET" else "workbench.update_work_item"
    if path.startswith("/api/v1/admin"):
        if "create_user" in operation_id:
            return "admin.create_user"
        if "update_role_permissions" in operation_id:
            return "admin.update_role_permissions"
        if "update_grants" in operation_id:
            return "admin.update_grants"
        if "set_status" in operation_id:
            return "admin.set_status"
        if "reset_password" in operation_id:
            return "admin.reset_password"
        if "retire_user" in operation_id:
            return "admin.retire_user"
        if "review" in operation_id:
            return "admin.review_application"
        suffix = operation_id.removeprefix("admin_").split("_")[0]
        return f"admin.{suffix or 'operation'}"
    return f"api.{operation_id or method.lower()}"


def _openapi_tools() -> list[AgentTool]:
    source = Path(__file__).resolve().parents[4] / "api-docs" / "openapi.json"
    if not source.exists():
        return []
    spec = json.loads(source.read_text(encoding="utf-8"))
    tools: list[AgentTool] = []
    for path, operations in spec.get("paths", {}).items():
        if path.startswith("/api/v1/agent/"):
            continue
        for method, operation in operations.items():
            method_upper = method.upper()
            if method_upper not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            operation_id = str(operation.get("operationId") or "")
            name = _tool_name(operation_id, method_upper, path)
            permission = _permission_for(path, method_upper)
            namespace = _permission_namespace_for(path)
            action = _permission_action(path, method_upper) if namespace else None
            tools.append(
                AgentTool(
                    name=name,
                    description=str(operation.get("summary") or "ADP 业务操作"),
                    method=method_upper,  # type: ignore[arg-type]
                    path_template=path,
                    parameters=_schema_for(method_upper),
                    required_permission=permission,
                    risk=_risk_for(method_upper, path),
                    required_role=_required_role_for(path),
                    permission_namespace=namespace,
                    permission_action=action,
                    resource_argument=_resource_argument_for(path),
                    requires_data_scope=_requires_data_scope(path),
                )
            )
    return tools


def _unique_tool_name(tool: AgentTool, by_name: dict[str, AgentTool]) -> str:
    """Return a deterministic unique name without dropping duplicate aliases.

    Several generic ADP routes intentionally share a friendly canonical tool
    name. The previous implementation only appended the HTTP method, so a third
    route using the same method silently replaced the second route in the dict.
    """
    if tool.name not in by_name:
        return tool.name

    method_name = f"{tool.name}:{tool.method.lower()}"
    if method_name not in by_name:
        return method_name

    path_slug = re.sub(r"[^a-z0-9]+", "_", tool.path_template.lower()).strip("_") or "route"
    candidate = f"{method_name}:{path_slug}"
    suffix = 2
    while candidate in by_name:
        candidate = f"{method_name}:{path_slug}:{suffix}"
        suffix += 1
    return candidate


def build_registry(executor_factory: Callable[[AgentTool], ToolExecutor | None] | None = None) -> AgentToolRegistry:
    """Build a closed registry from the checked-in API contract.

    Operation paths come from the generated OpenAPI document. No client input
    can add a URL, HTTP method, SQL expression, or tool at runtime. Every
    OpenAPI operation is retained exactly once, even when friendly tool names
    collide across route aliases or generic resource endpoints.
    """
    tools = _openapi_tools()
    by_name: dict[str, AgentTool] = {}
    for tool in tools:
        unique_name = _unique_tool_name(tool, by_name)
        if unique_name != tool.name:
            tool = replace(tool, name=unique_name)
        if executor_factory is not None:
            tool = replace(tool, execute=executor_factory(tool))
        by_name[tool.name] = tool
    return AgentToolRegistry(tuple(by_name.values()))


def _flask_path(rule: str) -> str:
    return re.sub(r"<(?:int|path):([^>]+)>|<([^>]+)>", lambda match: "{" + (match.group(1) or match.group(2)) + "}", rule)


def build_agent_catalog(app: Any, registry: AgentToolRegistry | None = None) -> dict[str, Any]:
    registry = registry or build_registry()
    operations: list[dict[str, str]] = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/v1") or rule.rule.startswith("/api/v1/agent/"):
            continue
        for method in sorted(rule.methods & {"GET", "POST", "PUT", "PATCH", "DELETE"}):
            operations.append({"method": method, "path": _flask_path(rule.rule)})
    registered = {(tool.method, tool.path_template) for tool in registry.tools}
    unmapped = [item for item in operations if (item["method"], item["path"]) not in registered]
    human_only = [
        {"method": tool.method, "path": tool.path_template, "tool": tool.name}
        for tool in registry.tools
        if tool.risk == "human_only"
    ]
    return {
        "operation_count": len(operations),
        "registered_count": len(operations) - len(unmapped),
        "unmapped_operations": unmapped,
        "human_only_operations": human_only,
        "tool_count": len(registry.tools),
    }
