"""导入器注册表：template_code -> 草稿写入实现。

设计约定（三层架构内的数据交换数据访问）：
- 每个 importer 只负责把一行「已通过预览校验」的数据写入对应业务表并形成
  status='draft' 的草稿记录，返回 (entity_type, entity_id) 供
  data_import_items 记账，供撤销（revoke）时定位删除。
- importer 使用确认事务的同一个 cursor，保证整批要么全部写入、要么全部回滚。
- 预览阶段（preview）的业务校验集中在 import_validation.validate_rows。
- inventory-ledger 为系统只追加账本，不在可导入范围内（importable=False），
  preview 入口先行拒绝。
- stocking（投苗记录）形成原批次的可撤销更正草稿，核验后才追加存塘流水。
"""

from __future__ import annotations

from typing import Any, Callable

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.data_exchange.import_refs import (
    _batch,
    _date,
    _decimal,
    _fetch,
    _first_warehouse,
    _int,
    _pond,
    _text,
    _warehouse,
    enforce_area_scope,
    scoped_area_defaults,
)
from backend.layers.features.data_exchange.importers_finance import (
    import_asset,
    import_cost_adjustment,
    import_customer_receipt,
    import_expense,
    import_payment,
    import_purchase_order,
    import_sales_order,
)

Importer = Callable[..., tuple[str, int]]


def _import_master(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int, table: str, entity_type: str, extra: dict[str, Any] | None = None) -> tuple[str, int]:
    scope = scoped_area_defaults(cursor, user, organization_id)
    columns = ["organization_id", "code", "name", *scope] + list((extra or {}).keys())
    values: list[Any] = [organization_id, row["code"], row["name"], *scope.values()] + list((extra or {}).values())
    cursor.execute(f"INSERT INTO {table} ({','.join(columns)},status,row_version,created_by) VALUES ({','.join(['%s'] * len(values))},'draft',1,%s)", (*values, user_id))
    return entity_type, int(cursor.lastrowid)


def _import_ponds(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int) -> tuple[str, int]:
    farm = _fetch(cursor, "SELECT organization_id FROM farms WHERE id=%s", (_int(row["farm_id"]),))
    if farm is None or int(farm["organization_id"]) != organization_id:
        raise DomainError("FARM_NOT_FOUND", "基地不存在或不属于当前企业", 400)
    area = _fetch(cursor, "SELECT organization_id,farm_id FROM areas WHERE id=%s", (_int(row["area_id"]),))
    if area is None or int(area["organization_id"]) != organization_id:
        raise DomainError("AREA_NOT_FOUND", "区域不存在或不属于当前企业", 400)
    if int(area["farm_id"]) != int(row["farm_id"]):
        raise DomainError("AREA_FARM_INVALID", "区域不属于所选基地", 400)
    enforce_area_scope(user, int(row["area_id"]))
    cursor.execute(
        "INSERT INTO ponds (organization_id,farm_id,area_id,code,name,capacity_mu,species,status,row_version,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,'draft',1,%s)",
        (organization_id, row["farm_id"], row["area_id"], row["code"], row["name"], row.get("capacity_mu") or 0, row.get("species"), user_id),
    )
    return "master:ponds", int(cursor.lastrowid)


def _import_batches(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int) -> tuple[str, int]:
    pond = _pond(cursor, organization_id, _int(row.get("pond_id")))
    enforce_area_scope(user, int(pond["area_id"]))
    cursor.execute(
        "INSERT INTO production_batches (organization_id,farm_id,area_id,pond_id,code,name,species,initial_quantity,stocked_at,batch_status,status,row_version,created_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'stocked','draft',1,%s)",
        (organization_id, pond["farm_id"], pond["area_id"], row["pond_id"], row["code"], _text(row.get("name")) or str(row["code"]), row["species"], row.get("quantity") or 0, row.get("happened_at"), user_id),
    )
    return "production:batches", int(cursor.lastrowid)


def _import_stocking(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int) -> tuple[str, int]:
    batch = _fetch(cursor, "SELECT * FROM production_batches WHERE id=%s AND organization_id=%s FOR UPDATE", (_int(row.get("batch_id")), organization_id))
    if batch is None:
        raise DomainError("BATCH_NOT_FOUND", "批次不存在或不属于当前企业", 400)
    if batch["status"] != "verified":
        raise DomainError("STOCKING_BATCH_NOT_VERIFIED", "投苗导入只能关联已核验批次", 409)
    enforce_area_scope(user, int(batch["area_id"]))
    happened = row.get("happened_at") or date.today().isoformat()
    quantity = _decimal(batch.get("initial_quantity")) + _decimal(row.get("quantity"))
    cursor.execute(
        "INSERT INTO production_batches (organization_id,farm_id,area_id,pond_id,code,name,species,initial_quantity,initial_weight_kg,stocked_at,expected_harvest_date,note,correction_of_id,batch_status,status,row_version,created_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',1,%s)",
        (organization_id, batch["farm_id"], batch["area_id"], batch["pond_id"], row["code"], f"投苗更正-{batch['name']}"[:120], batch["species"], quantity, batch.get("initial_weight_kg") or 0, happened, batch.get("expected_harvest_date"), "数据交换导入的投苗更正，核验后进入存塘流水", batch["id"], batch["batch_status"], user_id),
    )
    return "production:batches", int(cursor.lastrowid)


