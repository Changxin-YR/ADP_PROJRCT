from __future__ import annotations

import json

from backend.layers.common.audit.audit_logger import AuditLogger
from backend.layers.common.db.connection import get_connection
from backend.layers.common.db.repositories.cost_repository import CostRepository
from backend.layers.common.db.repositories.cost_dashboard_repository import CostDashboardRepository
from backend.layers.common.db.repositories.cost_expense_store import MySqlCostExpenseStore
from backend.layers.common.db.repositories.cost_allocation_store import MySqlCostAllocationStore
from backend.layers.common.db.repositories.cost_asset_store import MySqlCostAssetStore
from backend.layers.common.db.repositories.cost_settlement_store import MySqlCostSettlementStore


class MySqlCostStore:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.costs = CostRepository()
        self.dashboard = CostDashboardRepository()
        self.audit = AuditLogger()
        self.enterprise_stores = (MySqlCostExpenseStore(settings), MySqlCostAllocationStore(settings), MySqlCostAssetStore(settings), MySqlCostSettlementStore(settings))
        self._enterprise_methods = self._build_enterprise_methods(self.enterprise_stores)

    @staticmethod
    def _build_enterprise_methods(stores):
        methods = {}
        for store in stores:
            for name in dir(store):
                if name.startswith("_") or not callable(getattr(store, name)):
                    continue
                if name in methods:
                    raise RuntimeError(f"duplicate enterprise cost method: {name}")
                methods[name] = getattr(store, name)
        return methods

    def __getattr__(self, name):
        try:
            return self._enterprise_methods[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def list_category_totals(self, **kwargs):
        with get_connection(self.settings) as connection:
            rows = self.costs.list_category_totals(connection, **kwargs)
            warehouse = self.dashboard.warehouse_costs(connection, **kwargs)
            by_code = {row["code"]: row for row in rows}
            for fact in warehouse:
                row = by_code.get(fact["category_code"])
                if row is None:
                    continue
                amount = fact["amount"] or 0
                row["amount"] += amount
                row["direct_amount"] += amount if row["nature"] == "direct" else 0
                row["public_amount"] += amount if row["nature"] == "public" else 0
                row["confirmed_entry_count"] += int(fact["confirmed_entry_count"])
            return rows

    def get_dashboard_facts(self, **kwargs):
        with get_connection(self.settings) as connection:
            return self.dashboard.facts(connection, **kwargs)

    def list_entries(self, **kwargs):
        with get_connection(self.settings) as connection:
            if kwargs.get("status", "confirmed") == "confirmed":
                return self.dashboard.confirmed_entries(connection, **kwargs)
            return self.costs.list_entries(connection, **kwargs)

    def create_entry(self, *, user_id: int, request_id: str | None = None, ip_address: str | None = None, **payload):
        with get_connection(self.settings) as connection:
            result = self.costs.create_entry(connection, payload=payload, user_id=user_id)
            self.audit.write(connection, user_id=user_id, action="create_cost_entry", object_type="cost_entry", object_id=result.get("id"), object_ref=f"cost_entry:{result.get('id')}", result="success", ip_address=ip_address, request_id=request_id, module_code="cost", action_code="create_cost_entry", after=result)
            return result

    def update_draft(self, entry_id: int, *, user_id: int, request_id: str | None = None, ip_address: str | None = None, **payload):
        with get_connection(self.settings) as connection:
            before = self.costs.get_entry(connection, entry_id=entry_id, for_update=True)
            result = self.costs.update_draft(connection, entry_id=entry_id, payload=payload)
            self.audit.write(connection, user_id=user_id, action="update_cost_draft", object_type="cost_entry", object_id=entry_id, object_ref=f"cost_entry:{entry_id}", result="success", ip_address=ip_address, request_id=request_id, module_code="cost", action_code="update_cost_draft", before=before, after=result)
            return result

    def submit_entry(self, entry_id: int, *, user_id: int, request_id: str | None = None, ip_address: str | None = None):
        with get_connection(self.settings) as connection:
            before = self.costs.get_entry(connection, entry_id=entry_id, for_update=True)
            result = self.costs.submit_entry(connection, entry_id=entry_id)
            self.audit.write(connection, user_id=user_id, action="submit_cost_entry", object_type="cost_entry", object_id=entry_id, object_ref=f"cost_entry:{entry_id}", result="success", ip_address=ip_address, request_id=request_id, module_code="cost", action_code="submit_cost_entry", before=before, after=result)
            return result

    def confirm_entry(self, entry_id: int, *, user_id: int, request_id: str | None = None, ip_address: str | None = None):
        with get_connection(self.settings) as connection:
            before = self.costs.get_entry(connection, entry_id=entry_id, for_update=True)
            result = self.costs.confirm_entry(connection, entry_id=entry_id, user_id=user_id)
            self.audit.write(connection, user_id=user_id, action="confirm_cost_entry", object_type="cost_entry", object_id=entry_id, object_ref=f"cost_entry:{entry_id}", result="success", ip_address=ip_address, request_id=request_id, module_code="cost", action_code="confirm_cost_entry", before=before, after=result)
            return result

    def delete_draft(self, entry_id: int, *, user_id: int, request_id: str | None = None, ip_address: str | None = None):
        with get_connection(self.settings) as connection:
            before = self.costs.delete_draft(connection, entry_id=entry_id)
            self.audit.write(connection, user_id=user_id, action="delete_cost_draft", object_type="cost_entry", object_id=entry_id, object_ref=f"cost_entry:{entry_id}", result="success", ip_address=ip_address, request_id=request_id, module_code="cost", action_code="delete_cost_draft", before=before, reason="未正式录入草稿删除")
            return before

    def reverse_entry(self, entry_id: int, *, user_id: int, reason: str, request_id: str | None = None, ip_address: str | None = None):
        with get_connection(self.settings) as connection:
            before = self.costs.get_entry(connection, entry_id=entry_id, for_update=True)
            result = self.costs.reverse_entry(connection, entry_id=entry_id, user_id=user_id, reason=reason)
            self.audit.write(connection, user_id=user_id, action="reverse_cost_entry", object_type="cost_entry", object_id=entry_id, object_ref=f"cost_entry:{entry_id}", result="success", ip_address=ip_address, request_id=request_id, module_code="cost", action_code="reverse_cost_entry", before=before, after=result, reason=reason)
            return result

    def get_rule_version(self, **kwargs):
        with get_connection(self.settings) as connection:
            version = self.costs.get_rule_version(connection, **kwargs)
            if version:
                version["rules"] = self.costs.list_rule_items(connection, version_id=version["id"])
            return version

    def get_latest_rule_version(self):
        with get_connection(self.settings) as connection:
            version = self.costs.get_latest_rule_version(connection)
            if version:
                version["rules"] = self.costs.list_rule_items(connection, version_id=version["id"])
            return version

    def create_rule_version(self, *, user_id, ip_address, **kwargs):
        with get_connection(self.settings) as connection:
            creation = self.costs.create_rule_version(connection, created_by=user_id, **kwargs)
            version_id = int(creation["version_id"])
            previous_rules = (
                self.costs.list_rule_items(connection, version_id=int(creation["previous_version_id"]))
                if creation["previous_version_id"] is not None
                else []
            )
            new_rules = self.costs.list_rule_items(connection, version_id=version_id)
            previous_by_category = {int(item["category_id"]): item for item in previous_rules}
            rule_changes = []
            for item in new_rules:
                category_id = int(item["category_id"])
                previous = previous_by_category.get(category_id, {})
                before = (previous.get("driver"), previous.get("manual_ratio_json"))
                after = (item.get("driver"), item.get("manual_ratio_json"))
                if before != after:
                    rule_changes.append(
                        {
                            "category_id": category_id,
                            "from_driver": previous.get("driver"),
                            "to_driver": item.get("driver"),
                            "from_manual_ratio_json": previous.get("manual_ratio_json"),
                            "to_manual_ratio_json": item.get("manual_ratio_json"),
                        }
                    )
            audit_detail = {
                "previous_version": {
                    "id": creation["previous_version_id"],
                    "version_no": creation["previous_version_no"],
                },
                "new_version": {"id": version_id, "version_no": creation["version_no"]},
                "effective_from": kwargs["effective_from"],
                "change_reason": kwargs["change_reason"],
                "rules": kwargs["rules"],
                "rule_changes": rule_changes,
            }
            self.audit.write(
                connection,
                user_id=user_id,
                action="update_cost_allocation_rules",
                object_type="cost_allocation_rule_version",
                object_id=version_id,
                result="success",
                ip_address=ip_address,
                detail_json=json.dumps(audit_detail, ensure_ascii=False, default=str),
            )
            version = self.costs.get_rule_version(connection, effective_at=kwargs["effective_from"])
            if version:
                version["rules"] = new_rules
            return version
