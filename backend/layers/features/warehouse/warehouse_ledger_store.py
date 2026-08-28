from __future__ import annotations
from decimal import Decimal
from typing import Any
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.warehouse.warehouse_posting import allocate_fefo, amount, build_movements, movement_difference
from backend.layers.features.purchase.purchase_posting import post_purchase_receipt
class WarehouseLedgerPoster:
    @staticmethod
    def lock_business_anchors(cursor: Any, resource: str, row: dict[str, Any]) -> None:
        """Serialize quota and stock decisions before consistent reads are made."""
        if row.get("source_document_id") and resource in {"issues", "returns"}:
            cursor.execute(
                "SELECT id FROM warehouse_documents WHERE id=%s FOR UPDATE",
                (row["source_document_id"],),
            )
            cursor.fetchone()
        if resource not in {"issues", "transfers", "stocktakes", "scraps"} and not row.get("correction_of_id"):
            return
        cursor.execute(
            "SELECT id FROM inventory_lots WHERE organization_id=%s AND material_id=%s AND status='available' ORDER BY id FOR UPDATE",
            (row["organization_id"], row["material_id"]),
        )
        cursor.fetchall()
    @staticmethod
    def ensure_receipt_lot(cursor: Any, row: dict[str, Any]) -> int:
        if row.get("inventory_lot_id"):
            return int(row["inventory_lot_id"])
        if not str(row.get("lot_no") or "").strip():
            raise DomainError("WAREHOUSE_LOT_REQUIRED", "入库核验必须填写物料批次", 400)
        cursor.execute(
            "INSERT INTO inventory_lots (organization_id,material_id,lot_no,production_date,expiry_date,unit_cost) VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)",
            (row["organization_id"], row["material_id"], row["lot_no"], row.get("production_date"), row.get("expiry_date"), row.get("unit_cost") or 0),
        )
        return int(cursor.lastrowid)
    @staticmethod
    def _lots(cursor: Any, row: dict[str, Any]) -> list[dict[str, Any]]:
        cursor.execute(
            """
            SELECT l.id,l.expiry_date,l.expiry_date<CURRENT_DATE AS expired,
                   COALESCE(SUM(g.quantity_delta),0)-COALESCE((
                       SELECT SUM(d.quantity) FROM warehouse_documents d
                       WHERE d.document_type='scrap' AND d.status='submitted'
                       AND d.id<>%s
                       AND d.warehouse_id=%s AND d.material_id=l.material_id AND d.inventory_lot_id=l.id
                       AND NOT EXISTS (SELECT 1 FROM warehouse_documents newer WHERE newer.correction_of_id=d.id AND newer.status='submitted')
                   ),0) AS available
            FROM inventory_lots l
            LEFT JOIN inventory_ledger g ON g.inventory_lot_id=l.id AND g.warehouse_id=%s
            WHERE l.organization_id=%s AND l.material_id=%s AND l.status='available'
            GROUP BY l.id,l.expiry_date,l.material_id
            HAVING available>0
            FOR UPDATE
            """,
            (row.get("id") or 0, row["warehouse_id"], row["warehouse_id"], row["organization_id"], row["material_id"]),
        )
        return list(cursor.fetchall())
    def _allocations(self, cursor: Any, row: dict[str, Any]) -> list[tuple[int, Decimal]]:
        return allocate_fefo(
            self._lots(cursor, row),
            amount(row.get("quantity")),
            specified_lot_id=int(row["inventory_lot_id"]) if row.get("inventory_lot_id") else None,
            override_reason=str(row.get("override_reason") or "") or None,
            include_expired=row.get("_resource") == "scraps",
        )
    @staticmethod
    def _book_quantity(cursor: Any, row: dict[str, Any]) -> Decimal:
        if not row.get("inventory_lot_id"):
            raise DomainError("WAREHOUSE_LOT_REQUIRED", "盘点必须选择物料批次", 400)
        cursor.execute(
            "SELECT COALESCE(SUM(quantity_delta),0) AS quantity FROM inventory_ledger WHERE warehouse_id=%s AND material_id=%s AND inventory_lot_id=%s",
            (row["warehouse_id"], row["material_id"], row["inventory_lot_id"]),
        )
        return Decimal(str((cursor.fetchone() or {}).get("quantity", 0)))
    @staticmethod
    def _validate_return(cursor: Any, row: dict[str, Any]) -> None:
        cursor.execute("SELECT organization_id,warehouse_id,material_id,document_type,status FROM warehouse_documents WHERE id=%s FOR UPDATE", (row["source_document_id"],))
        source = cursor.fetchone()
        if source is None or source.get("document_type") != "issue" or source.get("status") != "verified" or any(
            int(source.get(key) or 0) != int(row.get(key) or 0) for key in ("organization_id", "warehouse_id", "material_id")
        ):
            raise DomainError("WAREHOUSE_RETURN_SOURCE_INVALID", "退库必须回到原出库单的同一企业、仓库和物料", 409)
        issued = -sum(
            (
                Decimal(str(movement["quantity_delta"]))
                for movement in WarehouseLedgerPoster()._effective_movements(cursor, int(row["source_document_id"]))
                if int(movement["warehouse_id"]) == int(row["warehouse_id"])
                and int(movement["inventory_lot_id"]) == int(row["inventory_lot_id"])
                and Decimal(str(movement["quantity_delta"])) < 0
            ),
            Decimal("0"),
        )
        cursor.execute(
            "SELECT COALESCE(SUM(g.quantity_delta),0) AS returned FROM inventory_ledger g JOIN warehouse_documents d ON d.id=g.source_id WHERE d.document_type='return' AND d.source_document_id=%s AND d.status='verified' AND g.source_type IN ('return','correction') AND g.inventory_lot_id=%s",
            (row["source_document_id"], row["inventory_lot_id"]),
        )
        returned = Decimal(str((cursor.fetchone() or {}).get("returned", 0)))
        if amount(row.get("quantity")) > issued - returned:
            raise DomainError("WAREHOUSE_RETURN_EXCEEDS_ISSUE", "退库数量不能超过原出库未退数量", 409)
    @staticmethod
    def _validate_issue_request(cursor: Any, row: dict[str, Any]) -> None:
        cursor.execute("SELECT id FROM warehouse_documents WHERE id=%s FOR UPDATE", (row["source_document_id"],))
        cursor.fetchone()
        cursor.execute(
            """
            SELECT r.id,r.quantity AS requested_quantity,COALESCE((
              SELECT -SUM(g.quantity_delta)
              FROM inventory_ledger g
              JOIN warehouse_documents i ON i.id=g.source_id
              WHERE i.source_document_id=r.id AND i.document_type='issue' AND i.status='verified'
                AND i.id<>%s AND g.source_type IN ('issue','correction')
            ),0) AS issued_quantity
            FROM warehouse_documents r
            WHERE r.id=%s AND r.document_type='issue_request' AND r.status='verified'
              AND r.material_id=%s AND r.pond_id<=>%s
            GROUP BY r.id,r.quantity
            HAVING issued_quantity+%s<=requested_quantity
            """,
            (row.get("id") or 0, row.get("source_document_id"), row.get("material_id"), row.get("pond_id"), row.get("quantity") or 0),
        )
        if cursor.fetchone() is None:
            raise DomainError("WAREHOUSE_ISSUE_REQUEST_INVALID", "实际出库必须关联已核验且剩余额度充足的领用申请", 409)
    @staticmethod
    def _ledger_movements(cursor: Any, source_id: int, source_type: str | None = None) -> list[dict[str, Any]]:
        clause = " AND source_type=%s" if source_type else ""
        params = (source_id, source_type) if source_type else (source_id,)
        cursor.execute(
            "SELECT warehouse_id,inventory_lot_id,quantity_delta FROM inventory_ledger WHERE source_id=%s" + clause + " ORDER BY line_no,id",
            params,
        )
        return [
            {**item, "quantity_delta": Decimal(str(item["quantity_delta"]))}
            for item in cursor.fetchall()
        ]
    def _correction_allocations(
        self,
        cursor: Any,
        row: dict[str, Any],
        original: list[dict[str, Any]],
        *,
        include_expired: bool = False,
    ) -> list[tuple[int, Decimal]]:
        remaining = amount(row.get("quantity"))
        allocations: list[tuple[int, Decimal]] = []
        for movement in original:
            if int(movement["warehouse_id"]) != int(row["warehouse_id"]) or movement["quantity_delta"] >= 0:
                continue
            used = min(remaining, -movement["quantity_delta"])
            if used:
                allocations.append((int(movement["inventory_lot_id"]), used)); remaining -= used
            if remaining == 0:
                return allocations
        if remaining:
            allocations.extend(allocate_fefo(
                self._lots(cursor, row), remaining,
                specified_lot_id=int(row["inventory_lot_id"]) if row.get("inventory_lot_id") else None,
                override_reason=str(row.get("override_reason") or "") or None,
                include_expired=include_expired,
            ))
        return allocations
    def _correction_movements(self, cursor: Any, resource: str, row: dict[str, Any]) -> list[dict[str, Any]]:
        if resource == "receipts":
            cursor.execute("SELECT * FROM warehouse_documents WHERE id=%s", (row["correction_of_id"],))
            parent = cursor.fetchone()
            if parent is None:
                raise DomainError("WAREHOUSE_CORRECTION_SOURCE_MISSING", "上次更正记录不存在", 409)
            original = build_movements(resource, parent)
        else:
            original = self._effective_movements(cursor, int(row["correction_of_id"]))
        if resource == "stocktakes":
            return build_movements(resource, row, book_quantity=self._book_quantity(cursor, row))
        allocations = self._correction_allocations(cursor, row, original, include_expired=resource == "scraps") if resource in {"issues", "transfers", "scraps"} else None
        desired = build_movements(resource, row, allocations=allocations)
        return movement_difference(desired, original)
    def _effective_movements(self, cursor: Any, source_id: int) -> list[dict[str, Any]]:
        cursor.execute("SELECT correction_of_id FROM warehouse_documents WHERE id=%s", (source_id,))
        parent_id = (cursor.fetchone() or {}).get("correction_of_id")
        current = self._ledger_movements(cursor, source_id)
        if not parent_id:
            return current
        return movement_difference(current + self._effective_movements(cursor, int(parent_id)), [])
    @staticmethod
    def _validate_negative(cursor: Any, row: dict[str, Any], movements: list[dict[str, Any]]) -> None:
        negative_lots = sorted({
            int(movement["inventory_lot_id"])
            for movement in movements
            if Decimal(str(movement["quantity_delta"])) < 0
        })
        for lot_id in negative_lots:
            cursor.execute("SELECT id FROM inventory_lots WHERE id=%s FOR UPDATE", (lot_id,))
            if cursor.fetchone() is None:
                raise DomainError("WAREHOUSE_LOT_NOT_FOUND", "库存批次不存在", 409)
        for movement in movements:
            quantity = Decimal(str(movement["quantity_delta"]))
            if quantity >= 0:
                continue
            cursor.execute(
                "SELECT COALESCE(SUM(quantity_delta),0) AS quantity FROM inventory_ledger WHERE warehouse_id=%s AND material_id=%s AND inventory_lot_id=%s FOR UPDATE",
                (movement["warehouse_id"], row["material_id"], movement["inventory_lot_id"]),
            )
            available = Decimal(str((cursor.fetchone() or {}).get("quantity", 0)))
            if -quantity > available:
                raise DomainError("WAREHOUSE_STOCK_INSUFFICIENT", "可用库存不足，禁止形成负库存", 409)
    @staticmethod
    def _insert(cursor: Any, resource: str, row: dict[str, Any], movements: list[dict[str, Any]], user_id: int, *, source_type: str | None = None) -> None:
        if not movements:
            return
        lot_ids = sorted({int(movement["inventory_lot_id"]) for movement in movements})
        cursor.execute(
            f"SELECT id,unit_cost FROM inventory_lots WHERE id IN ({','.join(['%s'] * len(lot_ids))})",
            tuple(lot_ids),
        )
        lot_costs = {int(item["id"]): Decimal(str(item["unit_cost"])) for item in cursor.fetchall()}
        start = 0
        if source_type == "correction":
            cursor.execute("SELECT COALESCE(MAX(line_no),0) AS line_no FROM inventory_ledger WHERE source_type='correction' AND source_id=%s", (row["id"],))
            start = int((cursor.fetchone() or {}).get("line_no", 0))
        kinds = {"receipts": "receipt", "issues": "issue", "returns": "return", "stocktakes": "stocktake", "scraps": "scrap"}
        values = []
        for offset, movement in enumerate(movements, 1):
            kind = source_type or (("transfer_out" if movement["quantity_delta"] < 0 else "transfer_in") if resource == "transfers" else kinds[resource])
            unit_cost = Decimal(str(row.get("unit_cost") or lot_costs.get(int(movement["inventory_lot_id"]), 0)))
            values.append((
                row["organization_id"], movement["warehouse_id"], row["material_id"], movement["inventory_lot_id"],
                kind, row["id"], start + offset, movement["quantity_delta"], unit_cost,
                row.get("pond_id"), row.get("batch_id"), row.get("happened_at"), user_id,
            ))
        cursor.executemany(
            "INSERT INTO inventory_ledger (organization_id,warehouse_id,material_id,inventory_lot_id,source_type,source_id,line_no,quantity_delta,unit_cost,pond_id,batch_id,happened_at,posted_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP),%s)",
            values,
        )
    def post(self, cursor: Any, resource: str, row: dict[str, Any], user_id: int) -> None:
        if resource == "issue-requests":
            return
        self.lock_business_anchors(cursor, resource, row)
        if resource == "returns":
            self._validate_return(cursor, row)
        if resource == "issues":
            self._validate_issue_request(cursor, row)
        if row.get("correction_of_id"):
            movements = self._correction_movements(cursor, resource, row)
            source_type = "correction"
        else:
            allocations = self._allocations(cursor, {**row, "_resource": resource}) if resource in {"issues", "scraps"} else None
            book = self._book_quantity(cursor, row) if resource == "stocktakes" else None
            movements = build_movements(resource, row, allocations=allocations, book_quantity=book)
            source_type = None
        self._validate_negative(cursor, row, movements)
        self._insert(cursor, resource, row, movements, user_id, source_type=source_type)
        if resource == "receipts":
            post_purchase_receipt(cursor, row)
    def post_transfer_dispatch(self, cursor: Any, row: dict[str, Any], user_id: int) -> None:
        self.lock_business_anchors(cursor, "transfers", row)
        if row.get("correction_of_id"):
            original = self._effective_movements(cursor, int(row["correction_of_id"]))
            allocations = self._correction_allocations(cursor, row, original)
            desired = [item for item in build_movements("transfers", row, allocations=allocations) if item["quantity_delta"] < 0]
            previous = [item for item in original if item["quantity_delta"] < 0]
            movements, source_type = movement_difference(desired, previous), "correction"
        else:
            movements = [item for item in build_movements("transfers", row, allocations=self._allocations(cursor, row)) if item["quantity_delta"] < 0]
            source_type = "transfer_out"
        self._validate_negative(cursor, row, movements)
        self._insert(cursor, "transfers", row, movements, user_id, source_type=source_type)
    def post_transfer_receive(self, cursor: Any, row: dict[str, Any], user_id: int) -> None:
        target = int(row["target_warehouse_id"]); received = amount(row.get("received_quantity"))
        cursor.execute("SELECT status FROM warehouses WHERE id=%s FOR UPDATE", (target,))
        target_row = cursor.fetchone()
        if target_row is None or target_row.get("status") != "active":
            raise DomainError("WAREHOUSE_TARGET_DISABLED", "停用仓库不能接收调拨库存", 409)
        if row.get("correction_of_id"):
            original = self._effective_movements(cursor, int(row["correction_of_id"]))
            dispatch_delta = self._ledger_movements(cursor, int(row["id"]), "correction")
            source = movement_difference(
                [item for item in original if int(item["warehouse_id"]) == int(row["warehouse_id"])],
                [{**item, "quantity_delta": -item["quantity_delta"]} for item in dispatch_delta if int(item["warehouse_id"]) == int(row["warehouse_id"])],
            )
            previous = [item for item in original if int(item["warehouse_id"]) == target and item["quantity_delta"] > 0]
            source_type = "correction"
        else:
            source = self._ledger_movements(cursor, int(row["id"]), "transfer_out")
            previous = []; source_type = "transfer_in"
        desired = []
        for item in source:
            available = max(Decimal("0"), -Decimal(str(item["quantity_delta"])))
            used = min(received, available)
            if used:
                desired.append({"warehouse_id": target, "inventory_lot_id": item["inventory_lot_id"], "quantity_delta": used}); received -= used
            if received == 0:
                break
        if received:
            raise DomainError("TRANSFER_RECEIPT_EXCEEDS_DISPATCH", "接收数量不能超过已发出数量", 409)
        movements = movement_difference(desired, previous)
        self._validate_negative(cursor, row, movements)
        self._insert(cursor, "transfers", row, movements, user_id, source_type=source_type)
    def post_transfer_cancel(self, cursor: Any, row: dict[str, Any], user_id: int) -> None:
        dispatch_type = "correction" if row.get("correction_of_id") else "transfer_out"
        dispatched = self._ledger_movements(cursor, int(row["id"]), dispatch_type)
        movements = [{**item, "quantity_delta": -item["quantity_delta"]} for item in dispatched]
        self._validate_negative(cursor, row, movements)
        self._insert(cursor, "transfers", row, movements, user_id, source_type="correction")
