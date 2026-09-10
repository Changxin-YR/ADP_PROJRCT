"""Bounded child-process cache for the ADP agent sidecar.

One gunicorn worker serves many user sessions; each session namespace maps to a live
Node harness child (~70 MB). Without a bound a busy day accumulates children until the
box swaps, and a child that broke mid-turn would be reused forever. This cache keeps a
small LRU window and lets callers drop a misbehaving runtime so the next turn starts
from a fresh child.
"""

from __future__ import annotations

from typing import Any

DEFAULT_LIMIT = 6


def close_harness(harness: Any) -> None:
    """Best-effort shutdown of one harness (never raises)."""
    exit_hook = getattr(harness, "__exit__", None)
    try:
        if callable(exit_hook):
            exit_hook(None, None, None)
            return
        close = getattr(harness, "close", None)
        if callable(close):
            close()
    except Exception:
        pass


class HarnessCache:
    """LRU cache of live harness children, keyed by session namespace."""

    def __init__(self, limit: int = DEFAULT_LIMIT) -> None:
        self.limit = max(1, int(limit))
        self._items: dict[str, Any] = {}
        self._order: list[str] = []
        self._active = ""

    def get(self, namespace: str) -> Any | None:
        """Return the cached runtime, marking it (and protecting it) as most recent."""
        self.touch(namespace)
        return self._items.get(namespace)

    def put(self, namespace: str, harness: Any) -> None:
        """Store a freshly created runtime and evict the oldest idle ones."""
        self._active = namespace
        self._items[namespace] = harness
        if namespace in self._order:
            self._order.remove(namespace)
        self._order.append(namespace)
        while len(self._order) > self.limit:
            stale = next((name for name in self._order if name != self._active), None)
            if stale is None:
                return
            self.drop(stale)

    def touch(self, namespace: str) -> None:
        self._active = namespace
        if namespace in self._order:
            self._order.remove(namespace)
            self._order.append(namespace)

    def drop(self, namespace: str) -> None:
        """Forget one runtime (used when it misbehaves) and close it."""
        if namespace in self._order:
            self._order.remove(namespace)
        close_harness(self._items.pop(namespace, None))

    def clear(self) -> None:
        """Close every cached runtime (orderly shutdown)."""
        items, self._items, self._order = list(self._items.values()), {}, []
        for harness in items:
            close_harness(harness)

    def namespaces(self) -> list[str]:
        return list(self._order)