def _import_production_document(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int, doc_type: str, entity_type: str) -> tuple[str, int]:
    pond_id = _int(row.get("pond_id"))
    if pond_id:
        pond = _pond(cursor, organization_id, pond_id)
    elif _int(row.get("batch_id")):
        batch_row = _batch(cursor, organization_id, _int(row.get("batch_id")))
        pond_id = int(batch_row["pond_id"])
        pond = {"organization_id": organization_id, "farm_id": batch_row["farm_id"], "area_id": batch_row["area_id"]}
    else:
        raise DomainError("POND_REQUIRED", "生产导入必须明确填写塘口或关联批次", 400)
    enforce_area_scope(user, int(pond["area_id"]))
    if doc_type == "feed_task" and _int(row.get("assignee_id")):
        assignee_id = _int(row.get("assignee_id"))
        if _fetch(cursor, "SELECT id FROM users WHERE id=%s AND status='active'", (assignee_id,)) is None:
            raise DomainError("FEED_TASK_ASSIGNEE_INVALID", "指派作业员不存在或已停用", 400)
        if _fetch(
            cursor,
            "SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id AND r.status='active' "
            "JOIN user_data_scopes uds ON uds.user_id=ur.user_id JOIN data_scopes ds ON ds.id=uds.data_scope_id AND ds.status='active' "
            "WHERE ur.user_id=%s AND r.code IN ('breed_worker','breed_manager') AND (ds.scope_type='farm' OR ds.area_id=%s) LIMIT 1",
            (assignee_id, pond["area_id"]),
        ) is None:
            raise DomainError("FEED_TASK_ASSIGNEE_INVALID", "投喂任务只能指派授权养殖岗位人员", 400)
    target = _int(row.get("target_pond_id"))
    if target:
        target_pond = _pond(cursor, organization_id, target)
        if target == pond_id:
            raise DomainError("TRANSFER_TARGET_INVALID", "转入塘口不能与转出塘口相同", 400)
        if int(target_pond["organization_id"]) != organization_id:
            raise DomainError("TRANSFER_TARGET_INVALID", "转入塘口不属于当前企业", 400)
        enforce_area_scope(user, int(target_pond["area_id"]))
    columns = ["organization_id", "farm_id", "area_id", "document_type", "code", "name", "pond_id", "batch_id", "target_pond_id", "material_id", "assigned_user_id", "feed_plan_id", "feed_task_id", "material_issue_request_id", "planned_at", "quantity", "happened_at", "note"]
    values: list[Any] = [
        organization_id, pond["farm_id"], pond["area_id"], doc_type, row["code"], _text(row.get("name")) or str(row["code"]),
        pond_id, _int(row.get("batch_id")), target, _int(row.get("material_id")), _int(row.get("assignee_id")),
        _int(row.get("feed_plan_id")), _int(row.get("feed_task_id")), _int(row.get("material_issue_request_id")),
        row.get("planned_at") if doc_type == "feed_plan" else (row.get("planned_at") or row.get("happened_at") if doc_type == "feed_task" else None),
        row.get("quantity"), row.get("happened_at") if doc_type not in {"feed_plan", "feed_task"} else None,
        _text(row.get("reason")) or None,
    ]
    cursor.execute(f"INSERT INTO production_documents ({','.join(columns)},status,row_version,created_by) VALUES ({','.join(['%s'] * len(values))},'draft',1,%s)", (*values, user_id))
    return entity_type, int(cursor.lastrowid)


def _import_warehouse_document(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int, doc_type: str, entity_type: str) -> tuple[str, int]:
    material = _fetch(cursor, "SELECT id FROM materials WHERE id=%s AND organization_id=%s AND status='verified'", (_int(row.get("material_id")), organization_id))
    if material is None:
        raise DomainError("WAREHOUSE_MATERIAL_INVALID", "物料不存在、未核验或不属于当前企业", 400)
    warehouse_id = _int(row.get("warehouse_id")) or _first_warehouse(cursor, organization_id)
    warehouse = _warehouse(cursor, organization_id, warehouse_id)
    enforce_area_scope(user, int(warehouse["area_id"] or 0))
    target = _int(row.get("target_warehouse_id"))
    if target:
        target_warehouse = _warehouse(cursor, organization_id, target)
        if target == warehouse_id:
            raise DomainError("WAREHOUSE_TARGET_INVALID", "调入仓不能与调出仓相同", 400)
        enforce_area_scope(user, int(target_warehouse["area_id"] or 0))
    columns = ["organization_id", "farm_id", "area_id", "document_type", "code", "name", "warehouse_id", "target_warehouse_id", "material_id", "inventory_lot_id", "source_document_id", "lot_no", "quantity", "happened_at", "reason"]
    values: list[Any] = [
        organization_id, warehouse["farm_id"], warehouse["area_id"], doc_type, row["code"], _text(row.get("name")) or str(row["code"]),
        warehouse_id, target, row["material_id"], _int(row.get("inventory_lot_id")), _int(row.get("source_document_id")), _text(row.get("lot_no")) or None, row.get("quantity") or 0, row.get("happened_at"), _text(row.get("reason")) or None,
    ]
    cursor.execute(f"INSERT INTO warehouse_documents ({','.join(columns)},status,row_version,created_by) VALUES ({','.join(['%s'] * len(values))},'draft',1,%s)", (*values, user_id))
    return entity_type, int(cursor.lastrowid)


