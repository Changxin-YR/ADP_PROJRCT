from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

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


class AgentToolRegistry:
    def __init__(self, tools: tuple[AgentTool, ...]) -> None:
        self.tools = tools
        self._by_name = {tool.name: tool for tool in tools}
        self._by_operation = {(tool.method, tool.path_template): tool for tool in tools}

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
    "admin": "auth.user.manage",
    "auth": None,
    "cost": "cost.view",
    "data-exchange": "data_exchange.view",
    "master-data": "master_data.view",
    "production": "production.view",
    "purchase": "purchase.view",
    "sales": "sales.view",
    "warehouse": "warehouse.view",
    "workbench": "work_item.view",
}

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


def _permission_for(path: str, method: str) -> str | None:
    segments = path.split("/")
    domain = segments[3] if len(segments) > 3 else ""
    if domain in {"work-items", "notifications"}:
        return "work_item.view"
    if domain == "admin":
        if "/roles" in path:
            return "auth.role.manage"
        if "/applications" in path:
            return "auth.review"
        if "/audit-logs" in path:
            return "audit.view"
        return "auth.user.manage"
    permission = _DOMAIN_PERMISSIONS.get(domain)
    if method != "GET" and permission and permission.endswith(".view"):
        return permission[:-5] + ".manage"
    if method != "GET" and permission == "work_item.view":
        return "work_item.manage"
    return permission


def _risk_for(method: str, path: str) -> Risk:
    if path.startswith("/api/v1/admin") and method != "GET":
        return "human_only"
    if path.startswith("/api/v1/auth") and method != "GET":
        return "human_only"
    if method == "GET":
        return "read"
    return "write"


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
        for method, operation in operations.items():
            method_upper = method.upper()
            if method_upper not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            operation_id = str(operation.get("operationId") or "")
            name = _tool_name(operation_id, method_upper, path)
            tools.append(
                AgentTool(
                    name=name,
                    description=str(operation.get("summary") or "ADP 业务操作"),
                    method=method_upper,  # type: ignore[arg-type]
                    path_template=path,
                    parameters=_schema_for(method_upper),
                    required_permission=_permission_for(path, method_upper),
                    risk=_risk_for(method_upper, path),
                )
            )
    return tools


def build_registry(executor_factory: Callable[[AgentTool], ToolExecutor | None] | None = None) -> AgentToolRegistry:
    """Build a closed registry from the checked-in API contract.

    Operation paths come from the generated OpenAPI document. No client input
    can add a URL, HTTP method, SQL expression, or tool at runtime.
    """
    tools = _openapi_tools()
    by_name: dict[str, AgentTool] = {}
    for tool in tools:
        # Canonical names are useful to the Harness plugin; duplicate route
        # variants retain their operation id so every route remains auditable.
        if tool.name in by_name:
            tool = AgentTool(
                name=f"{tool.name}:{tool.method.lower()}",
                description=tool.description,
                method=tool.method,
                path_template=tool.path_template,
                parameters=tool.parameters,
                required_permission=tool.required_permission,
                risk=tool.risk,
            )
        if executor_factory is not None:
            tool = AgentTool(
                name=tool.name,
                description=tool.description,
                method=tool.method,
                path_template=tool.path_template,
                parameters=tool.parameters,
                required_permission=tool.required_permission,
                risk=tool.risk,
                execute=executor_factory(tool),
            )
        by_name[tool.name] = tool
    return AgentToolRegistry(tuple(by_name.values()))


def _flask_path(rule: str) -> str:
    import re

    return re.sub(r"<(?:int|path):([^>]+)>|<([^>]+)>", lambda match: "{" + (match.group(1) or match.group(2)) + "}", rule)


def build_agent_catalog(app: Any, registry: AgentToolRegistry | None = None) -> dict[str, Any]:
    registry = registry or build_registry()
    operations: list[dict[str, str]] = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/v1"):
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
