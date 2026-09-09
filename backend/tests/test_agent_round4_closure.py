from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from threading import Barrier
from typing import Any, Callable

import pytest
from openpyxl import Workbook

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.idempotency import execute_idempotent
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.agent.agent_confirmation_store import MySqlAgentConfirmationStore
from backend.layers.features.agent.agent_gateway_service import AgentGatewayError, AgentGatewayService
from backend.layers.features.agent.agent_tool_registry import AgentTool, AgentToolRegistry
from backend.layers.features.data_exchange.data_exchange_service import DataExchangeService
from backend.layers.features.data_exchange.data_exchange_store import MySqlDataExchangeStore
from backend.layers.features.master_data.master_data_service import MasterDataService
from backend.layers.features.master_data.master_data_store import MySqlMasterDataStore
from backend.layers.features.production.production_service import ProductionService
from backend.layers.features.production.production_store import MySqlProductionStore
from backend.layers.features.purchase.purchase_service import PurchaseService
from backend.layers.features.purchase.purchase_store import MySqlPurchaseStore
from backend.layers.features.sales.sales_service import SalesService
from backend.layers.features.sales.sales_store import MySqlSalesStore
from backend.layers.features.warehouse.warehouse_service import WarehouseService
from backend.layers.features.warehouse.warehouse_store import MySqlWarehouseStore
from backend.tests.mysql_test_database import disposable_database, settings_for
from test_warehouse_mysql_integration import _seed


def _actor(user_id: int, permissions: list[str], *, area_id: int | None = None) -> dict[str, Any]:
    return {
        "id": user_id,
        "status": "active",
        "permissions": permissions,
        "roles": [],
        "data_scopes": [] if area_id is None else [{"scope_type": "area", "area_id": area_id}],
        "_scope_enforced": area_id is not None,
        "_session_hash": f"session-{user_id}",
        "_session_token": f"session-token-{user_id}",
    }


def _audit_writer(settings: Any) -> Callable[[dict[str, Any]], None]:
    logger = AuditLogger()

    def write(event: dict[str, Any]) -> None:
        with get_connection(settings) as connection:
            logger.write(
                connection,
                user_id=int(event.get("user_id") or 0),
                action="agent_tool",
                object_type=str(event.get("tool_name") or "agent_tool"),
                object_id=int(event.get("object_id") or 0) or None,
                result=str(event.get("result") or "failure"),
                ip_address=None,
                request_id=str(event.get("request_id") or ""),
                module_code="agent",
                action_code=str(event.get("tool_name") or "agent_tool"),
                reason=event.get("reason"),
                before=event.get("before"),
                after=event.get("after"),
                detail_json=__import__("json").dumps(event, ensure_ascii=False, default=str),
            )

    return write


def _agent_write(
    settings: Any,
    actor: dict[str, Any],
    tool_name: str,
    execute: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    arguments: dict[str, Any],
    *,
    request_id: str,
) -> dict[str, Any]:
    tool = AgentTool(
        name=tool_name,
        description=tool_name,
        method="POST",
        path_template=f"/api/v1/round4/{tool_name}",
        parameters={"payload": {"type": "object", "required": True}},
        required_permission="warehouse.manage",
        risk="write",
        execute=execute,
        requires_data_scope=True,
    )
    gateway = AgentGatewayService(
        settings,
        registry=AgentToolRegistry((tool,)),
        confirmations=MySqlAgentConfirmationStore(settings),
        audit=_audit_writer(settings),
    )
    pending = gateway.prepare_tool(
        actor,
        tool_name,
        {**arguments, "raw_instruction": arguments.get("raw_instruction", tool_name)},
        conversation_id=f"round4-{request_id}",
        request_id=f"{request_id}-prepare",
    )
    return gateway.confirm(actor, pending["confirmation"]["token"], request_id=f"{request_id}-confirm")


