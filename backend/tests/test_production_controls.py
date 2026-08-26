from pathlib import Path

import pytest

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.production.production_service import ProductionService
from backend.layers.features.production.production_store import MySqlProductionStore


def test_write_scope_rejects_a_pond_outside_authorized_area() -> None:
    user = {
        "id": 7,
        "data_scopes": [{"scope_type": "area", "area_id": 11}],
    }

    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        MySqlProductionStore.require_write_scope(
            user,
            {"area_id": 12, "_target_area_id": 11},
        )


def test_write_scope_rejects_a_transfer_target_outside_authorized_area() -> None:
    user = {
        "id": 7,
        "data_scopes": [{"scope_type": "area", "area_id": 11}],
    }

    with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
        MySqlProductionStore.require_write_scope(
            user,
            {"area_id": 11, "_target_area_id": 12},
        )


def test_migration_prevents_parallel_corrections_for_one_record() -> None:
    sql = (Path(__file__).parents[2] / "database/migrations/009_production.sql").read_text(encoding="utf-8")

    assert "uq_production_batches_correction" in sql
    assert "uq_production_documents_correction" in sql


def test_correction_requires_an_explicit_reason() -> None:
    class Store:
        @staticmethod
        def get_record(_resource: str, _record_id: int) -> dict[str, object]:
            return {"id": 1, "status": "verified", "row_version": 2, "created_by": 3}

        @staticmethod
        def create_correction(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {"id": 2, "status": "draft", "row_version": 1}

    service = ProductionService(Store())
    actor = {"id": 7, "permissions": ["production.manage"], "data_scopes": []}

    with pytest.raises(DomainError, match="CORRECTION_REASON_REQUIRED"):
        service.correct(actor, "samplings", 1, {
            "expected_version": 2,
            "code": "SP-1-C1",
            "name": "抽样更正",
        })


def test_feed_log_requires_a_verified_request_and_actual_issue() -> None:
    class Cursor:
        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            self.sql = sql
            self.params = params

        @staticmethod
        def fetchone() -> None:
            return None

    row = {"material_issue_request_id": 5, "material_id": 7, "pond_id": 3, "quantity": 20}
    with pytest.raises(DomainError, match="FEED_MATERIAL_ISSUE_REQUIRED"):
        MySqlProductionStore.require_material_issue(Cursor(), row)


def test_feed_log_accepts_a_verified_request_with_sufficient_actual_issue() -> None:
    class Cursor:
        sql = ""

        def execute(self, sql: str, _params: tuple[object, ...]) -> None:
            self.sql = sql

        @staticmethod
        def fetchone() -> dict[str, object]:
            return {"request_id": 5, "issued_quantity": 20}

    cursor = Cursor()
    row = {"material_issue_request_id": 5, "material_id": 7, "pond_id": 3, "quantity": 20}
    MySqlProductionStore.require_material_issue(cursor, row)

    assert "document_type='issue_request'" in cursor.sql
    assert "document_type='issue'" in cursor.sql


def test_invalid_feed_task_assignee_is_rejected_before_fk_write() -> None:
    class Cursor:
        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            self.sql, self.params = sql, params

        @staticmethod
        def fetchone() -> None:
            return None

    with pytest.raises(DomainError, match="FEED_TASK_ASSIGNEE_INVALID") as raised:
        MySqlProductionStore._scope_defaults(Cursor(), {"assigned_user_id": 999999})

    assert raised.value.status == 400
