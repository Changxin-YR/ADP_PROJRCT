from __future__ import annotations

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.features.agent.agent_tool_registry import build_agent_catalog


def test_agent_catalog_covers_every_live_business_route() -> None:
    """Fail CI when Flask gains an API route that the Agent contract cannot reach."""
    dependency = object()
    app = create_app(
        Settings.from_env({"APP_ENV": "test"}),
        store=dependency,
        cost_store=dependency,
        master_store=dependency,
        production_store=dependency,
        warehouse_store=dependency,
        purchase_store=dependency,
        sales_store=dependency,
        data_exchange_store=dependency,
        agent_gateway=dependency,
        agent_sidecar=dependency,
    )
    catalog = build_agent_catalog(app)
    assert catalog["unmapped_operations"] == [], catalog["unmapped_operations"]
    assert catalog["registered_count"] == catalog["operation_count"]


def test_only_identity_session_lifecycle_remains_human_only() -> None:
    dependency = object()
    app = create_app(
        Settings.from_env({"APP_ENV": "test"}),
        store=dependency,
        cost_store=dependency,
        master_store=dependency,
        production_store=dependency,
        warehouse_store=dependency,
        purchase_store=dependency,
        sales_store=dependency,
        data_exchange_store=dependency,
        agent_gateway=dependency,
        agent_sidecar=dependency,
    )
    human_only = build_agent_catalog(app)["human_only_operations"]
    assert human_only
    assert all(item["path"].startswith("/api/v1/auth") for item in human_only)