def test_agent_idor_rejects_foreign_area_without_mutation() -> None:
    with disposable_database("adp_round4_idor", through=32) as database:
        settings = settings_for(database)
        ids = _seed(settings)
        service = MasterDataService(MySqlMasterDataStore(settings))
        user = _actor(2, ["master_data.view", "master_data.manage"], area_id=ids["area_id"] + 99)
        tool = AgentTool(
            name="master_data.update_record",
            description="更新塘口",
            method="PATCH",
            path_template="/api/v1/master-data/ponds/{record_id}",
            parameters={"payload": {"type": "object", "required": True}},
            required_permission="master_data.manage",
            risk="write",
            execute=lambda arguments, _context: service.update(user, "ponds", ids["pond_id"], arguments["payload"]),
            permission_namespace="master_data",
            permission_action="manage",
            resource_argument="resource",
        )
        gateway = AgentGatewayService(
            settings,
            registry=AgentToolRegistry((tool,)),
            confirmations=MySqlAgentConfirmationStore(settings),
            audit=_audit_writer(settings),
        )
        pending = gateway.prepare_tool(
            user,
            tool.name,
            {"resource": "ponds", "record_id": ids["pond_id"], "payload": {"expected_version": 1, "name": "foreign"}, "raw_instruction": "修改 B 区塘口"},
            conversation_id="idor",
            request_id="idor-prepare",
        )
        with pytest.raises(AgentGatewayError) as error:
            gateway.confirm(user, pending["confirmation"]["token"], request_id="idor-confirm")
        assert error.value.status == 400
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT name FROM ponds WHERE id=%s", (ids["pond_id"],))
            assert cursor.fetchone()["name"] == "一号塘"
            cursor.execute("SELECT COUNT(*) AS total FROM audit_logs WHERE request_id='idor-confirm' AND result='failure'")
            assert cursor.fetchone()["total"] == 1


def test_agent_confirmation_concurrency_posts_inventory_and_cost_once() -> None:
    with disposable_database("adp_round4_confirmation", through=32) as database:
        settings = settings_for(database)
        ids = _seed(settings)
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO inventory_lots (organization_id,material_id,lot_no,unit_cost,status) VALUES (%s,%s,'ROUND4-LOT',5,'available')",
                (ids["organization_id"], ids["material_id"]),
            )
            lot_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,'round4',1,%s,%s,'round4.pdf','application/pdf',12,1)", (ids["organization_id"], "c" * 64, "d" * 32))
            attachment_id = int(cursor.lastrowid)
        warehouse = WarehouseService(MySqlWarehouseStore(settings))
        actor = _actor(1, ["warehouse.view", "warehouse.manage", "warehouse.verify"])
        verifier = _actor(2, ["warehouse.view", "warehouse.verify"])
        created = warehouse.create(actor, "receipts", {"code": "ROUND4-REC", "name": "并发入库", "warehouse_id": ids["warehouse_1"], "material_id": ids["material_id"], "quantity": 20, "unit_cost": 5, "lot_no": "ROUND4-LOT", "expiry_date": "2027-01-01"})
        submitted = warehouse.submit(actor, "receipts", created["id"], {"expected_version": created["version"]})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE attachments SET entity_type='warehouse:receipts',entity_id=%s WHERE id=%s", (created["id"], attachment_id))
        tool_name = "warehouse.verify_receipt"
        tool = AgentTool(
            name=tool_name,
            description="核验入库",
            method="POST",
            path_template="/api/v1/warehouse/receipts/{record_id}/verify",
            parameters={"payload": {"type": "object", "required": True}},
            required_permission="warehouse.verify",
            risk="write",
            execute=lambda arguments, _context: warehouse.verify(verifier, "receipts", created["id"], arguments["payload"]),
        )
        gateway = AgentGatewayService(settings, registry=AgentToolRegistry((tool,)), confirmations=MySqlAgentConfirmationStore(settings), audit=_audit_writer(settings))
        pending = gateway.prepare_tool(verifier, tool_name, {"record_id": created["id"], "payload": {"expected_version": submitted["version"], "evidence_attachment_ids": [attachment_id]}, "raw_instruction": "确认入库"}, conversation_id="confirm-effect", request_id="confirm-effect-prepare")
        token = pending["confirmation"]["token"]
        barrier = Barrier(20)

        def confirm() -> tuple[str, str]:
            barrier.wait()
            try:
                return "ok", gateway.confirm(verifier, token, request_id="confirm-effect-confirm")["kind"]
            except AgentGatewayError as error:
                return "error", error.code

        with ThreadPoolExecutor(max_workers=20) as pool:
            outcomes = list(pool.map(lambda _: confirm(), range(20)))
        assert sum(kind == "ok" for kind, _ in outcomes) == 1
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status FROM warehouse_documents WHERE id=%s", (created["id"],))
            assert cursor.fetchone()["status"] == "verified"
            cursor.execute("SELECT COUNT(*) AS total FROM inventory_ledger WHERE source_type='receipt' AND source_id=%s", (created["id"],))
            assert cursor.fetchone()["total"] == 1
            cursor.execute("SELECT COUNT(*) AS total FROM agent_confirmations WHERE id=%s AND status='confirmed'", (pending["confirmation"]["id"],))
            assert cursor.fetchone()["total"] == 1
            cursor.execute("SELECT COUNT(*) AS total FROM audit_logs WHERE request_id='confirm-effect-confirm' AND result='success'")
            assert cursor.fetchone()["total"] == 1


