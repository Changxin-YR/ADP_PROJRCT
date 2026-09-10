"""Streaming adapter for the ADP agent turn.

The DSH runtime already emits incremental events over JSON-RPC; the SDK just collects
them until the turn ends. Here we translate those notifications into small NDJSON
chunks so the panel can render progress and tokens while the turn is still running:

* ``{"type": "status", "text": "正在查询生产记录…"}``   — a tool call started
* ``{"type": "delta", "text": "…"}``                    — assistant text delta
* ``{"type": "result", "data": {...}}``                 — the same payload ``/turn`` returns
* ``{"type": "error", "code": ..., "message": ...}``    — turn-level failure

The turn itself still runs through :meth:`HarnessSidecar.run`, which keeps permission
enforcement, audit and confirmation semantics identical to the non-streaming endpoint.
"""

from __future__ import annotations

import json
import queue
import threading
from typing import Any, Callable, Iterator

# Tool display names keep the panel readable while a turn is in flight.
TOOL_LABELS = {
    "adp_query": "正在查询业务数据…",
    "adp_mutation": "正在准备写入操作…",
    "adp_ask_user": "正在向你确认信息…",
}
_IDLE_GRACE_SECONDS = 20.0


def translate(notification: Any) -> list[dict[str, Any]]:
    """Map one DSH notification to zero or more UI chunks."""
    payload = getattr(notification, "payload", None)
    if not isinstance(payload, dict):
        return []
    event = payload.get("event")
    if not isinstance(event, dict):
        return []
    kind = str(event.get("type") or "")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    if kind == "assistant/chunk":
        chunk = data.get("chunk") if isinstance(data.get("chunk"), dict) else {}
        if chunk.get("type") == "text-delta" and str(chunk.get("text") or ""):
            return [{"type": "delta", "text": str(chunk["text"])}]
        return []
    if kind == "tool/call":
        name = str(data.get("name") or data.get("tool") or "").strip()
        return [{"type": "status", "tool": name, "text": TOOL_LABELS.get(name, "正在执行操作…")}]
    return []


def _ndjson(chunk: dict[str, Any]) -> str:
    return json.dumps(chunk, ensure_ascii=False, separators=(",", ":")) + "\n"


def stream_turn(
    runner: Callable[..., dict[str, Any]],
    prompt: str,
    *,
    context: dict[str, str],
    timeout_seconds: float,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> Iterator[str]:
    """Run one turn in a helper thread and yield NDJSON chunks as they happen.

    ``runner`` is ``HarnessSidecar.run`` (already bound); it is blocking, hence the
    background thread. The generator stops streaming after ``timeout_seconds`` plus a
    short grace window so a hung child cannot hold the HTTP response forever.
    """
    chunks: "queue.Queue[tuple[str, Any]]" = queue.Queue()

    def sink(notification: Any) -> None:
        for chunk in translate(notification):
            chunks.put(("chunk", chunk))

    def work() -> None:
        try:
            chunks.put(("result", runner(prompt, context=context, on_notification=sink)))
        except Exception as exc:  # noqa: BLE001 - surfaced to the client as an error chunk
            chunks.put(("error", exc))

    thread = threading.Thread(target=work, name="adp-agent-stream", daemon=True)
    thread.start()
    deadline = timeout_seconds + _IDLE_GRACE_SECONDS
    while True:
        try:
            kind, value = chunks.get(timeout=deadline)
        except queue.Empty:
            yield _ndjson({"type": "error", "code": "AGENT_TIMEOUT", "message": "智能助手响应超时，请稍后重试"})
            return
        if kind == "chunk":
            if on_event is not None:
                on_event(value)
            yield _ndjson(value)
            continue
        if kind == "result":
            payload = {"type": "result", "data": value}
        else:
            payload = {
                "type": "error",
                "code": str(getattr(value, "code", "AGENT_REQUEST_FAILED")),
                "message": str(getattr(value, "message", value)),
                "status": int(getattr(value, "status", 400)),
            }
        if on_event is not None:
            on_event(payload)
        yield _ndjson(payload)
        return
