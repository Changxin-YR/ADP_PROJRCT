"""The sidecar must not accumulate harness children forever, nor reuse a broken one."""

from __future__ import annotations

import sys
import types

import pytest

from backend.config.settings import Settings
from backend.layers.features.agent.harness_cache import HarnessCache
from backend.layers.features.agent.harness_sidecar import HarnessSidecar


class HarnessTransportError(RuntimeError):
    """Name matches the DSH transport failures the sidecar classifies as protocol errors."""


class _FakeHarness:
    def __init__(self, behaviour: str = "ok") -> None:
        self.behaviour = behaviour
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.closed = True

    def run(self, prompt: str, *, session_id: str, on_notification=None):
        if self.behaviour == "protocol":
            raise HarnessTransportError("jsonrpc transport broke")
        return {"kind": "assistant", "message": prompt, "session_id": session_id}


def test_cache_keeps_a_bounded_lru_window_and_closes_evicted_runtimes() -> None:
    cache = HarnessCache(limit=2)
    created = {name: _FakeHarness() for name in ("a", "b", "c")}

    cache.put("a", created["a"])
    cache.put("b", created["b"])
    cache.get("a")           # 最近使用：a 不应被淘汰
    cache.put("c", created["c"])

    assert cache.namespaces() == ["a", "c"]
    assert created["b"].closed is True
    assert created["a"].closed is False and created["c"].closed is False

    cache.clear()
    assert cache.namespaces() == []
    assert created["a"].closed is True and created["c"].closed is True


def test_sidecar_replaces_a_runtime_that_breaks_mid_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """A child that dies (protocol/transport error) must not poison later turns."""
    created: list[_FakeHarness] = []

    def factory(**_kwargs):
        harness = _FakeHarness(behaviour="protocol" if not created else "ok")
        created.append(harness)
        return harness

    monkeypatch.setitem(sys.modules, "deepseek_harness", types.SimpleNamespace(DeepSeekHarness=factory))
    sidecar = HarnessSidecar(Settings.from_env({"APP_ENV": "test"}))
    context = {"conversation_id": "c-1", "user_namespace": "user-a"}

    with pytest.raises(Exception) as failure:
        sidecar.run("第一轮", context=context)
    assert getattr(failure.value, "code", "") == "AGENT_PROTOCOL_ERROR"

    second = sidecar.run("第二轮", context=context)
    assert len(created) == 2                       # 坏掉的子进程被丢弃并新建
    assert created[0].closed is True
    assert second["kind"] == "assistant"
    sidecar.close()
