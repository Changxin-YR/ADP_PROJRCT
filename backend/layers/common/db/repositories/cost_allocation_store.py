from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.cost_enterprise_repository import decode, require_scope
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.cost.calculation import allocate_amount


class MySqlCostAllocationStore:
    def __init__(self, settings: Any) -> None:
        self.settings, self.audit = settings, AuditLogger()

    @staticmethod
    def _scope(cursor: Any, period_start: Any, period_end: Any, farm_id: int, area_id: int | None, user: dict[str, Any]) -> dict[str, Any]:
        cursor.execute(
            "SELECT f.organization_id,f.id AS farm_id,a.id AS area_id,%s AS created_by FROM farms f LEFT JOIN areas a ON a.id=%s AND a.farm_id=f.id AND a.status<>'archived' WHERE f.id=%s AND f.status<>'archived'",
            (user["id"], area_id, farm_id),
        )
        scope = cursor.fetchone()
        if not scope or (area_id is not None and scope.get("area_id") is None):
            raise DomainError("COST_ALLOCATION_SCOPE_INVALID", "成本分摊基地或区域不存在", 400)
        require_scope(user, scope)
        cursor.execute(
            "SELECT 1 FROM cost_entries WHERE organization_id=%s AND farm_id=%s AND (%s IS NULL OR area_id=%s) AND status='confirmed' AND period_start>=%s AND period_end<=%s LIMIT 1",
            (scope["organization_id"], farm_id, area_id, area_id, period_start, period_end),
        )
        if cursor.fetchone() is None:
            raise DomainError("COST_ALLOCATION_SCOPE_EMPTY", "当前范围没有可分摊的已确认成本", 422)
        return scope

    @staticmethod
    def _rule(cursor: Any, effective_at: Any) -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
        cursor.execute("SELECT * FROM cost_allocation_rule_versions WHERE status IN ('active','retired') AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s) ORDER BY effective_from DESC,version_no DESC LIMIT 1", (effective_at, effective_at))
        version = cursor.fetchone()
        if not version:
            raise DomainError("COST_ALLOCATION_RULE_MISSING", "当前期间没有生效的分摊规则", 422)
        cursor.execute("SELECT * FROM cost_allocation_rules WHERE version_id=%s", (version["id"],))
        rules = {int(row["category_id"]): decode(row) or {} for row in cursor.fetchall()}
        return version, rules

    @staticmethod
    def _participants(cursor: Any, scope: dict[str, Any], period_start: Any, period_end: Any) -> list[dict[str, Any]]:
        cursor.execute(
            """
            SELECT p.id AS pond_id,p.capacity_mu,
              (SELECT b.id FROM production_batches b WHERE b.pond_id=p.id AND b.status='verified'
                AND (b.stocked_at IS NULL OR DATE(b.stocked_at)<=%s) ORDER BY b.stocked_at DESC,b.id DESC LIMIT 1) AS batch_id,
              (SELECT COUNT(*) FROM cost_assets a WHERE a.organization_id=p.organization_id AND a.farm_id=p.farm_id
                AND a.status='confirmed' AND a.target_type='pond' AND a.target_id=p.id AND a.purchase_date<=%s) AS equipment_count,
              (SELECT COALESCE(SUM(CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(op.payload_json,'$.runtime_hours')),'null'),'0') AS DECIMAL(18,4))),0)
                FROM production_documents op WHERE op.pond_id=p.id AND op.document_type='daily_operation' AND op.status='verified'
                  AND DATE(op.happened_at) BETWEEN %s AND %s) AS runtime_hours,
              (SELECT COALESCE(SUM(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(work.payload_json,'$.work_scope')),'null') AS DECIMAL(18,4)),1)),0)
                FROM production_documents work WHERE work.pond_id=p.id AND work.document_type='daily_operation' AND work.status='verified'
                  AND DATE(work.happened_at) BETWEEN %s AND %s) AS work_scope,
              (SELECT COALESCE(SUM(GREATEST(stock.quantity_delta,0)),0) FROM batch_stock_records stock
                WHERE stock.pond_id=p.id AND stock.source_type='stocking' AND DATE(stock.happened_at) BETWEEN %s AND %s) AS direct_input,
              (SELECT COALESCE(-SUM(g.quantity_delta*g.unit_cost),0) FROM inventory_ledger g
                JOIN warehouse_documents d ON d.id=g.source_id WHERE g.pond_id=p.id AND d.status='verified'
                  AND d.document_type IN ('issue','return') AND g.source_type IN ('issue','return','correction')
                  AND DATE(g.happened_at) BETWEEN %s AND %s) AS direct_consumption
            FROM ponds p
            WHERE p.organization_id=%s AND p.farm_id=%s AND (%s IS NULL OR p.area_id=%s)
              AND p.status='verified' AND DATE(p.created_at)<=%s ORDER BY p.id
            """,
            (
                period_end, period_end, period_start, period_end, period_start, period_end,
                period_start, period_end, period_start, period_end, scope["organization_id"],
                scope["farm_id"], scope.get("area_id"), scope.get("area_id"), period_end,
            ),
        )
        rows = list(cursor.fetchall())
        if not rows:
            raise DomainError("COST_ALLOCATION_TARGET_EMPTY", "当前期间没有参与核算的塘口", 422)
        return rows

    @staticmethod
    def _weights(entry: dict[str, Any], rule: dict[str, Any], participants: list[dict[str, Any]]) -> tuple[list[tuple[int, Decimal]], bool]:
        direct_pond = None
        if entry.get("target_type") == "pond":
            direct_pond = int(entry["target_id"])
        elif entry.get("target_type") == "batch":
            direct_pond = next((int(row["pond_id"]) for row in participants if row.get("batch_id") == entry.get("target_id")), None)
        if direct_pond is not None:
            return [(int(row["pond_id"]), Decimal("1") if int(row["pond_id"]) == direct_pond else Decimal("0")) for row in participants], False
        driver = str(rule.get("driver") or "equal")
        manual = rule.get("manual_ratio_json") or {}
        if isinstance(manual, str):
            manual = json.loads(manual)
        weights = []
        for row in participants:
            if driver == "area":
                value = Decimal(str(row.get("capacity_mu") or 0))
            elif driver == "manual_ratio":
                value = Decimal(str(manual.get(str(row["pond_id"]), 0)))
            elif driver == "equal":
                value = Decimal("1")
            else:
                value = Decimal(str(row.get(driver) or 0))
            weights.append((int(row["pond_id"]), value))
        return weights, sum((value for _, value in weights), Decimal("0")) == 0

    def run_allocation(self, *, period_start: Any, period_end: Any, farm_id: int, area_id: int | None, user: dict[str, Any], user_id: int) -> dict[str, Any]:
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            scope = self._scope(cursor, period_start, period_end, farm_id, area_id, user); version, rules = self._rule(cursor, period_end)
            participants = self._participants(cursor, scope, period_start, period_end)
            cursor.execute("SELECT * FROM cost_entries WHERE organization_id=%s AND farm_id=%s AND (%s IS NULL OR area_id=%s) AND status='confirmed' AND period_start>=%s AND period_end<=%s ORDER BY id FOR UPDATE", (scope["organization_id"], scope["farm_id"], scope.get("area_id"), scope.get("area_id"), period_start, period_end))
            entries = list(cursor.fetchall())
            source_total = sum((Decimal(str(row["amount"])) for row in entries), Decimal("0"))
            if not entries or source_total == 0:
                raise DomainError("COST_ALLOCATION_SOURCE_EMPTY", "当前期间没有可分摊成本", 422)
            cursor.execute("SELECT COALESCE(MAX(result_version),0)+1 AS version FROM cost_allocation_runs WHERE organization_id=%s AND farm_id=%s AND area_id<=>%s AND period_start=%s AND period_end=%s FOR UPDATE", (scope["organization_id"], scope["farm_id"], scope.get("area_id"), period_start, period_end))
            result_version = int(cursor.fetchone()["version"])
            cursor.execute("UPDATE cost_allocation_runs SET status='superseded' WHERE organization_id=%s AND farm_id=%s AND area_id<=>%s AND period_start=%s AND period_end=%s AND status='completed'", (scope["organization_id"], scope["farm_id"], scope.get("area_id"), period_start, period_end))
            detail_rows, fallback_count = [], 0
            for entry in entries:
                rule = rules.get(int(entry["category_id"]), {"driver": "equal"})
                weights, fallback = self._weights(entry, rule, participants)
                allocations = allocate_amount(Decimal(str(entry["amount"])), weights)
                for participant in participants:
                    pond_id = int(participant["pond_id"]); amount = allocations.get(pond_id, Decimal("0"))
                    if amount == 0:
                        continue
                    detail_rows.append((entry, participant, rule, next(value for target, value in weights if target == pond_id), amount, fallback))
                    fallback_count += int(fallback)
            allocated_total = sum((row[4] for row in detail_rows), Decimal("0"))
            if allocated_total != source_total:
                raise DomainError("COST_ALLOCATION_UNBALANCED", "成本分摊金额不平", 500)
            snapshot = json.dumps(participants, ensure_ascii=False, default=str)
            cursor.execute("INSERT INTO cost_allocation_runs (organization_id,farm_id,area_id,period_start,period_end,rule_version_id,result_version,source_total,allocated_total,fallback_count,participant_snapshot_json,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (scope["organization_id"], scope["farm_id"], scope.get("area_id"), period_start, period_end, version["id"], result_version, source_total, allocated_total, fallback_count, snapshot, user_id))
            run_id = int(cursor.lastrowid)
            cursor.executemany(
                "INSERT INTO cost_allocation_details (run_id,cost_entry_id,category_id,pond_id,batch_id,amount,driver,driver_value,fallback_used,source_snapshot_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [(run_id, entry["id"], entry["category_id"], participant["pond_id"], participant.get("batch_id"), amount, rule.get("driver") or "equal", driver_value, fallback, json.dumps(entry, ensure_ascii=False, default=str)) for entry, participant, rule, driver_value, amount, fallback in detail_rows],
            )
            self.audit.write(connection, user_id=user_id, action="run_cost_allocation", object_type="cost_allocation_run", object_id=run_id, result="success", ip_address=None, module_code="cost", action_code="run_cost_allocation", after={"source_total": source_total, "allocated_total": allocated_total, "result_version": result_version})
            cursor.execute("SELECT * FROM cost_allocation_runs WHERE id=%s", (run_id,)); run = decode(cursor.fetchone()) or {}
            cursor.execute("SELECT * FROM cost_allocation_details WHERE run_id=%s ORDER BY pond_id,id", (run_id,)); run["details"] = [decode(row) or {} for row in cursor.fetchall()]
            return run