def _workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["code", "name", "category", "unit"])
    sheet.append(["ROUND4-IMPORT", "幂等导入", "饲料", "kg"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_agent_request_id_idempotency_covers_payment_receipt_inventory_and_import(tmp_path: Path) -> None:
    with disposable_database("adp_round4_idempotency", through=32) as database:
        settings = settings_for(database)
        ids = _seed(settings)
        purchase = PurchaseService(MySqlPurchaseStore(settings))
        purchaser = _actor(1, ["purchase.view", "purchase.manage", "purchase.verify", "finance.payment.manage", "finance.payable.view"])
        order = purchase.create_order(purchaser, {"code": "ROUND4-PO", "name": "幂等采购", "supplier_id": ids["supplier_id"], "material_id": ids["material_id"], "warehouse_id": ids["warehouse_1"], "quantity": 2, "unit_price": 5, "due_date": "2026-12-31"})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,material_id,purchase_order_id,quantity,unit_cost,lot_no,status,created_by) VALUES (%s,%s,%s,'receipt','ROUND4-SOURCE','幂等来源',%s,%s,%s,2,5,'ROUND4-SOURCE-LOT','verified',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["warehouse_1"], ids["material_id"], order["id"]))
            source_receipt_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO purchase_payables (organization_id,purchase_order_id,source_receipt_id,supplier_id,idempotency_key,amount,due_date) VALUES (%s,%s,%s,%s,'ROUND4-PAYABLE',10,'2026-12-31')", (ids["organization_id"], order["id"], source_receipt_id, ids["supplier_id"]))
            payable_id = int(cursor.lastrowid)
        payment_payload = {"code": "ROUND4-PAY", "name": "幂等付款", "payable_id": payable_id, "amount": 10, "paid_at": "2026-09-08", "payment_method": "bank_transfer"}
        payment_calls = []

        def payment_operation() -> tuple[dict[str, Any], int]:
            payment_calls.append(1)
            return purchase.create_payment(purchaser, payment_payload), 200

        barrier = Barrier(10)

        def payment_call(_: int) -> tuple[str, Any]:
            barrier.wait()
            try:
                return "ok", execute_idempotent(settings, user_id=1, action_code="agent:payment.create", key="round4-payment-key", payload=payment_payload, operation=payment_operation)
            except DomainError as error:
                return "error", error.code

        with ThreadPoolExecutor(max_workers=10) as pool:
            payment_results = list(pool.map(payment_call, range(10)))
        successful_payments = [value for kind, value in payment_results if kind == "ok"]
        assert payment_calls == [1] and successful_payments
        payment = successful_payments[0][0]
        # Deterministic timeout model: the first committed response is discarded
        # before the client receives it; the same request id must replay it.
        replay, _ = execute_idempotent(settings, user_id=1, action_code="agent:payment.create", key="round4-payment-key", payload=payment_payload, operation=payment_operation)
        assert payment["id"] == replay["id"]

        sales = SalesService(MySqlSalesStore(settings))
        customer_id = ids["supplier_id"]
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO business_partners (organization_id,farm_id,area_id,partner_type,code,name,status,created_by) VALUES (%s,%s,%s,'customer','ROUND4-CUSTOMER','幂等客户','verified',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"]))
            customer_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO production_batches (organization_id,farm_id,area_id,pond_id,code,name,species,status,created_by) VALUES (%s,%s,%s,%s,'ROUND4-BATCH','幂等批次','鲈鱼','verified',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["pond_id"]))
            batch_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO production_documents (organization_id,farm_id,area_id,document_type,code,name,batch_id,pond_id,quantity,weight_kg,happened_at,status,created_by,verified_by,verified_at) VALUES (%s,%s,%s,'harvest','ROUND4-HARVEST','幂等出塘',%s,%s,2,2,'2026-09-08','verified',1,2,NOW())", (ids["organization_id"], ids["farm_id"], ids["area_id"], batch_id, ids["pond_id"]))
            harvest_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_orders (organization_id,farm_id,area_id,pond_id,batch_id,customer_id,code,name,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,'ROUND4-SO','幂等销售','鲈鱼',2,'kg',10,20,'2026-09-08','2026-12-31','approved',1)", (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["pond_id"], batch_id, customer_id))
            sales_order_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_deliveries (organization_id,sales_order_id,harvest_document_id,harvest_root_id,code,name,quantity,delivered_at,status,created_by) VALUES (%s,%s,%s,%s,'ROUND4-SD','幂等交付',2,'2026-09-08','verified',1)", (ids["organization_id"], sales_order_id, harvest_id, harvest_id))
            delivery_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO sales_receivables (organization_id,sales_order_id,source_delivery_id,customer_id,idempotency_key,amount,due_date) VALUES (%s,%s,%s,%s,'ROUND4-RECEIVABLE',20,'2026-12-31')", (ids["organization_id"], sales_order_id, delivery_id, customer_id))
            receivable_id = int(cursor.lastrowid)
        cashier = _actor(1, ["finance.receivable.view", "finance.receipt.manage"])
        receipt_payload = {"code": "ROUND4-RECEIPT", "name": "幂等收款", "receivable_id": receivable_id, "amount": 20, "received_at": "2026-09-08", "receipt_method": "bank_transfer"}
        receipt_calls = []

        def receipt_operation() -> tuple[dict[str, Any], int]:
            receipt_calls.append(1)
            return sales.create_receipt(cashier, receipt_payload), 200

        barrier = Barrier(10)

        def receipt_call(_: int) -> tuple[str, Any]:
            barrier.wait()
            try:
                return "ok", execute_idempotent(settings, user_id=1, action_code="agent:receipt.create", key="round4-receipt-key", payload=receipt_payload, operation=receipt_operation)
            except DomainError as error:
                return "error", error.code

        with ThreadPoolExecutor(max_workers=10) as pool:
            receipt_results = list(pool.map(receipt_call, range(10)))
        successful_receipts = [value for kind, value in receipt_results if kind == "ok"]
        assert receipt_calls == [1] and successful_receipts
        receipt = successful_receipts[0][0]
        replay_receipt, _ = execute_idempotent(settings, user_id=1, action_code="agent:receipt.create", key="round4-receipt-key", payload=receipt_payload, operation=receipt_operation)
        assert receipt["id"] == replay_receipt["id"]

        inventory = WarehouseService(MySqlWarehouseStore(settings))
        warehouse_actor = _actor(1, ["warehouse.view", "warehouse.manage", "warehouse.verify"])
        inventory_verifier = _actor(2, ["warehouse.view", "warehouse.verify"])
        inventory_receipt = inventory.create(warehouse_actor, "receipts", {"code": "ROUND4-IDEMP-RECEIPT", "name": "幂等入库", "warehouse_id": ids["warehouse_1"], "material_id": ids["material_id"], "quantity": 1, "unit_cost": 5, "lot_no": "ROUND4-IDEMP-LOT", "expiry_date": "2027-01-01"})
        inventory_receipt = inventory.submit(warehouse_actor, "receipts", inventory_receipt["id"], {"expected_version": inventory_receipt["version"]})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,'warehouse:receipts',%s,%s,%s,'idempotency.pdf','application/pdf',12,1)", (ids["organization_id"], inventory_receipt["id"], "i" * 64, "i" * 32))
            inventory_attachment = int(cursor.lastrowid)

        def inventory_operation() -> tuple[dict[str, Any], int]:
            return inventory.verify(inventory_verifier, "receipts", inventory_receipt["id"], {"expected_version": inventory_receipt["version"], "evidence_attachment_ids": [inventory_attachment]}), 200

        with ThreadPoolExecutor(max_workers=10) as pool:
            barrier = Barrier(10)

            def inventory_call(_: int) -> tuple[str, Any]:
                barrier.wait()
                try:
                    return "ok", execute_idempotent(settings, user_id=1, action_code="agent:inventory.mutate", key="round4-inventory-key", payload={"quantity": 1}, operation=inventory_operation)
                except DomainError as error:
                    return "error", error.code

            inventory_results = list(pool.map(inventory_call, range(10)))
        assert sum(kind == "ok" for kind, _ in inventory_results) == 1
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status FROM warehouse_documents WHERE id=%s", (inventory_receipt["id"],))
            assert cursor.fetchone()["status"] == "verified"
            cursor.execute("SELECT COUNT(*) AS total FROM inventory_ledger WHERE source_type='receipt' AND source_id=%s", (inventory_receipt["id"],))
            assert cursor.fetchone()["total"] == 1
        inventory_replay, _ = execute_idempotent(
            settings,
            user_id=1,
            action_code="agent:inventory.mutate",
            key="round4-inventory-key",
            payload={"quantity": 1},
            operation=inventory_operation,
        )
        assert inventory_replay["id"] == inventory_receipt["id"]

        exchange = DataExchangeService(MySqlDataExchangeStore(settings), tmp_path)
        user = _actor(1, ["data_exchange.view", "data_exchange.import", "data_exchange.export", "production.view"])
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT id FROM organizations WHERE code='default'")
            organization_id = int(cursor.fetchone()["id"])
        imported = exchange.preview(user, organization_id=organization_id, template_code="materials", file_name="round4.xlsx", content=_workbook())
        assert imported["status"] == "ready"
        import_calls = []

        def import_operation() -> tuple[dict[str, Any], int]:
            import_calls.append(1)
            return exchange.confirm(user, imported["id"]), 200

        barrier = Barrier(10)

        def import_call(_: int) -> tuple[str, Any]:
            barrier.wait()
            try:
                return "ok", execute_idempotent(settings, user_id=1, action_code="agent:data-import.confirm", key="round4-import-key", payload={"batch_id": imported["id"]}, operation=import_operation)
            except DomainError as error:
                return "error", error.code

        with ThreadPoolExecutor(max_workers=10) as pool:
            import_results = list(pool.map(import_call, range(10)))
        successful_imports = [value for kind, value in import_results if kind == "ok"]
        assert import_calls == [1] and successful_imports
        confirmed = successful_imports[0][0]
        replay_import, _ = execute_idempotent(settings, user_id=1, action_code="agent:data-import.confirm", key="round4-import-key", payload={"batch_id": imported["id"]}, operation=import_operation)
        assert confirmed["status"] == replay_import["status"] == "imported"
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM purchase_payments WHERE code='ROUND4-PAY'")
            assert cursor.fetchone()["total"] == 1
            cursor.execute("SELECT COUNT(*) AS total FROM sales_receipts WHERE code='ROUND4-RECEIPT'")
            assert cursor.fetchone()["total"] == 1
            cursor.execute("SELECT COUNT(*) AS total FROM materials WHERE code='ROUND4-IMPORT'")
            assert cursor.fetchone()["total"] == 1
            cursor.execute("SELECT COUNT(*) AS total FROM data_import_items WHERE import_batch_id=%s", (imported["id"],))
            assert cursor.fetchone()["total"] == 1
            cursor.execute("SELECT COUNT(*) AS total FROM idempotency_keys WHERE user_id=1 AND action_code IN ('agent:payment.create','agent:receipt.create','agent:inventory.mutate','agent:data-import.confirm') AND status='completed'")
            assert cursor.fetchone()["total"] == 4


