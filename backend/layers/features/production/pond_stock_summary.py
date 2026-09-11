"""塘口存塘量只读汇总（D1）：把生产事实聚合为「塘口级」视图。

口径：数量 = SUM(batch_stock_records.quantity_delta)（尾/只），重量 = SUM(weight_delta_kg)（kg）；
事实由生产核验写入且该表 append-only；抽样取已核验 sampling 中 COALESCE(happened_at, created_at) 最新一条。
ponds.stock_quantity / current_spec 只读展示、不写回，无批次流水时作为兜底（data_source='manual'）。
拆分说明：本模块从 production_store.py / production_service.py 抽出，兼顾 300 行门禁与口径集中。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.common.db.connection import get_connection
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.security.data_scope import row_in_scope, scope_predicate

POND_IDS_ERROR = ("POND_IDS_INVALID", "pond_ids 必须是正整数列表")


class PondStockSummaryQueries:
    """MySqlProductionStore 的只读查询 mixin：3 条聚合查询覆盖多口塘，避免逐塘 N+1。"""

    SUMMARIZABLE_POND_STATUS = ("draft", "submitted", "verified")
    POND_SUMMARY_COLUMNS = ("p.id AS pond_id,p.code AS pond_code,p.name AS pond_name,p.status AS pond_status,"
                            "p.stock_quantity AS manual_stock_quantity,p.current_spec AS manual_current_spec")

    @staticmethod
    def _pond_ids(values: Any) -> list[int]:
        result: set[int] = set()
        for value in values:
            try:
                pond_id = int(str(value).strip())
            except (TypeError, ValueError) as exc:
                raise DomainError(*POND_IDS_ERROR, 400) from exc
            if pond_id < 1:
                raise DomainError(*POND_IDS_ERROR, 400)
            result.add(pond_id)
        return sorted(result)

    @staticmethod
    def parse_pond_ids(values: Any) -> list[int]:
        """解析 pond_ids（逗号分隔或列表），非法取值 → 400 POND_IDS_INVALID。"""
        if values in (None, ""):
            return []
        raw = str(values).split(",") if isinstance(values, str) else list(values)
        return PondStockSummaryQueries._pond_ids(raw)

    @staticmethod
    def _scope_sql(user: dict[str, Any], alias: str) -> tuple[str, list[Any]]:
        predicate, values = scope_predicate(user, alias)
        return ((f" AND {predicate}" if predicate else ""), list(values))

    @staticmethod
    def _quantize3(value: Any) -> Decimal:
        """与 DECIMAL(18,3) 同口径：真实库里 SUM() 的结果带 3 位小数。"""
        try:
            return Decimal(str(value if value not in (None, "") else 0)).quantize(Decimal("0.001"))
        except (InvalidOperation, ValueError):
            return Decimal("0.000")
    @staticmethod
    def _aggregate_pond_stock(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        aggregates: dict[int, dict[str, Any]] = {}
        for row in rows:
            pond_id = int(row["pond_id"])
            aggregate = aggregates.setdefault(pond_id, {"ledger": {"quantity": Decimal("0.000"), "weight_kg": Decimal("0.000")},
                                                         "stock_record_count": 0, "batch_count": 0, "latest_sampling": None})
            if row.get("row_kind") == "stock":
                aggregate["stock_record_count"] += 1
                aggregate["ledger"]["quantity"] = PondStockSummaryQueries._quantize3(
                    aggregate["ledger"]["quantity"] + Decimal(str(row.get("quantity_delta") or 0))
                )
                aggregate["ledger"]["weight_kg"] = PondStockSummaryQueries._quantize3(
                    aggregate["ledger"]["weight_kg"] + Decimal(str(row.get("weight_delta_kg") or 0))
                )
            elif row.get("row_kind") == "batch":
                aggregate["batch_count"] += 1
            elif row.get("row_kind") == "sampling":
                occurred_at = row.get("happened_at") or row.get("created_at")
                document_id = int(row["document_id"])
                current = aggregate["latest_sampling"]
                if current is None or (str(occurred_at), document_id) > (str(current[0]), int(current[1]["document_id"])):
                    aggregate["latest_sampling"] = (occurred_at, {"document_id": document_id, "occurred_at": occurred_at})
        return aggregates

    def list_pond_stock_summary_rows(self, pond_ids: list[int], *, user: dict[str, Any]) -> list[dict[str, Any]]:
        """批量取流水/批次/抽样事实行。数据范围由调用方先按 ponds.area_id/farm_id 校验。"""
        targets = self._pond_ids(pond_ids)
        if not targets:
            return []
        placeholders, rows = ",".join(["%s"] * len(targets)), []

        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT a.pond_id,'stock' AS row_kind,a.quantity_delta,a.weight_delta_kg,NULL AS batch_id,NULL AS document_id,NULL AS happened_at,NULL AS created_at " f"FROM batch_stock_records a WHERE a.pond_id IN ({placeholders}) ORDER BY a.pond_id,a.id",
                tuple(targets),
            )
            rows.extend(cursor.fetchall())
            cursor.execute(
                "SELECT a.pond_id,'batch' AS row_kind,NULL AS quantity_delta,NULL AS weight_delta_kg,a.batch_id,NULL AS document_id,NULL AS happened_at,NULL AS created_at " f"FROM batch_stock_records a WHERE a.pond_id IN ({placeholders}) GROUP BY a.pond_id,a.batch_id ORDER BY a.pond_id,a.batch_id",
                tuple(targets),
            )
            rows.extend(cursor.fetchall())
            cursor.execute(
                "SELECT d.pond_id,'sampling' AS row_kind,NULL AS quantity_delta,NULL AS weight_delta_kg,NULL AS batch_id,d.id AS document_id," "COALESCE(d.happened_at,d.created_at) AS happened_at,d.created_at " f"FROM production_documents d WHERE d.pond_id IN ({placeholders}) AND d.document_type='sampling' AND d.status='verified' " "ORDER BY d.pond_id,COALESCE(d.happened_at,d.created_at),d.id",
                tuple(targets),
            )
            rows.extend(cursor.fetchall())
        return rows

    def _pond_rows(self, user: dict[str, Any], *, page: int = 1, page_size: int = 50, pond_ids: list[int] | None = None) -> dict[str, Any]:
        statuses, scope, scope_values = ",".join(["%s"] * len(self.SUMMARIZABLE_POND_STATUS)), *self._scope_sql(user, "p")
        if pond_ids:
            placeholders = ",".join(["%s"] * len(pond_ids))
            where, order, limit = f"WHERE p.status IN ({statuses}){scope} AND p.id IN ({placeholders})", "ORDER BY p.id", ""
            values = tuple([*self.SUMMARIZABLE_POND_STATUS, *scope_values, *pond_ids])
        else:
            page, page_size = max(1, int(page)), min(100, max(1, int(page_size)))
            where, values = f"WHERE p.status IN ({statuses}){scope}", tuple([*self.SUMMARIZABLE_POND_STATUS, *scope_values])
            order, limit = "ORDER BY p.updated_at DESC,p.id DESC", f" LIMIT {page_size} OFFSET {(page - 1) * page_size}"
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT {self.POND_SUMMARY_COLUMNS} FROM ponds p {where} {order}{limit}", values)
            ponds = list(cursor.fetchall())
            if pond_ids:
                total, has_next = len(ponds), False
            else:
                cursor.execute(f"SELECT COUNT(*) AS total FROM ponds p {where}", values)
                total = int((cursor.fetchone() or {}).get("total", 0))
                has_next = page * page_size < total
        return {"ponds": ponds, "page": page, "page_size": page_size, "total": total, "has_next": has_next}

    def list_pond_stock_summary(self, *, user: dict[str, Any], page: int = 1, page_size: int = 50, pond_ids: list[int] | None = None) -> dict[str, Any]:
        """返回 {ponds, rows, page, page_size, total, has_next}；rows 供上层聚合，避免逐塘查询。"""
        targets = self._pond_ids(pond_ids or [])
        page_result = self._pond_rows(user, page=page, page_size=page_size, pond_ids=targets or None)
        return {**page_result, "rows": self.list_pond_stock_summary_rows([int(row["pond_id"]) for row in page_result["ponds"]], user=user)}

    def get_pond_stock_summary(self, pond_id: int, *, user: dict[str, Any]) -> dict[str, Any] | None:
        """单塘入口：塘口不存在/已归档返回 None（服务层转 404）；存在但越权直接 403。"""
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ponds WHERE id=%s", (int(pond_id),))
            pond = cursor.fetchone()
        if pond is None or pond.get("status") not in self.SUMMARIZABLE_POND_STATUS:
            return None
        if not row_in_scope(user, pond):
            raise DomainError("DATA_SCOPE_FORBIDDEN", "无权访问授权范围之外的塘口存塘量", 403)
        page_result = self._pond_rows(user, pond_ids=[int(pond_id)])
        rows = self.list_pond_stock_summary_rows([int(pond_id)], user=user)
        return {**page_result, "rows": rows, "page": 1, "page_size": 1, "total": 1, "has_next": False}

    def list_pond_batches(self, pond_id: int) -> list[dict[str, Any]]:
        """该塘口每个批次按流水累计的存量明细（一次 GROUP BY，不逐批次查询）。"""
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT b.id AS batch_id,b.code,b.name,b.batch_status,b.species," "COALESCE(SUM(a.quantity_delta),0) AS quantity,COALESCE(SUM(a.weight_delta_kg),0) AS weight_kg,COUNT(a.id) AS stock_record_count " "FROM batch_stock_records a JOIN production_batches b ON b.id=a.batch_id WHERE a.pond_id=%s " "GROUP BY b.id,b.code,b.name,b.batch_status,b.species ORDER BY b.id",
                (int(pond_id),),
            )
            return list(cursor.fetchall())

    def get_latest_verified_sampling(self, pond_id: int) -> dict[str, Any] | None:
        """该塘口最近一次已核验抽样：COALESCE(happened_at,created_at) 降序取首条。"""
        with get_connection(self.settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT d.id AS document_id,COALESCE(d.happened_at,d.created_at) AS occurred_at,d.quantity,d.weight_kg,d.batch_id,d.code,d.name " "FROM production_documents d WHERE d.pond_id=%s AND d.document_type='sampling' AND d.status='verified' " "ORDER BY COALESCE(d.happened_at,d.created_at) DESC,d.id DESC LIMIT 1",
                (int(pond_id),),
            )
            return cursor.fetchone()


class PondStockSummaryService:
    """ProductionService 的只读汇总 mixin：权限沿用 ProductionService.require。"""

    @staticmethod
    def _quantity_text(value: Any) -> str:
        """数值统一按 DECIMAL(18,3) 口径输出为字符串（与 Flask 对 Decimal 的序列化一致）。"""
        try:
            return str(Decimal(str(value if value not in (None, "") else 0)).quantize(Decimal("0.001")))
        except (InvalidOperation, ValueError):
            return "0.000"

    @staticmethod
    def _average_weight(weight_kg: Any, quantity: Any) -> str | None:
        """折算平均体重 = 样本重量 / 样本数量；数量为 0 返回 None（不编造数字）。"""
        try:
            divisor = Decimal(str(quantity if quantity not in (None, "") else 0))
            if divisor == 0:
                return None
            return str((Decimal(str(weight_kg if weight_kg not in (None, "") else 0)) / divisor).quantize(Decimal("0.001")))
        except (InvalidOperation, ValueError):
            return None

    @classmethod
    def _ledger_payload(cls, aggregate: dict[str, Any]) -> dict[str, str]:
        ledger = aggregate.get("ledger") or {}
        return {"quantity": cls._quantity_text(ledger.get("quantity")), "weight_kg": cls._quantity_text(ledger.get("weight_kg"))}

    @classmethod
    def _manual_payload(cls, pond: dict[str, Any]) -> dict[str, Any]:
        """档案手工值：只读展示，绝不回写；无值时为 null，不编造 0。"""
        manual = pond.get("manual_stock_quantity")
        return {"quantity": None if manual in (None, "") else cls._quantity_text(manual), "current_spec": pond.get("manual_current_spec") or None}

    @classmethod
    def _data_source(cls, stock_record_count: int, manual_quantity: Any) -> str:
        if int(stock_record_count or 0) > 0:
            return "batch_ledger"
        if manual_quantity not in (None, ""):
            return "manual"
        return "none"

    @classmethod
    def _batches(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        batches = []
        for row in rows:
            quantity = cls._quantity_text(row.get("quantity"))
            weight_kg = cls._quantity_text(row.get("weight_kg"))
            batches.append({**{key: row.get(key) for key in ("code", "name", "species", "batch_status")},
                            "batch_id": int(row["batch_id"]), "quantity": quantity, "weight_kg": weight_kg,
                            "avg_weight_kg": cls._average_weight(weight_kg, quantity)})
        return batches

    @classmethod
    def _sampling(cls, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        quantity = cls._quantity_text(row.get("quantity"))
        weight_kg = cls._quantity_text(row.get("weight_kg"))
        return {
            "document_id": int(row["document_id"]),
            "occurred_at": row.get("occurred_at"),
            "quantity": quantity,
            "weight_kg": weight_kg,
            "avg_weight_kg": cls._average_weight(weight_kg, quantity),
            "batch_id": int(row["batch_id"]) if row.get("batch_id") not in (None, "") else None,
            "code": row.get("code"),
        }

    @classmethod
    def _sampling_latest(cls, aggregate: dict[str, Any]) -> dict[str, Any] | None:
        """列表页只带抽样时间：聚合里的 latest_sampling 是 (occurred_at, {document_id, occurred_at})。"""
        latest = aggregate.get("latest_sampling")
        if not latest:
            return None
        _, sampling = latest
        return {"document_id": int(sampling["document_id"]), "occurred_at": sampling.get("occurred_at")}

    def pond_stock_summary(self, user: dict[str, Any], pond_id: int) -> dict[str, Any]:
        self.require(user, "ponds", "view")
        result = self.store.get_pond_stock_summary(int(pond_id), user=user)
        if not result or not result.get("ponds"):
            raise DomainError("POND_NOT_FOUND", "塘口不存在或不在授权范围内", 404)
        pond = result["ponds"][0]
        aggregate = self.store._aggregate_pond_stock(result.get("rows") or []).get(int(pond_id)) or {}
        return {
            "pond_id": int(pond["pond_id"]),
            "pond_code": pond.get("pond_code"),
            "pond_name": pond.get("pond_name"),
            "batch_stock": self._ledger_payload(aggregate),
            "manual_stock": self._manual_payload(pond),
            "batches": self._batches(self.store.list_pond_batches(int(pond_id))),
            "latest_sampling": self._sampling(self.store.get_latest_verified_sampling(int(pond_id))),
            "data_source": self._data_source(int(aggregate.get("stock_record_count") or 0), (pond.get("manual_stock_quantity") or None)),
        }

    def list_pond_stock_summaries(self, user: dict[str, Any], *, page: int = 1, page_size: int = 50, pond_ids: Any = None) -> dict[str, Any]:
        self.require(user, "ponds", "view")
        targets = self.store.parse_pond_ids(pond_ids or [])
        result = self.store.list_pond_stock_summary(user=user, page=page, page_size=page_size, pond_ids=targets or None)
        aggregates = self.store._aggregate_pond_stock(result.get("rows") or [])
        items = []
        for pond in result["ponds"]:
            pond_id = int(pond["pond_id"])
            aggregate = aggregates.get(pond_id) or {}
            manual_quantity = pond.get("manual_stock_quantity")
            items.append({
                "pond_id": pond_id,
                "pond_code": pond.get("pond_code"),
                "pond_name": pond.get("pond_name"),
                "pond_status": pond.get("pond_status"),
                "batch_stock": self._ledger_payload(aggregate),
                "manual_stock": {
                    "quantity": None if manual_quantity in (None, "") else self._quantity_text(manual_quantity),
                    "current_spec": pond.get("manual_current_spec") or None,
                },
                "batch_count": int(aggregate.get("batch_count") or 0),
                "latest_sampling": self._sampling_latest(aggregate),
                "data_source": self._data_source(int(aggregate.get("stock_record_count") or 0), manual_quantity),
            })
        return {
            "items": items,
            "page": int(result.get("page") or page),
            "page_size": int(result.get("page_size") or page_size),
            "total": int(result.get("total") or len(items)),
            "has_next": bool(result.get("has_next")),
            "source": "production_facts",
        }
