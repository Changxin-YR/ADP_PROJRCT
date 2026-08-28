from __future__ import annotations

from datetime import datetime
from typing import Any
from backend.layers.common.security.data_scope import require_active_scope, scope_predicate, unrestricted


STATUS_LABELS = {
    "build": "筹建", "stocked": "已放养", "farming": "养殖中",
    "rest": "轮休", "clean": "清塘", "rebuild": "改造",
}
BATCH_LABELS = {"stocked": "已放养", "farming": "养殖中", "pending_settlement": "待结算", "closed": "已关闭"}


class WorkbenchRepository:
    @staticmethod
    def _scope(user: dict[str, Any], alias: str) -> tuple[str, list[Any]]:
        predicate, values = scope_predicate(user, alias)
        return predicate or "1=1", values

    def summary(self, connection: Any, *, user: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now()
        if "production.view" not in set(user.get("permissions") or []):
            return {
                "date_label": f"{now.year}年{now.month:02d}月{now.day:02d}日",
                "availability": {"production": False},
                "kpis": {"ponds": None, "active_batches": None, "current_stock": None, "todo_open": 0},
                "operating_metrics": {"feed_today": None, "payable_open": None, "receivable_open": None, "confirmed_cost": None},
                "pond_status": [], "todos": [], "alerts": [], "recent_batches": [],
            }
        pond_scope, pond_params = self._scope(user, "p")
        batch_scope, batch_params = self._scope(user, "pb")
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM ponds p WHERE p.status = 'verified' AND {pond_scope}", tuple(pond_params))
            pond_count = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(f"SELECT p.pond_status AS status, COUNT(*) AS count FROM ponds p WHERE p.status = 'verified' AND {pond_scope} GROUP BY p.pond_status", tuple(pond_params))
            pond_status = [{"status": row["status"], "label": STATUS_LABELS.get(row["status"], row["status"]), "count": int(row["count"])} for row in cursor.fetchall()]
            cursor.execute(f"SELECT COUNT(*) AS total FROM production_batches pb WHERE pb.status='verified' AND pb.batch_status IN ('stocked','farming') AND {batch_scope}", tuple(batch_params))
            active_batches = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(f"SELECT COALESCE(SUM(bsr.quantity_delta),0) AS total FROM batch_stock_records bsr INNER JOIN production_batches pb ON pb.id=bsr.batch_id WHERE pb.status='verified' AND {batch_scope}", tuple(batch_params))
            current_stock = float((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(
                f"""SELECT pb.id,pb.code AS batch_code,pb.name,pb.species,pb.batch_status AS status,
                           p.name AS pond_name,pb.pond_id,pb.initial_quantity,pb.stocked_at,pb.expected_harvest_date,pb.updated_at,
                           COALESCE((SELECT SUM(quantity_delta) FROM batch_stock_records WHERE batch_id=pb.id),0) AS current_stock
                    FROM production_batches pb INNER JOIN ponds p ON p.id=pb.pond_id
                    WHERE pb.status='verified' AND {batch_scope}
                    ORDER BY pb.updated_at DESC,pb.id DESC LIMIT 5""",
                tuple(batch_params),
            )
            batches = [self._batch(row) for row in cursor.fetchall()]
            organization_id = int(user.get("organization_id") or 0)
            cursor.execute("SELECT COUNT(*) AS total FROM production_documents pd WHERE pd.organization_id=%s AND pd.document_type IN ('feed_log','daily_operation') AND pd.status='verified' AND DATE(COALESCE(pd.happened_at,pd.created_at))=CURRENT_DATE()", (organization_id,))
            feed_today = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute("SELECT COALESCE(SUM(GREATEST(p.amount-p.paid_amount-COALESCE(a.adjusted,0),0)),0) AS total FROM purchase_payables p LEFT JOIN (SELECT payable_id,SUM(amount_delta) adjusted FROM purchase_payable_adjustments GROUP BY payable_id) a ON a.payable_id=p.id WHERE p.organization_id=%s AND p.status NOT IN ('cancelled','settled')", (organization_id,))
            payable_open = float((cursor.fetchone() or {}).get("total", 0))
            cursor.execute("SELECT COALESCE(SUM(GREATEST(r.amount-r.received_amount-COALESCE(a.adjusted,0),0)),0) AS total FROM sales_receivables r LEFT JOIN (SELECT receivable_id,SUM(amount_delta) adjusted FROM sales_receivable_adjustments GROUP BY receivable_id) a ON a.receivable_id=r.id WHERE r.organization_id=%s AND r.status NOT IN ('cancelled','settled')", (organization_id,))
            receivable_open = float((cursor.fetchone() or {}).get("total", 0))
            cursor.execute("SELECT COALESCE(SUM(amount),0) AS total FROM cost_entries WHERE organization_id=%s AND status='confirmed' AND MONTH(occurred_on)=MONTH(CURRENT_DATE()) AND YEAR(occurred_on)=YEAR(CURRENT_DATE())", (organization_id,))
            confirmed_cost = float((cursor.fetchone() or {}).get("total", 0))
        return {
            "date_label": f"{now.year}年{now.month:02d}月{now.day:02d}日",
            "availability": {"production": True},
            "kpis": {"ponds": pond_count, "active_batches": active_batches, "current_stock": current_stock, "todo_open": 0},
            "operating_metrics": {"feed_today": feed_today, "payable_open": payable_open, "receivable_open": receivable_open, "confirmed_cost": confirmed_cost},
            "pond_status": pond_status, "todos": [], "alerts": [], "recent_batches": batches,
        }

    @staticmethod
    def _batch(row: dict[str, Any]) -> dict[str, Any]:
        status = str(row["status"])
        return {
            "id": row["id"], "batch_code": row["batch_code"], "name": row["name"], "species": row["species"],
            "status": status, "status_label": BATCH_LABELS.get(status, status), "pond_names": [row["pond_name"]],
            "pond_ids": [row["pond_id"]], "stocked_at": row.get("stocked_at"),
            "expected_harvest_date": row.get("expected_harvest_date"), "initial_stock": float(row.get("initial_quantity") or 0),
            "current_stock": float(row.get("current_stock") or 0), "stock_unit": "尾", "updated_at": row.get("updated_at"),
        }
