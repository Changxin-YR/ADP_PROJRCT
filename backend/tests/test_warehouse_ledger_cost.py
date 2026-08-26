from decimal import Decimal

from backend.layers.features.warehouse.warehouse_ledger_store import WarehouseLedgerPoster


def test_ledger_posting_uses_inventory_lot_cost_when_issue_form_has_no_price() -> None:
    class Cursor:
        inserted: list[tuple[object, ...]] = []

        def execute(self, _sql: str, _params: tuple[object, ...]) -> None:
            pass

        @staticmethod
        def fetchall() -> list[dict[str, object]]:
            return [{"id": 8, "unit_cost": Decimal("5.0000")}]

        def executemany(self, _sql: str, values: list[tuple[object, ...]]) -> None:
            self.inserted = values

    cursor = Cursor()
    WarehouseLedgerPoster._insert(
        cursor,
        "issues",
        {"id": 9, "organization_id": 1, "material_id": 7, "pond_id": 3, "batch_id": 4},
        [{"warehouse_id": 2, "inventory_lot_id": 8, "quantity_delta": Decimal("-4")}],
        11,
    )

    assert cursor.inserted[0][8] == Decimal("5.0000")
