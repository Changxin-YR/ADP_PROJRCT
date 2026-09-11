"""Agent 工具注册表：把签入的 OpenAPI 契约固化成模型可调用的封闭工具集。

策略细节（权限、风险、数据范围、参数 schema）在 ``agent_tool_policy`` 中，
本模块只负责解析契约、命名与注册，避免单文件继续膨胀。

安全边界：路径与 HTTP 方法全部来自生成的 OpenAPI 文档，客户端输入无法在运行时
新增 URL、SQL 表达式或工具。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from backend.layers.features.agent.agent_tool_policy import (
    Method,
    Risk,
    permission_action,
    permission_for,
    permission_namespace_for,
    permission_options,
    required_role_for,
    requires_data_scope,
    resource_argument_for,
    risk_for,
    schema_for,
)

# 以下名字通过本模块对外暴露（其他模块与测试直接从本模块导入），
# 因此这里显式再导出，保持既有导入路径不变。
__all__ = [
    "AgentTool",
    "AgentToolRegistry",
    "Method",
    "Risk",
    "ToolExecutor",
    "build_agent_catalog",
    "build_agent_tool_catalog",
    "build_registry",
    "permission_options",
]

ToolExecutor = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]

# Generated summaries are generic counts ("查询列表"); the model needs the real
# intent for the operations users ask about by name.
_DESCRIPTION_OVERRIDES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/auth/me"): "查询当前登录用户的资料、角色、数据范围与权限码（回答“我有哪些权限/我是谁”必须用它）",
    ("GET", "/api/v1/auth/workbench"): "查询当前登录用户的工作台入口信息",
    ("GET", "/api/v1/workbench/summary"): "查询工作台摘要：待办事项、通知与风险提醒",
    ("GET", "/api/v1/admin/roles"): "查询角色清单及其权限配置（需要 auth.role.manage）",
    ("GET", "/api/v1/health"): "查询系统健康状态（无需业务权限）",
}


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
            namespace = permission_namespace_for(path)
            tools.append(
                AgentTool(
                    name=name,
                    description=_DESCRIPTION_OVERRIDES.get((method_upper, path)) or str(operation.get("summary") or "ADP 业务操作"),
                    method=method_upper,  # type: ignore[arg-type]
                    path_template=path,
                    parameters=schema_for(method_upper, path),
                    required_permission=permission_for(path, method_upper),
                    risk=risk_for(method_upper, path),
                    required_role=required_role_for(path),
                    permission_namespace=namespace,
                    permission_action=permission_action(path, method_upper) if namespace else None,
                    resource_argument=resource_argument_for(path),
                    requires_data_scope=requires_data_scope(path),
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


def build_agent_tool_catalog(registry: AgentToolRegistry | None = None) -> str:
    """Serialize the fixed operation contract for the model tool description.

    Compact keys keep the environment value below Windows' process
    environment limit while retaining the fields needed for tool selection.
    A trailing ``!`` marks a required parameter.

    ``f`` carries the business payload fields the endpoint accepts (and which of them
    are required) so the model stops guessing names like ``group_id`` when the archive
    actually expects ``pond_group_id``. ``rs`` lists the legal values for ``resource``.
    """
    from backend.layers.features.agent.agent_field_guide import field_spec, fields_by_resource, resources_for

    registry = registry or build_registry()
    operations = []
    for tool in sorted(registry.tools, key=lambda item: item.name):
        entry: dict[str, Any] = {
            "n": tool.name,
            "d": tool.description,
            "m": tool.method,
            "p": tool.path_template,
            "r": tool.risk,
            "q": tool.required_permission or "",
            "a": [
                f"{name}!" if isinstance(schema, dict) and schema.get("required") else name
                for name, schema in tool.parameters.items()
            ],
        }
        resources = resources_for(tool.path_template)
        if resources:
            # 通用 {resource} 接口：先告诉模型 resource 能填什么（读操作同样需要）
            entry["rs"] = resources
            if tool.risk != "read":
                # 写操作再按资源给出各自的字段清单，模型照抄字段名而不是猜
                entry["f"] = fields_by_resource(tool)
        elif tool.risk != "read":
            spec = field_spec(tool)
            if spec is not None:
                allowed, required = spec
                entry["f"] = [f"{name}!" if name in required else name for name in allowed]
        operations.append(entry)

    return json.dumps(
        {
            "legend": "n=name; d=description; m=HTTP method; p=path; r=risk; q=required permission; a=parameters; f=payload 可用字段(!=必填); rs=resource 可选值; ! means required",
            "operations": operations,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


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
