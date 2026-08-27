from __future__ import annotations

import pytest

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.data_exchange.import_validation import validate_rows
from backend.layers.features.master_data.master_data_store import MySqlMasterDataStore
from backend.layers.features.production.production_store import MySqlProductionStore


class Cursor:
    def __init__(self, rows: list[dict[str, object] | None]) -> None:
        self.rows = list(rows)
        self.sql: list[str] = []

    def execute(self, statement: str, _params: tuple[object, ...] = ()) -> None:
        self.sql.append(statement)

    def fetchone(self) -> dict[str, object] | None:
        return self.rows.pop(0) if self.rows else None


def test_feed_plan_final_validation_rejects_invalid_material_relation() -> None:
    cursor = Cursor([None])
    with pytest.raises(DomainError, match="FEED_PLAN_RELATION_INVALID"):
        MySqlProductionStore._validate_relations(
            cursor,
            "feed-plans",
            {"organization_id": 1, "pond_id": 10, "batch_id": 20, "material_id": 30},
        )


def test_archive_blocks_material_with_pending_purchase_reference() -> None:
    cursor = Cursor([None, {"id": 1}])
    with pytest.raises(DomainError, match="MASTER_ARCHIVE_BLOCKED"):
        MySqlMasterDataStore._archive_references(cursor, "materials", {"id": 7})


def test_archive_blocks_pond_with_positive_stock() -> None:
    cursor = Cursor([None, None, None, {"id": 1}])
    with pytest.raises(DomainError, match="MASTER_ARCHIVE_BLOCKED"):
        MySqlMasterDataStore._archive_references(cursor, "ponds", {"id": 10})


def test_feed_plan_import_preview_rejects_wrong_batch_pond_relation() -> None:
    class PreviewCursor:
        def __init__(self) -> None:
            self.result: list[dict[str, object]] = []

        def execute(self, statement: str, _params: tuple[object, ...] = ()) -> None:
            self.last_statement = statement
            if "FROM production_documents" in statement:
                self.result = []
            elif "FROM ponds" in statement:
                self.result = [{"id": 10}]
            elif "FROM production_batches" in statement:
                self.result = [{"id": 20}]
            elif "FROM materials" in statement:
                self.result = [{"id": 30}]
            else:
                self.result = []

        def fetchall(self) -> list[dict[str, object]]:
            return self.result

        def fetchone(self) -> dict[str, object] | None:
            return None if "JOIN production_batches" in getattr(self, "last_statement", "") else (self.result[0] if self.result else None)

    cursor = PreviewCursor()
    errors = validate_rows(
        cursor,
        1,
        "feed-plans",
        [{"code": "FP-1", "pond_id": 10, "batch_id": 20, "material_id": 30}],
        [2],
    )
    assert any(error["column"] == "batch_id" and "同企业、同塘口" in error["message"] for error in errors)
