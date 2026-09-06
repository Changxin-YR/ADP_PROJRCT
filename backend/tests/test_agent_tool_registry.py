from __future__ import annotations

from backend.layers.features.agent.agent_tool_registry import build_registry


def test_registry_marks_read_write_and_human_only_operations() -> None:
    registry = build_registry()
    assert registry.get("master_data.list_records").risk == "read"
    assert registry.get("master_data.create_record").risk == "write"
    assert registry.get("admin.update_role_permissions").risk == "human_only"
    assert registry.get("admin.create_user").risk == "human_only"


def test_registry_exposes_fixed_paths_and_no_arbitrary_http() -> None:
    registry = build_registry()
    for tool in registry.tools:
        assert tool.method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
        assert tool.path_template.startswith("/api/v1/")
        assert "url" not in tool.parameters
        assert "sql" not in tool.parameters


def test_registry_contains_all_business_domains() -> None:
    names = {tool.name for tool in build_registry().tools}
    for prefix in {"master_data", "production", "warehouse", "purchase", "sales", "cost", "data_exchange", "workbench"}:
        assert any(name.startswith(prefix + ".") for name in names)
