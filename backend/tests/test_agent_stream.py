"""Streaming adapter tests: notification translation and NDJSON chunking."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from backend.layers.features.agent.agent_stream import stream_turn, translate


def _notification(event_type: str, data: dict[str, Any]) -> Any:
    return SimpleNamespace(payload={"event": {"type": event_type, "data": data}})


def _lines(raw: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def test_translate_maps_text_deltas_and_tool_calls() -> None:
    delta = translate(_notification("assistant/chunk", {"chunk": {"type": "text-delta", "index": 0, "text": "你好"}}))
    assert delta == [{"type": "delta", "text": "你好"}]

    status = translate(_notification("tool/call", {"name": "adp_query"}))
    assert status == [{"type": "status", "tool": "adp_query", "text": "正在查询业务数据…"}]

    assert translate(_notification("assistant/chunk", {"chunk": {"type": "usage"}})) == []
    assert translate(_notification("turn/start", {})) == []
    assert translate(SimpleNamespace(payload=None)) == []


def test_stream_turn_emits_chunks_then_final_result() -> None:
    def runner(prompt: str, *, context: dict[str, str], on_notification: Any) -> dict[str, Any]:
        assert prompt == "查塘口"
        assert context["conversation_id"] == "c-1"
        on_notification(_notification("tool/call", {"name": "adp_query"}))
        on_notification(_notification("assistant/chunk", {"chunk": {"type": "text-delta", "text": "共4个"}}))
        return {"kind": "assistant", "message": "共4个塘口", "session_id": "ns:c-1:1"}

    chunks = _lines("".join(stream_turn(runner, "查塘口", context={"conversation_id": "c-1"}, timeout_seconds=5)))

    assert chunks[0]["type"] == "status"
    assert chunks[1] == {"type": "delta", "text": "共4个"}
    assert chunks[2]["type"] == "result"
    assert chunks[2]["data"]["message"] == "共4个塘口"


def test_stream_turn_reports_turn_failures_as_error_chunks() -> None:
    class AgentGatewayError(ValueError):
        def __init__(self) -> None:
            super().__init__("超时")
            self.code = "AGENT_TIMEOUT"
            self.message = "智能助手响应超时，请稍后重试"
            self.status = 504

    def runner(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AgentGatewayError()

    chunks = _lines("".join(stream_turn(runner, "查", context={}, timeout_seconds=5)))

    assert chunks == [
        {"type": "error", "code": "AGENT_TIMEOUT", "message": "智能助手响应超时，请稍后重试", "status": 504}
    ]
