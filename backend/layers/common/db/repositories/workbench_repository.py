from __future__ import annotations

from datetime import datetime
from typing import Any
from backend.layers.common.security.data_scope import require_active_scope, unrestricted


STATUS_LABELS = {
    "build": "筹建", "stocked": "已放养", "farming": "养殖中",
    "rest": "轮休", "clean": "清塘", "rebuild": "改造",
}
BATCH_LABELS = {"stocked": "已放养", "farming": "养殖中", "pending_settlement": "待结算", "closed": "已关闭"}


class WorkbenchRepository:
    @staticmethod
    def _scope(user: dict[str, Any], alias: str) -> tuple[str, list[Any]]:
        scopes = require_active_scope(user)
        if unrestricted(user):
            return "1=1", []
        areas = sorted({int(item["area_id"]) for item in scopes if item.get("scope_type") == "area" and item.get("area_id")})
        if areas:
            return f"{alias}.area_id IN ({','.join(['%s'] * len(areas))})", areas
        if any(item.get("scope_type") == "personal" for item in scopes):
            return f"{alias}.created_by = %s", [int(user["id"])]
        return "1=0", []

    def summary(self, connection: Any, *, user: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now()
        if "production.view" not in set(user.get("permissions") or []):
            return {
                "date_label": f"{now.year}年{now.month:02d}月{now.day:02d}日",
                "availability": {"production": False},
                "kpis": {"ponds": None, "active_batches": None, "current_stock": None, "todo_open": 0},
                "pond_status": [], "todos": [], "alerts": [], "recent_batches": [],
            }
        pond_scope, pond_params = self._scope(user, "p")
        batch_scope, batch_params = self._scope(user, "pb")
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM ponds p WHERE p.status <> 'archived' AND {pond_scope}", tuple(pond_params))
            pond_count = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(f"SELECT p.pond_status AS status, COUNT(*) AS count FROM ponds p WHERE p.status <> 'archived' AND {pond_scope} GROUP BY p.pond_status", tuple(pond_params))
            pond_status = [{"status": row["status"], "label": STATUS_LABELS.get(row["status"], row["status"]), "count": int(row["count"])} for row in cursor.fetchall()]
            cursor.execute(f"SELECT COUNT(*) AS total FROM production_batches pb WHERE pb.status='verified' AND pb.batch_status IN ('stocked','farming') AND {batch_scope}", tuple(batch_params))
            active_batches = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(f"SELECT COALESCE(SUM(bsr.quantity_delta),0) AS total FROM batch_stock_records bsr INNER JOIN production_batches pb ON pb.id=bsr.batch_id WHERE pb.status='verified' AND {batch_scope}", tuple(batch_params))
            current_stock = float((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(
                f"""SELECT pb.id,pb.code AS batch_code,pb.name,pb.species,pb.batch_status AS status,
                           p.name AS pond_name,pb.pond_id,pb.stocked_at,pb.expected_harvest_date,pb.updated_at,
                           COALESCE((SELECT SUM(quantity_delta) FROM batch_stock_records WHERE batch_id=pb.id),0) AS current_stock
                    FROM production_batches pb INNER JOIN ponds p ON p.id=pb.pond_id
                    WHERE pb.status='verified' AND {batch_scope}
                    ORDER BY pb.updated_at DESC,pb.id DESC LIMIT 5""",
                tuple(batch_params),
            )
            batches = [self._batch(row) for row in cursor.fetchall()]
        return {
            "date_label": f"{now.year}年{now.month:02d}月{now.day:02d}日",
            "availability": {"production": True},
            "kpis": {"ponds": pond_count, "active_batches": active_batches, "current_stock": current_stock, "todo_open": 0},
            "pond_status": pond_status, "todos": [], "alerts": [], "recent_batches": batches,
        }

    @staticmethod
    def _batch(row: dict[str, Any]) -> dict[str, Any]:
        status = str(row["status"])
        return {
            "id": row["id"], "batch_code": row["batch_code"], "name": row["name"], "species": row["species"],
            "status": status, "status_label": BATCH_LABELS.get(status, status), "pond_names": [row["pond_name"]],
            "pond_ids": [row["pond_id"]], "stocked_at": row.get("stocked_at"),
            "expected_harvest_date": row.get("expected_harvest_date"), "initial_stock": 0,
            "current_stock": float(row.get("current_stock") or 0), "stock_unit": "尾", "updated_at": row.get("updated_at"),
        }
