"""工具目录必须带着业务字段清单，否则模型只能猜字段名。

线上事故（2026-09-11 21:06）：智能体建塘口时传了 ``{area: 11.2, group_id: 5}``，
被 MASTER_FIELD_INVALID 拒——塘口档案认的是 ``capacity_mu`` / ``pond_group_id``。
根因是工具说明里只有一个不透明的 payload，没有任何字段线索。
"""

from __future__ import annotations

import json

from backend.layers.features.agent.agent_field_guide import fields_by_resource, resources_for
from backend.layers.features.agent.agent_tool_registry import build_agent_tool_catalog, build_registry

# 进程环境变量有大小上限，目录是塞进 env 传给子进程的，必须留出余量。
MAX_CATALOG_BYTES = 200_000


def _catalog() -> dict[str, object]:
    return json.loads(build_agent_tool_catalog(build_registry()))


def _operation(catalog: dict[str, object], name: str) -> dict[str, object]:
    for entry in catalog["operations"]:  # type: ignore[index]
        if entry["n"] == name:
            return entry
    raise AssertionError(f"catalog 里没有 {name}")


def test_master_data_create_tells_the_model_the_real_pond_fields() -> None:
    entry = _operation(_catalog(), "master_data.create_record")

    ponds = entry["f"]["ponds"]
    assert "capacity_mu!" not in ponds, "养殖面积不是硬性必填"
    for field in ("capacity_mu", "pond_group_id", "code!", "name!"):
        assert field in ponds, f"塘口档案缺字段 {field}"
    # 这两个正是模型猜错过的名字，列表里不该出现
    assert "area" not in ponds and "group_id" not in ponds


def test_production_create_lists_every_resource_and_its_fields() -> None:
    entry = _operation(_catalog(), "api.production_create_post_api_v1_production_resource")

    assert set(entry["f"]) == set(resources_for("/api/v1/production/{resource}"))
    feed_logs = entry["f"]["feed-logs"]
    for field in ("code!", "name!", "pond_id", "batch_id", "material_id", "weight_kg"):
        assert field in feed_logs
    batches = entry["f"]["batches"]
    for field in ("pond_id!", "species!", "initial_quantity"):
        assert field in batches


def test_specialised_write_endpoints_keep_their_required_fields() -> None:
    catalog = _catalog()

    expense = _operation(catalog, "api.cost_create_expense_post_api_v1_cost_expenses")["f"]
    for field in ("category_code!", "amount!", "period_start!", "period_end!", "source_ref!"):
        assert field in expense

    order = _operation(catalog, "api.purchase_create_order_post_api_v1_purchase_orders")["f"]
    for field in ("code", "supplier_id", "material_id", "quantity", "unit_price"):
        assert field in order


def test_read_operations_stay_lean_and_catalog_stays_small_enough() -> None:
    catalog = _catalog()
    reads = [entry for entry in catalog["operations"] if entry["r"] == "read"]  # type: ignore[index]

    assert reads, "目录里应该有只读操作"
    assert all("f" not in entry for entry in reads), "只读操作不需要字段清单"

    size = len(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    assert size < MAX_CATALOG_BYTES, f"工具目录 {size} 字节，超过环境变量安全上限 {MAX_CATALOG_BYTES}"


def test_field_guide_reads_from_the_business_validation_source() -> None:
    """字段清单必须来自业务校验，不能是第二份手抄口径。"""
    from backend.layers.features.cost.cost_enterprise_validation import EXPENSE_FIELDS
    from backend.layers.features.master_data.master_data_service import MASTER_FIELDS

    tool = build_registry().require("master_data.create_record")
    assert set(fields_by_resource(tool)["ponds"]) == {
        f"{field}!" if field in {"code", "name"} else field for field in MASTER_FIELDS["ponds"]
    }
    expense_tool = build_registry().require("api.cost_create_expense_post_api_v1_cost_expenses")
    _allowed, required = __import__(
        "backend.layers.features.agent.agent_field_guide", fromlist=["field_spec"]
    ).field_spec(expense_tool)
    assert set(required) <= set(EXPENSE_FIELDS)