def test_agent_confirmation_payment_effects_are_exactly_once() -> None:
    """A confirmed payment may be claimed by many callers, but posts once."""
    with disposable_database("adp_round4_payment_confirmation", through=32) as database:
        settings = settings_for(database)
        ids = _seed(settings)
        purchase = PurchaseService(MySqlPurchaseStore(settings))
        maker = _actor(1, ["purchase.view", "purchase.manage", "finance.payment.manage", "finance.payable.view"])
        checker = _actor(2, ["purchase.view", "purchase.verify", "finance.payment.verify", "finance.payable.view"])
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO warehouse_documents (organization_id,farm_id,area_id,document_type,code,name,warehouse_id,material_id,purchase_order_id,quantity,unit_cost,lot_no,status,created_by) VALUES (%s,%s,%s,'receipt','R4-PAY-SOURCE','付款来源',%s,%s,%s,2,5,'R4-PAY-LOT','verified',1)",
                (ids["organization_id"], ids["farm_id"], ids["area_id"], ids["warehouse_1"], ids["material_id"], ids["purchase_order_id"]),
            )
            receipt_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO purchase_payables (organization_id,purchase_order_id,source_receipt_id,supplier_id,idempotency_key,amount,due_date) VALUES (%s,%s,%s,%s,'R4-PAYABLE-CONF',10,'2026-12-31')",
                (ids["organization_id"], ids["purchase_order_id"], receipt_id, ids["supplier_id"]),
            )
            payable_id = int(cursor.lastrowid)
        payment = purchase.create_payment(maker, {"code": "R4-CONF-PAY", "name": "确认付款", "payable_id": payable_id, "amount": 10, "paid_at": "2026-09-08", "payment_method": "bank_transfer"})
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO attachments (organization_id,entity_type,entity_id,sha256,storage_name,original_name,media_type,size_bytes,uploaded_by) VALUES (%s,'purchase:payment',%s,%s,%s,'payment.pdf','application/pdf',12,1)",
                (ids["organization_id"], payment["id"], "r" * 64, "r" * 32),
            )
            evidence_id = int(cursor.lastrowid)
        payment = purchase.submit_payment(maker, payment["id"], {"expected_version": payment["version"]})
        audit = _audit_writer(settings)
        tool = AgentTool(
            name="purchase.verify_payment",
            description="核验付款",
            method="POST",
            path_template="/api/v1/purchase/payments/{record_id}/verify",
            parameters={"payload": {"type": "object", "required": True}},
            required_permission="finance.payment.verify",
            risk="write",
            execute=lambda arguments, _context: purchase.verify_payment(checker, payment["id"], arguments["payload"]),
        )
        gateway = AgentGatewayService(settings, registry=AgentToolRegistry((tool,)), confirmations=MySqlAgentConfirmationStore(settings), audit=audit)
        pending = gateway.prepare_tool(checker, tool.name, {"record_id": payment["id"], "payload": {"expected_version": payment["version"], "evidence_attachment_ids": [evidence_id]}, "raw_instruction": "确认付款"}, conversation_id="r4-payment", request_id="r4-payment-prepare")
        token = pending["confirmation"]["token"]
        barrier = Barrier(20)

        def confirm_once(_: int) -> tuple[str, str]:
            barrier.wait()
            try:
                return "ok", gateway.confirm(checker, token, request_id="r4-payment-confirm")["kind"]
            except AgentGatewayError as error:
                return "error", error.code

        with ThreadPoolExecutor(max_workers=20) as pool:
            outcomes = list(pool.map(confirm_once, range(20)))
        assert sum(kind == "ok" for kind, _ in outcomes) == 1
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status FROM purchase_payments WHERE id=%s", (payment["id"],))
            assert cursor.fetchone()["status"] == "verified"
            cursor.execute("SELECT paid_amount,status FROM purchase_payables WHERE id=%s", (payable_id,))
            assert cursor.fetchone() == {"paid_amount": Decimal("10.00"), "status": "settled"}
            cursor.execute("SELECT COUNT(*) AS total FROM audit_logs WHERE request_id='r4-payment-confirm' AND result='success'")
            assert cursor.fetchone()["total"] == 1


