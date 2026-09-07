from __future__ import annotations

from backend.layers.features.agent.agent_tool_registry import _openapi_tools, build_registry, permission_options


def test_registry_marks_read_write_and_identity_only_operations() -> None:
    registry = build_registry()
    assert registry.get("master_data.list_records").risk == "read"
    assert registry.get("master_data.create_record").risk == "write"
    assert registry.get("admin.update_role_permissions").risk == "write"
    assert registry.get("admin.create_user").risk == "write"

    # Authentication/session lifecycle stays human-only; business/admin actions
    # are delegable when the logged-in user has the same authorization.
    auth_writes = [
        tool for tool in registry.tools
        if tool.path_template.startswith("/api/v1/auth") and tool.method != "GET"
    ]
    assert auth_writes
    assert all(tool.risk == "human_only" for tool in auth_writes)


def test_admin_tools_keep_super_admin_role_constraint_and_skip_business_scope() -> None:
    registry = build_registry()
    tool = registry.get("admin.update_role_permissions")
    assert tool.required_permission == "auth.role.manage"
    assert tool.required_role == "super_admin"
    assert tool.requires_data_scope is False


def test_resource_permissions_match_business_service_alternatives() -> None:
    registry = build_registry()

    master = registry.get("master_data.list_records")
    assert set(permission_options(master, {"resource": "pond-groups"})) == {
        "master_data.view",
        "master_data.pond_groups.view",
    }

    production = registry.get("production.list_records")
    assert set(permission_options(production, {"resource": "feed-logs"})) == {
        "production.view",
        "production.feed_logs.view",
    }

    warehouse = registry.get("warehouse.list_records")
    assert set(permission_options(warehouse, {"resource": "issue-requests"})) == {
        "warehouse.view",
        "production.view",
    }


def test_registry_exposes_fixed_paths_and_no_arbitrary_http() -> None:
    registry = build_registry()
    for tool in registry.tools:
        assert tool.method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
        assert tool.path_template.startswith("/api/v1/")
        assert "url" not in tool.parameters
        assert "sql" not in tool.parameters


def test_registry_never_drops_operations_when_friendly_names_collide() -> None:
    registry = build_registry()
    raw_tools = _openapi_tools()
    names = [tool.name for tool in registry.tools]
    operations = [(tool.method, tool.path_template) for tool in registry.tools]
    assert len(registry.tools) == len(raw_tools)
    assert len(names) == len(set(names))
    assert len(operations) == len(set(operations))


def test_registry_contains_all_business_domains() -> None:
    names = {tool.name for tool in build_registry().tools}
    for prefix in {"master_data", "production", "warehouse", "purchase", "sales", "cost", "data_exchange", "workbench"}:
        assert any(name.startswith(prefix + ".") for name in names)


def test_specialized_tools_use_the_same_permissions_as_their_services() -> None:
    registry = build_registry()
    expected = {
        ("PUT", "/api/v1/cost/allocation-rules"): "cost.allocation.manage",
        ("POST", "/api/v1/cost/entries/{entry_id}/confirm"): "cost.entry.confirm",
        ("POST", "/api/v1/cost/entries/{entry_id}/reverse"): "cost.entry.reverse",
        ("POST", "/api/v1/cost/assets/{record_id}/verify"): "cost.asset.verify",
        ("POST", "/api/v1/cost/settlements/{record_id}/confirm"): "cost.settlement.confirm",
        ("POST", "/api/v1/data-exchange/exports"): "data_exchange.export",
        ("POST", "/api/v1/data-exchange/attachments"): "attachment.manage",
        ("GET", "/api/v1/data-exchange/attachments"): "attachment.manage",
        ("GET", "/api/v1/data-exchange/attachments/{attachment_id}/download"): "attachment.manage",
        ("POST", "/api/v1/purchase/payments"): "finance.payment.manage",
        ("POST", "/api/v1/purchase/payments/{record_id}/reverse"): "finance.payment.verify",
        ("POST", "/api/v1/sales/receipts"): "finance.receipt.manage",
        ("POST", "/api/v1/sales/receipts/{record_id}/reverse"): "finance.receipt.verify",
        ("POST", "/api/v1/purchase/returns"): "purchase.return.manage",
        ("POST", "/api/v1/purchase/returns/{record_id}/verify"): "purchase.return.verify",
        ("POST", "/api/v1/sales/returns"): "sales.return.manage",
        ("POST", "/api/v1/sales/returns/{record_id}/verify"): "sales.return.verify",
    }
    for operation, permission in expected.items():
        tool = registry.find_operation(*operation)
        assert tool is not None, operation
        assert tool.required_permission == permission, operation
