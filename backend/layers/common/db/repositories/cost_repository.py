from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from backend.layers.common.db.repositories.cost_enterprise_repository import scope_clause


class CostRepository:
    def list_category_totals(self, connection: Any, *, period_start, period_end, user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        scope, scope_values = scope_clause(user, "ce") if user else ("", [])
        scoped_join = f"AND {scope}" if scope else ""
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.id, c.code, c.name, c.default_nature AS nature,
                       c.default_allocation_driver AS allocation_driver,
                       COALESCE(SUM(ce.amount), 0.00) AS amount,
                       COALESCE(SUM(CASE WHEN ce.cost_nature = 'direct' THEN ce.amount ELSE 0 END), 0.00) AS direct_amount,
                       COALESCE(SUM(CASE WHEN ce.cost_nature = 'public' THEN ce.amount ELSE 0 END), 0.00) AS public_amount,
                       COUNT(ce.id) AS confirmed_entry_count,
                       CASE WHEN SUM(CASE WHEN ce.source_type = 'legacy_import' THEN 1 ELSE 0 END) > 0
                            THEN 'legacy_import' ELSE 'verified' END AS source_quality
                FROM cost_categories c
                LEFT JOIN cost_entries ce ON ce.category_id = c.id
                  AND ce.status = 'confirmed'
                  AND ce.occurred_on BETWEEN %s AND %s
                  {scoped_join}
                WHERE c.status = 'active'
                GROUP BY c.id, c.code, c.name, c.default_nature, c.default_allocation_driver, c.sort_order
                ORDER BY c.sort_order, c.id
                """,
                (period_start, period_end, *scope_values),
            )
            return list(cursor.fetchall())

    def list_entries(self, connection: Any, *, category_code, period_start, period_end, page, page_size, status: str | None = "confirmed", user: dict[str, Any] | None = None) -> dict[str, Any]:
        where_parts = ["c.code = %s", "ce.occurred_on BETWEEN %s AND %s"]
        params_list: list[Any] = [category_code, period_start, period_end]
        if status == "confirmed":
            # 保持正式台账查询的显式语义，也避免把状态值误当作 SQL 参数以外的结构。
            where_parts.append("ce.status = 'confirmed'")
        elif status and status != "all":
            where_parts.append("ce.status = %s")
            params_list.append(status)
        scope, scope_values = scope_clause(user, "ce") if user else ("", [])
        if scope:
            where_parts.append(scope)
            params_list.extend(scope_values)
        where = " AND ".join(where_parts)
        params = tuple(params_list)
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM cost_entries ce INNER JOIN cost_categories c ON c.id = ce.category_id WHERE {where}",
                params,
            )
            total = int((cursor.fetchone() or {}).get("total", 0))
            cursor.execute(
                f"""
                SELECT ce.id, c.code AS category_code, c.name AS category_name, ce.amount,
                       ce.occurred_on, ce.period_start, ce.period_end, ce.status,
                       ce.source_type, ce.source_ref, ce.source_detail_json
                FROM cost_entries ce INNER JOIN cost_categories c ON c.id = ce.category_id
                WHERE {where}
                ORDER BY ce.occurred_on DESC, ce.id DESC
                LIMIT %s OFFSET %s
                """,
                (*params, page_size, (page - 1) * page_size),
            )
            items = list(cursor.fetchall())
        for item in items:
            if isinstance(item.get("source_detail_json"), str):
                item["source_detail_json"] = json.loads(item["source_detail_json"])
        return {"items": items, "page": page, "page_size": page_size, "total": total, "has_next": page * page_size < total}

    def get_entry(self, connection: Any, *, entry_id: int, for_update: bool = False) -> dict[str, Any] | None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ce.*, c.code AS category_code, c.name AS category_name
                FROM cost_entries AS ce
                INNER JOIN cost_categories AS c ON c.id = ce.category_id
                WHERE ce.id = %s
                """ + (" FOR UPDATE" if for_update else ""),
                (entry_id,),
            )
            row = cursor.fetchone()
        if row and isinstance(row.get("source_detail_json"), str):
            row["source_detail_json"] = json.loads(row["source_detail_json"])
        return row

    def create_entry(self, connection: Any, *, payload: dict[str, Any], user_id: int) -> dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, default_nature FROM cost_categories WHERE code = %s AND status = 'active'", (payload["category_code"],))
            category = cursor.fetchone()
            if category is None:
                raise ValueError("成本分类不存在")
            cursor.execute(
                """
                INSERT INTO cost_entries
                    (category_id, amount, occurred_on, period_start, period_end, status,
                     cost_nature, source_type, source_ref, source_detail_json, target_type,
                     target_id, created_by)
                VALUES (%s, %s, %s, %s, %s, 'draft', %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    category["id"], payload["amount"], payload["occurred_on"], payload["period_start"], payload["period_end"],
                    payload.get("cost_nature") or category["default_nature"], payload["source_type"], payload["source_ref"],
                    json.dumps(payload.get("source_detail"), ensure_ascii=False, default=str) if payload.get("source_detail") is not None else None,
                    payload.get("target_type"), payload.get("target_id"), user_id,
                ),
            )
            return dict(self.get_entry(connection, entry_id=int(cursor.lastrowid)) or {})

    def update_draft(self, connection: Any, *, entry_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        fields = ["amount", "occurred_on", "period_start", "period_end", "source_type", "source_ref", "source_detail_json", "target_type", "target_id"]
        values = [
            payload["amount"], payload["occurred_on"], payload["period_start"], payload["period_end"], payload["source_type"], payload["source_ref"],
            json.dumps(payload.get("source_detail"), ensure_ascii=False, default=str) if payload.get("source_detail") is not None else None,
            payload.get("target_type"), payload.get("target_id"), entry_id,
        ]
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE cost_entries SET amount=%s, occurred_on=%s, period_start=%s, period_end=%s, source_type=%s, source_ref=%s, source_detail_json=%s, target_type=%s, target_id=%s WHERE id=%s AND status='draft'",
                tuple(values),
            )
            if cursor.rowcount != 1:
                raise ValueError("只有草稿成本才可以编辑")
        return dict(self.get_entry(connection, entry_id=entry_id) or {})

    def submit_entry(self, connection: Any, *, entry_id: int) -> dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE cost_entries SET status='pending' WHERE id=%s AND status='draft'", (entry_id,))
            if cursor.rowcount != 1:
                raise ValueError("只有草稿成本才可以提交核验")
        return dict(self.get_entry(connection, entry_id=entry_id) or {})

    def confirm_entry(self, connection: Any, *, entry_id: int, user_id: int) -> dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT created_by, status FROM cost_entries WHERE id = %s FOR UPDATE", (entry_id,))
            current = cursor.fetchone()
            if current is None:
                raise ValueError("成本台账不存在")
            if current.get("created_by") == user_id:
                raise ValueError("提交人不能核验自己提交的成本")
            cursor.execute("UPDATE cost_entries SET status='confirmed', confirmed_by=%s, confirmed_at=CURRENT_TIMESTAMP WHERE id=%s AND status='pending'", (user_id, entry_id))
            if cursor.rowcount != 1:
                raise ValueError("只有待核验成本才可以完成核验")
        return dict(self.get_entry(connection, entry_id=entry_id) or {})

    def delete_draft(self, connection: Any, *, entry_id: int) -> dict[str, Any]:
        before = self.get_entry(connection, entry_id=entry_id, for_update=True)
        if before is None:
            raise ValueError("成本台账不存在")
        if before.get("status") != "draft":
            raise ValueError("只有未正式录入的草稿成本可以删除")
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM cost_entries WHERE id=%s AND status='draft'", (entry_id,))
            if cursor.rowcount != 1:
                raise ValueError("草稿成本删除失败")
        return dict(before)

    def reverse_entry(self, connection: Any, *, entry_id: int, user_id: int, reason: str) -> dict[str, Any]:
        original = self.get_entry(connection, entry_id=entry_id, for_update=True)
        if original is None:
            raise ValueError("成本台账不存在")
        if original.get("status") != "confirmed":
            raise ValueError("只有已核验成本才可以冲销")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cost_entries
                    (category_id, amount, occurred_on, period_start, period_end, status,
                     cost_nature, source_type, source_ref, source_detail_json, target_type,
                     target_id, reversal_of_id, created_by, confirmed_by, confirmed_at)
                VALUES (%s, %s, %s, %s, %s, 'confirmed', %s, 'reversal', %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    original["category_id"], -abs(original["amount"]), original["occurred_on"], original["period_start"], original["period_end"],
                    original["cost_nature"], f"REV-{entry_id}-{user_id}", json.dumps({"reason": reason, "reversed_entry_id": entry_id}, ensure_ascii=False),
                    original.get("target_type"), original.get("target_id"), entry_id, user_id, user_id,
                ),
            )
            return dict(self.get_entry(connection, entry_id=int(cursor.lastrowid)) or {})

    def get_rule_version(self, connection: Any, *, effective_at) -> dict[str, Any] | None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT v.id, v.version_no, v.effective_from, v.effective_to, v.status,
                       v.change_reason, u.name AS created_by_name
                FROM cost_allocation_rule_versions v
                LEFT JOIN users u ON u.id = v.created_by
                WHERE v.status IN ('active','retired') AND v.effective_from <= %s
                  AND (v.effective_to IS NULL OR v.effective_to >= %s)
                ORDER BY v.effective_from DESC, v.version_no DESC LIMIT 1
                """,
                (effective_at, effective_at),
            )
            return cursor.fetchone()

    def get_latest_rule_version(self, connection: Any) -> dict[str, Any] | None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT v.id, v.version_no, v.effective_from, v.effective_to, v.status,
                       v.change_reason, u.name AS created_by_name
                FROM cost_allocation_rule_versions v
                LEFT JOIN users u ON u.id = v.created_by
                WHERE v.status IN ('active','retired')
                ORDER BY v.version_no DESC LIMIT 1
                """
            )
            return cursor.fetchone()

    def list_rule_items(self, connection: Any, *, version_id) -> list[dict[str, Any]]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.category_id, c.code AS category_code, c.name AS category_name,
                       r.driver, r.fallback_driver, r.manual_ratio_json
                FROM cost_allocation_rules r
                INNER JOIN cost_categories c ON c.id = r.category_id
                WHERE r.version_id = %s ORDER BY c.sort_order, c.id
                """,
                (version_id,),
            )
            rows = list(cursor.fetchall())
        for row in rows:
            if isinstance(row.get("manual_ratio_json"), str):
                row["manual_ratio_json"] = json.loads(row["manual_ratio_json"])
        return rows

    def create_rule_version(self, connection: Any, *, effective_from, change_reason, created_by, rules) -> dict[str, int | None]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM cost_categories WHERE status = 'active' ORDER BY id FOR UPDATE")
            active_category_ids = {int(item["id"]) for item in cursor.fetchall()}
            requested_category_ids = {int(item["category_id"]) for item in rules}
            if not active_category_ids or requested_category_ids != active_category_ids or len(rules) != len(active_category_ids):
                raise ValueError("RULE_CATEGORY_SET_MISMATCH")
            cursor.execute(
                "SELECT id, version_no, effective_from, status FROM cost_allocation_rule_versions ORDER BY version_no FOR UPDATE"
            )
            versions = list(cursor.fetchall())
            if any(item.get("effective_from") == effective_from for item in versions):
                raise ValueError("RULE_EFFECTIVE_DATE_CONFLICT")
            existing_dates = [item["effective_from"] for item in versions if item.get("effective_from") is not None]
            if existing_dates and effective_from <= max(existing_dates):
                raise ValueError("RULE_EFFECTIVE_DATE_CONFLICT")
            next_version = max((int(item.get("version_no", 0)) for item in versions), default=0) + 1
            previous = max(versions, key=lambda item: int(item.get("version_no", 0)), default=None)
            cursor.execute(
                "UPDATE cost_allocation_rule_versions SET status = 'retired', effective_to = %s WHERE status = 'active' AND effective_from < %s",
                (effective_from - timedelta(days=1), effective_from),
            )
            cursor.execute(
                "INSERT INTO cost_allocation_rule_versions (version_no, effective_from, status, change_reason, created_by) VALUES (%s, %s, 'active', %s, %s)",
                (next_version, effective_from, change_reason, created_by),
            )
            version_id = int(cursor.lastrowid)
            cursor.executemany(
                "INSERT INTO cost_allocation_rules (version_id, category_id, driver, fallback_driver, manual_ratio_json) VALUES (%s, %s, %s, 'equal', %s)",
                [
                    (
                        version_id,
                        int(item["category_id"]),
                        item["driver"],
                        json.dumps(item.get("manual_ratio_json"), ensure_ascii=False) if item.get("manual_ratio_json") is not None else None,
                    )
                    for item in rules
                ],
            )
            return {
                "version_id": version_id,
                "version_no": next_version,
                "previous_version_id": int(previous["id"]) if previous else None,
                "previous_version_no": int(previous["version_no"]) if previous else None,
            }
