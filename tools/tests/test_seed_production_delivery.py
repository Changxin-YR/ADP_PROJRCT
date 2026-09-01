from __future__ import annotations

from tools import seed_production_delivery as seed


def test_context_does_not_require_inventory_lot_before_purchase_receipt(monkeypatch) -> None:
    monkeypatch.setattr(seed, "base_context", lambda cursor: {"org": 1})

    requested: list[str] = []

    def lookup(cursor, sql: str, params=()):
        requested.append(sql)
        if "inventory_lots" in sql:
            raise AssertionError("inventory lot is created later by purchase_warehouse")
        return 1

    monkeypatch.setattr(seed, "one", lookup)

    assert seed.context(object())["warehouse"] == 1
    assert not any("inventory_lots" in sql for sql in requested)
