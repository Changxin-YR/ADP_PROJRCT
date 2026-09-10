from __future__ import annotations

import json
from typing import Any

from backend.layers.features.agent.agent_prompt import (
    AGENT_INSTRUCTIONS,
    build_user_brief,
    ensure_instructions,
    render_prompt,
)
from backend.layers.features.agent.harness_sidecar import _clarification_from_result, _confirmation_from_result

USER = {
    "id": 21,
    "name": "验收_核验员",
    "status": "active",
    "roles": [{"id": 40, "code": "breed_manager", "name": "养殖管理员"}],
    "data_scopes": [{"id": 3, "scope_type": "farm", "name": "一号基地"}],
    "permissions": ["master_data.view", "production.view", "workbench.enter"],
}


class _Result:
    def __init__(self, events: list[dict[str, Any]], final_response: str = "", session_id: str = "s-1") -> None:
        self.events = events
        self.final_response = final_response
        self.session_id = session_id


def _tool_event(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "tool/result",
        "data": {"message": {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}},
    }


def test_user_brief_keeps_the_agent_inside_the_logged_in_permissions() -> None:
    brief = build_user_brief(USER)

    assert "验收_核验员" in brief
    assert "breed_manager" in brief
    assert "farm" in brief
    assert "master_data.view" in brief
    assert "production.view" in brief
    assert build_user_brief({}) == ""


def test_render_prompt_puts_identity_and_contract_before_the_request() -> None:
    rendered = render_prompt("查询我的权限", build_user_brief(USER))

    assert rendered.startswith("【当前登录用户】")
    assert "【行为约定】" in rendered
    assert rendered.endswith("【用户请求】\n查询我的权限")
    assert "adp_ask_user" in rendered
    assert render_prompt("查询", "") == "查询"


def test_ensure_instructions_installs_the_contract_into_the_harness_home(tmp_path: Any) -> None:
    assert ensure_instructions(tmp_path) is True
    installed = tmp_path / "AGENTS.md"
    assert installed.read_text(encoding="utf-8") == AGENT_INSTRUCTIONS
    # Idempotent: a second call must not rewrite or fail.
    assert ensure_instructions(tmp_path) is True


def test_clarification_result_is_exposed_to_the_panel() -> None:
    result = _Result(
        [
            _tool_event(
                {
                    "kind": "clarification",
                    "question": "要查询哪个塘口？",
                    "options": ["1 号塘", "2 号塘", "", "3 号塘", "4 号塘", "5 号塘", "6 号塘"],
                    "allow_free_text": True,
                }
            )
        ],
        final_response="需要先确认塘口。",
    )

    clarification = _clarification_from_result(result)

    assert clarification == {
        "question": "要查询哪个塘口？",
        "options": ["1 号塘", "2 号塘", "3 号塘", "4 号塘", "5 号塘"],
        "allow_free_text": True,
    }
    assert _clarification_from_result(_Result([])) is None
    assert _clarification_from_result(_Result([_tool_event({"kind": "clarification", "question": "   "})])) is None


def test_confirmation_and_clarification_payloads_stay_distinguishable() -> None:
    result = _Result(
        [
            _tool_event({"kind": "clarification", "question": "确认投放数量？"}),
            _tool_event(
                {
                    "kind": "confirmation_required",
                    "confirmation": {"token": "once", "id": 7, "summary": "投喂 20kg"},
                }
            ),
        ]
    )

    assert _confirmation_from_result(result) == {"token": "once", "id": 7, "summary": "投喂 20kg"}
    assert _clarification_from_result(result) == {"question": "确认投放数量？", "options": [], "allow_free_text": True}