def _import_business_settings(cursor: Any, row: dict[str, Any], *, organization_id: int, user: dict[str, Any], user_id: int) -> tuple[str, int]:
    scope = scoped_area_defaults(cursor, user, organization_id)
    scope_columns = ",".join(scope)
    prefix = f",{scope_columns}" if scope_columns else ""
    cursor.execute(
        f"INSERT INTO business_settings (organization_id,code,name,group_code,value_text{prefix},status,row_version,created_by) VALUES (%s,%s,%s,%s,%s{',' + ','.join(['%s'] * len(scope)) if scope else ''},'draft',1,%s)",
        (organization_id, row["code"], row["name"], row["group_code"], row["value_text"], *scope.values(), user_id),
    )
    return "master:business-settings", int(cursor.lastrowid)


IMPORTERS: dict[str, Importer] = {
    "materials": lambda cursor, row, **ctx: _import_master(cursor, row, table="materials", entity_type="master:materials", extra={"category": row.get("category"), "specification": row.get("specification"), "unit": row.get("unit"), "safety_stock": row.get("safety_stock") or 0}, **ctx),
    "suppliers": lambda cursor, row, **ctx: _import_master(cursor, row, table="business_partners", entity_type="master:suppliers", extra={"partner_type": "supplier", "contact_name": row.get("contact_name"), "phone": row.get("phone")}, **ctx),
    "customers": lambda cursor, row, **ctx: _import_master(cursor, row, table="business_partners", entity_type="master:customers", extra={"partner_type": "customer", "contact_name": row.get("contact_name"), "phone": row.get("phone")}, **ctx),
    "business-settings": _import_business_settings,
    "ponds": _import_ponds,
    "batches": _import_batches,
    "stocking": _import_stocking,
    "samplings": lambda cursor, row, **ctx: _import_production_document(cursor, row, doc_type="sampling", entity_type="production:samplings", **ctx),
    "transfers": lambda cursor, row, **ctx: _import_production_document(cursor, row, doc_type="transfer", entity_type="production:transfers", **ctx),
    "losses": lambda cursor, row, **ctx: _import_production_document(cursor, row, doc_type="loss", entity_type="production:losses", **ctx),
    "harvests": lambda cursor, row, **ctx: _import_production_document(cursor, row, doc_type="harvest", entity_type="production:harvests", **ctx),
    "feed-plans": lambda cursor, row, **ctx: _import_production_document(cursor, row, doc_type="feed_plan", entity_type="production:feed-plans", **ctx),
    "feed-tasks": lambda cursor, row, **ctx: _import_production_document(cursor, row, doc_type="feed_task", entity_type="production:feed-tasks", **ctx),
    "feed-logs": lambda cursor, row, **ctx: _import_production_document(cursor, row, doc_type="feed_log", entity_type="production:feed-logs", **ctx),
    "daily-operations": lambda cursor, row, **ctx: _import_production_document(cursor, row, doc_type="daily_operation", entity_type="production:daily-operations", **ctx),
    "receipts": lambda cursor, row, **ctx: _import_warehouse_document(cursor, row, doc_type="receipt", entity_type="warehouse:receipts", **ctx),
    "issues": lambda cursor, row, **ctx: _import_warehouse_document(cursor, row, doc_type="issue", entity_type="warehouse:issues", **ctx),
    "warehouse-transfers": lambda cursor, row, **ctx: _import_warehouse_document(cursor, row, doc_type="transfer", entity_type="warehouse:transfers", **ctx),
    "returns": lambda cursor, row, **ctx: _import_warehouse_document(cursor, row, doc_type="return", entity_type="warehouse:returns", **ctx),
    "stocktakes": lambda cursor, row, **ctx: _import_warehouse_document(cursor, row, doc_type="stocktake", entity_type="warehouse:stocktakes", **ctx),
    "scraps": lambda cursor, row, **ctx: _import_warehouse_document(cursor, row, doc_type="scrap", entity_type="warehouse:scraps", **ctx),
    "purchase-orders": import_purchase_order,
    "payments": import_payment,
    "sales-orders": import_sales_order,
    "customer-receipts": import_customer_receipt,
    "expenses": import_expense,
    "assets": lambda cursor, row, **ctx: import_asset(cursor, row, asset_type=_text(row.get("asset_type")) or "equipment", entity_type="cost:assets", **ctx),
    "leases": lambda cursor, row, **ctx: import_asset(cursor, row, asset_type="lease", entity_type="cost:assets", **ctx),
    "cost-adjustments": import_cost_adjustment,
}


def get_importer(template_code: str) -> Importer | None:
    return IMPORTERS.get(template_code)