def test_agent_audit_trace_reconstructs_success_and_failure() -> None:
    with disposable_database("adp_round4_audit_trace", through=32) as database:
        settings = settings_for(database)
        ids = _seed(settings)
        actor = _actor(1, ["master_data.view", "master_data.manage"], area_id=ids["area_id"])
        service = MasterDataService(MySqlMasterDataStore(settings))
        target = service.create(actor, "ponds", {"code": "R4-AUDIT-POND", "name": "审计前塘", "area_id": ids["area_id"]})
        target_id = int(target["id"])

        def execute(arguments: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
            with get_connection(settings) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT * FROM ponds WHERE id=%s", (target_id,))
                before = dict(cursor.fetchone())
            after = service.update(actor, "ponds", target_id, arguments["payload"])
            return {"before": before, "after": after}

        tool = AgentTool(
            name="master_data.update_record",
            description="更新塘口",
            method="PATCH",
            path_template="/api/v1/master-data/{resource}/{record_id}",
            parameters={"payload": {"type": "object", "required": True}},
            required_permission="master_data.manage",
            risk="write",
            execute=execute,
            permission_namespace="master_data",
            permission_action="manage",
            resource_argument="resource",
        )
        gateway = AgentGatewayService(settings, registry=AgentToolRegistry((tool,)), confirmations=MySqlAgentConfirmationStore(settings), audit=_audit_writer(settings))
        pending = gateway.prepare_tool(actor, tool.name, {"resource": "ponds", "record_id": target_id, "payload": {"expected_version": 1, "name": "审计后塘"}, "raw_instruction": "把 P001 停用"}, conversation_id="r4-audit", request_id="r4-audit-prepare")
        gateway.confirm(actor, pending["confirmation"]["token"], request_id="r4-audit-confirm")
        with pytest.raises(AgentGatewayError) as error:
            gateway.prepare_tool(_actor(2, ["master_data.view"], area_id=ids["area_id"]), tool.name, {"resource": "ponds", "record_id": target_id, "payload": {"expected_version": 2, "name": "越权"}, "raw_instruction": "越权修改"}, conversation_id="r4-audit", request_id="r4-audit-denied")
        assert error.value.code == "FORBIDDEN"
        with get_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT result,request_id,detail_json,before_json,after_json,reason FROM audit_logs WHERE request_id IN ('r4-audit-prepare','r4-audit-confirm','r4-audit-denied') ORDER BY id")
            rows = cursor.fetchall()
        assert len(rows) == 3
        success = rows[1]
        assert success["result"] == "success"
        detail = __import__("json").loads(success["detail_json"])
        assert detail["authenticated_user_id"] == actor["id"]
        assert detail["raw_instruction"] == "把 P001 停用"
        assert detail["intent"] == tool.name
        assert detail["tool_name"] == tool.name
        assert detail["required_permission"] == "master_data.manage"
        assert detail["confirmation_id"] == pending["confirmation"]["id"]
        assert __import__("json").loads(success["before_json"])["name"] == "审计前塘"
        assert __import__("json").loads(success["after_json"])["name"] == "审计后塘"
        assert rows[2]["result"] == "failure" and rows[2]["reason"] == "FORBIDDEN"
