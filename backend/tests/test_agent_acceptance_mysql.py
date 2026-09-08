from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from typing import Any

import pytest

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.idempotency import execute_idempotent
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.agent.agent_confirmation_store import MySqlAgentConfirmationStore
from backend.layers.features.agent.agent_contracts import AgentConfirmation
from backend.layers.features.master_data.master_data_service import MasterDataService
from backend.layers.features.master_data.master_data_store import MySqlMasterDataStore
from backend.tests.mysql_test_database import disposable_database, settings_for
from test_warehouse_mysql_integration import _seed


def _env_for(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYSQL_HOST", settings.mysql_host)
    monkeypatch.setenv("MYSQL_PORT", str(settings.mysql_port))
    monkeypatch.setenv("MYSQL_DATABASE", settings.mysql_database)
    monkeypatch.setenv("MYSQL_USER", settings.mysql_user)
    monkeypatch.setenv("MYSQL_PASSWORD", settings.mysql_password)


def _actor(user_id: int, area_id: int | None = None) -> dict[str, Any]:
    scopes = [] if area_id is None else [{"scope_type": "area", "area_id": area_id}]
    return {
        "id": user_id,
        "status": "active",
        "permissions": ["master_data.view", "master_data.manage"],
        "roles": [] if area_id is None else [{"code": "operator"}],
        "data_scopes": scopes,
        "_scope_enforced": area_id is not None,
    }


def test_mysql_confirmation_claim_is_exactly_once_under_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    with disposable_database("adp_agent_confirmation", through=31) as database:
        settings = settings_for(database)
        _env_for(settings, monkeypatch)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO users (phone,name,password_hash,status) VALUES ('13980000001','Agent User','hash','active')")
            user_id = int(cursor.lastrowid)
        store = MySqlAgentConfirmationStore()
        token = "confirmation-token-concurrency"
        row = store.create(
            AgentConfirmation(
                id=0,
                idempotency_key="agent-confirmation:pending",
                token_hash="",
                user_id=user_id,
                session_hash="session-hash",
                conversation_id="conversation-1",
                request_id="request-1",
                tool_name="master_data.create_record",
                payload={"resource": "ponds"},
                status="pending",
                expires_at=datetime.now() + timedelta(minutes=2),
            ),
            token,
        )
        barrier = Barrier(20)

        def claim() -> Any:
            barrier.wait()
            return store.claim(token=token, user_id=user_id, session_hash="session-hash")

        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(lambda _: claim(), range(20)))

        assert sum(result is not None for result in results) == 1
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status, used_at FROM agent_confirmations WHERE id=%s", (row.id,))
            stored = cursor.fetchone()
        assert stored["status"] == "confirmed"
        assert stored["used_at"] is not None


def test_agent_request_id_is_exactly_once_under_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    with disposable_database("adp_agent_idempotency", through=31) as database:
        settings = settings_for(database)
        _env_for(settings, monkeypatch)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO users (phone,name,password_hash,status) VALUES ('13980000002','Idempotent User','hash','active')")
            user_id = int(cursor.lastrowid)
        barrier = Barrier(10)
        calls: list[int] = []

        def operation() -> tuple[dict[str, Any], int]:
            calls.append(1)
            return {"mutation": "once"}, 200

        def invoke() -> tuple[str, Any]:
            barrier.wait()
            try:
                return ("ok", execute_idempotent(settings, user_id=user_id, action_code="agent:inventory.mutate", key="request-id-123456", payload={"quantity": 20}, operation=operation))
            except DomainError as error:
                return ("error", error.code)

        with ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(lambda _: invoke(), range(10)))

        assert calls == [1]
        assert all(kind == "ok" or value == "IDEMPOTENCY_IN_PROGRESS" for kind, value in outcomes)
        assert any(kind == "ok" for kind, _ in outcomes)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status, response_json FROM idempotency_keys WHERE user_id=%s", (user_id,))
            stored = cursor.fetchone()
        assert stored["status"] == "completed"
        assert '"mutation": "once"' in stored["response_json"]


