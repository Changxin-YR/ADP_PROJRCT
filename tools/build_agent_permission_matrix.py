from __future__ import annotations

import ast
import dis
import inspect
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.features.agent.agent_tool_registry import (
    _flask_path,
    build_registry,
)


_PERMISSION = re.compile(r"^[a-z_]+(?:\.[a-z_]+)+$")
_ACTIONS = {"view", "manage", "verify", "confirm", "reverse"}
_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _code_objects(code: Any):
    yield code
    for child in code.co_consts:
        if isinstance(child, type(code)):
            yield from _code_objects(child)


def _called_methods(function: Any) -> set[tuple[str, str]]:
    calls: set[tuple[str, str]] = set()
    for code in _code_objects(function.__code__):
        instructions = list(dis.get_instructions(code))
        for left, right in zip(instructions, instructions[1:]):
            if left.opname in {"LOAD_DEREF", "LOAD_FAST", "LOAD_GLOBAL"} and right.opname in {"LOAD_ATTR", "LOAD_METHOD"}:
                calls.add((str(left.argval), str(right.argval)))
    return calls


def _services(function: Any) -> dict[str, Any]:
    cells = dict(zip(function.__code__.co_freevars, (cell.cell_contents for cell in function.__closure__ or ())))
    return {
        name: value
        for name, value in cells.items()
        if getattr(value.__class__, "__module__", "").startswith("backend.layers.features")
    }


def _permission_literals(service: Any, methods: set[str]) -> set[str]:
    permissions: set[str] = set()
    for name in methods:
        method = getattr(service, name, None)
        if not callable(method):
            continue
        try:
            tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
        except (OSError, TypeError, IndentationError):
            continue
        parents: dict[ast.AST, ast.AST] = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                if isinstance(node, ast.Set) and isinstance(parents.get(node), ast.BinOp) and isinstance(parents[node].op, ast.BitAnd):
                    permissions.update(
                        item.value for item in node.elts
                        if isinstance(item, ast.Constant) and isinstance(item.value, str) and _PERMISSION.fullmatch(item.value)
                    )
                if isinstance(node, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
                    if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str) and _PERMISSION.fullmatch(node.left.value):
                        permissions.add(node.left.value)
                continue
            if node.func.attr in {"require", "require_permission"}:
                constants = [arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
                has_resource = any(isinstance(arg, ast.Name) and arg.id == "resource" for arg in node.args)
                for value in constants:
                    if value in _ACTIONS and has_resource:
                        permissions.add("<resource>." + value)
            for keyword in node.keywords:
                if keyword.arg == "permission" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    permissions.add(keyword.value.value)
    return permissions


def _domain(path: str) -> str:
    parts = path.strip("/").split("/")
    return parts[2] if len(parts) > 2 else ""


def _backend_permissions(path: str, tool: Any, function: Any) -> tuple[str, bool]:
    services = _services(function)
    calls = _called_methods(function)
    discovered: set[str] = set()
    for variable, service in services.items():
        discovered.update(_permission_literals(service, {method for name, method in calls if name == variable}))

    if discovered:
        normalized = set()
        for permission in discovered:
            if permission.startswith("<resource>."):
                normalized.add(f"{tool.required_permission.rsplit('.', 1)[0]}.{permission.split('.', 1)[1]} (resource-specific)")
            else:
                normalized.add(permission)
        return " / ".join(sorted(normalized)), tool.required_permission in discovered or any(
            permission.endswith("(resource-specific)") for permission in normalized
        )

    if _domain(path) == "admin":
        return f"{tool.required_permission} (route guard + super_admin)", True
    if _domain(path) == "auth":
        return "session guard", True
    if _domain(path) == "health":
        return "none", True
    return f"{tool.required_permission} (service guard not statically exposed)", bool(tool.required_permission)


def build_matrix(app: Any | None = None) -> list[dict[str, str]]:
    app = app or create_app(Settings.from_env({"APP_ENV": "test"}))
    registry = build_registry()
    rows: list[dict[str, str]] = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda item: (item.rule, item.endpoint)):
        path = _flask_path(rule.rule)
        if not path.startswith("/api/v1") or path.startswith("/api/v1/agent/"):
            continue
        function = app.view_functions[rule.endpoint]
        for method in sorted(rule.methods & _METHODS):
            tool = registry.find_operation(method, path)
            if tool is None:
                rows.append({"method": method, "route": path, "agent_permission": "", "backend_permission": "", "tool": "", "status": "FAIL"})
                continue
            backend, guard_match = _backend_permissions(path, tool, function)
            rows.append({
                "method": method,
                "route": path,
                "agent_permission": tool.required_permission or "none",
                "backend_permission": backend,
                "tool": tool.name,
                "status": "PASS" if guard_match else "FAIL",
            })
    return rows


def render_markdown(rows: list[dict[str, str]]) -> str:
    lines = [
        "# Agent Permission Matrix",
        "",
        f"> Generated from `app.url_map` and `build_registry()`; {len(rows)} business operations.",
        "",
        "| Method | Route | Agent Permission | Backend Permission | Agent Tool | Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {row['method']} | `{row['route']}` | `{row['agent_permission']}` | `{row['backend_permission']}` | `{row['tool']}` | {row['status']} |"
        for row in rows
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "docs/testing/AGENT_PERMISSION_MATRIX.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = build_matrix()
    output.write_text(render_markdown(rows), encoding="utf-8")
    print(f"wrote {output} ({len(rows)} operations)")
