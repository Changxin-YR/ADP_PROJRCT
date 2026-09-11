"""待办队列里的措辞回归：确认卡片不能把工具名或参数 JSON 甩到用户面前。"""
from __future__ import annotations

from typing import Any

from backend.layers.features.agent.agent_confirmation_work_item import _action_text, _detail_text
from backend.layers.features.agent.agent_tool_registry import build_registry

TECHNICAL = ("api.", "adp_", "POST", "PATCH", "DELETE", "{", "}", "request_id", "tool_name", "expected_version")


def _tool(name: str) -> Any:
    return build_registry().require(name)


def test_work_item_text_is_business_chinese_for_a_create() -> None:
    tool = _tool("api.production_create_post_api_v1_production_resource")
    arguments = {
        "resource": "feed-logs",
        "payload": {"code": "FL-1", "name": "晨投", "pond_id": 2, "quantity": 20, "expected_version": 3},
    }

    assert _action_text(tool, arguments) == "新增投喂记录"
    detail = _detail_text(tool, arguments)
    assert detail.startswith("影响对象：投喂记录 ")
    assert "数量 20" in detail
    assert "expected_version" not in detail and "3" not in detail.split("数量")[-1], "乐观锁版本不该出现在业务待办里"


def test_work_item_text_never_leaks_machine_identifiers() -> None:
    for name, arguments in (
        ("api.production_create_post_api_v1_production_resource", {"resource": "medications", "payload": {"quantity": 1}}),
        ("admin.update_role_permissions", {"role_id": 1, "payload": {"permission_ids": [1, 2]}}),
        ("master_data.create_record", {"resource": "ponds", "payload": {"name": "一号塘"}}),
    ):
        tool = _tool(name)
        for text in (_action_text(tool, arguments), _detail_text(tool, arguments)):
            assert text and text.strip(), name
            assert not any(token in text for token in TECHNICAL), f"{name} 泄漏了机器标识：{text}"