def test_agent_audit_persists_before_after_and_failure_without_side_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    with disposable_database("adp_agent_audit", through=31) as database:
        settings = settings_for(database)
        _env_for(settings, monkeypatch)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO users (phone,name,password_hash,status) VALUES ('13980000003','Audit User','hash','active')")
            user_id = int(cursor.lastrowid)
            logger = AuditLogger()
            logger.write(connection, user_id=user_id, action="agent_tool", object_type="master:ponds", object_id=7, result="success", ip_address=None, request_id="agent-request-1", module_code="agent", action_code="master_data.update", before={"status": "active"}, after={"status": "inactive"})
            logger.write(connection, user_id=user_id, action="agent_tool", object_type="master:ponds", object_id=8, result="failure", ip_address=None, request_id="agent-request-2", module_code="agent", action_code="master_data.update", reason="DATA_SCOPE_FORBIDDEN", before={"status": "active"}, after=None)
            cursor.execute("SELECT result, request_id, before_json, after_json, changed_fields_json, reason FROM audit_logs WHERE user_id=%s ORDER BY id", (user_id,))
            rows = cursor.fetchall()
        assert rows[0]["result"] == "success"
        assert rows[0]["request_id"] == "agent-request-1"
        assert '"status": "active"' in rows[0]["before_json"]
        assert '"status": "inactive"' in rows[0]["after_json"]
        assert '"before": "active"' in rows[0]["changed_fields_json"]
        assert rows[1]["result"] == "failure"
        assert rows[1]["reason"] == "DATA_SCOPE_FORBIDDEN"
        assert rows[1]["after_json"] is None


def _run_pond_create(settings: Any, mode: str) -> dict[str, Any]:
    ids = _seed(settings)
    service = MasterDataService(MySqlMasterDataStore(settings))
    actor = _actor(1)
    payload = {"code": "P-EQUIV", "name": "等价性塘口", "area_id": ids["area_id"], "pond_status": "build"}
    if mode == "manual":
        return service.create(actor, "ponds", payload)
    from backend.layers.features.agent.agent_gateway_service import AgentGatewayService
    from backend.layers.features.agent.agent_tool_registry import build_registry
    from backend.tests.test_agent_gateway import _MemoryConfirmationStore

    registry = build_registry(lambda _tool: lambda arguments, _context: service.create(actor, "ponds", arguments["payload"]))
    gateway = AgentGatewayService(settings, registry=registry, confirmations=_MemoryConfirmationStore())
    pending = gateway.prepare_tool(actor, "master_data.create_record", {"payload": payload}, conversation_id="equivalence", request_id="request-equivalence")
    return gateway.confirm(actor, pending["confirmation"]["token"], request_id="request-equivalence-confirm")


def test_manual_and_agent_mysql_snapshots_are_business_equivalent() -> None:
    with disposable_database("adp_manual_equivalence", through=31) as manual_db:
        manual_settings = settings_for(manual_db)
        manual = _run_pond_create(manual_settings, "manual")
        assert manual["code"] == "P-EQUIV"
        from backend.tests.helpers.db_snapshot import compare_snapshots, snapshot_tables

        manual_snapshot = snapshot_tables(manual_settings, ["areas", "ponds"])

    with disposable_database("adp_agent_equivalence", through=31) as agent_db:
        agent_settings = settings_for(agent_db)
        agent = _run_pond_create(agent_settings, "agent")
        assert agent["kind"] == "success"
        agent_snapshot = snapshot_tables(agent_settings, ["areas", "ponds"])

        assert compare_snapshots(
            manual_snapshot,
            agent_snapshot,
            ignore_fields={
                "areas": {"created_at", "updated_at"},
                "ponds": {"id", "created_at", "updated_at", "created_by"},
            },
        )


def test_agent_scope_rejects_foreign_pond_without_database_change(monkeypatch: pytest.MonkeyPatch) -> None:
    with disposable_database("adp_agent_idor", through=31) as database:
        settings = settings_for(database)
        _env_for(settings, monkeypatch)
        ids = _seed(settings)
        service = MasterDataService(MySqlMasterDataStore(settings))
        scoped_user = _actor(2, area_id=ids["area_id"] + 1)
        with pytest.raises(DomainError, match="DATA_SCOPE_FORBIDDEN"):
            service.update(scoped_user, "ponds", ids["pond_id"], {"expected_version": 1, "name": "越权修改"})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT name FROM ponds WHERE id=%s", (ids["pond_id"],))
            assert cursor.fetchone()["name"] == "一号塘"
