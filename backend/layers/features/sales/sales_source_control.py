from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.common.files.evidence import validate_bound_evidence


def harvest_root(cursor: Any, order: dict[str, Any], row: dict[str, Any]) -> int:
    cursor.execute(
        "SELECT id,document_type,status,batch_id,pond_id,quantity,weight_kg,correction_of_id "
        "FROM production_documents WHERE id=%s",
        (row.get("harvest_document_id"),),
    )
    harvest = cursor.fetchone()
    if harvest is None or harvest["document_type"] != "harvest" or harvest["status"] != "verified" or int(harvest["batch_id"] or 0) != int(order["batch_id"]) or int(harvest["pond_id"]) != int(order["pond_id"]):
        raise DomainError("SALES_HARVEST_INVALID", "交付必须关联同批次塘口的已核验出塘单", 409)
    cursor.execute("SELECT id FROM production_documents WHERE correction_of_id=%s AND status='verified' LIMIT 1", (harvest["id"],))
    if cursor.fetchone():
        raise DomainError("SALES_HARVEST_SUPERSEDED", "该出塘单已有已核验更正，请关联最新更正单", 409)
    available = Decimal(str(harvest["weight_kg"])) * (2 if order["unit"] == "jin" else 1) if order["unit"] != "tail" else Decimal(str(harvest["quantity"]))
    if Decimal(str(row["quantity"])) != available:
        raise DomainError("SALES_HARVEST_QUANTITY_MISMATCH", "交付数量必须与关联出塘事实一致", 409)
    root_id, parent_id = int(harvest["id"]), harvest.get("correction_of_id")
    while parent_id:
        root_id = int(parent_id)
        cursor.execute("SELECT correction_of_id FROM production_documents WHERE id=%s", (root_id,))
        parent = cursor.fetchone()
        if parent is None:
            raise DomainError("SALES_HARVEST_INVALID", "出塘更正来源不存在", 409)
        parent_id = parent.get("correction_of_id")
    return root_id


def require_order_evidence(cursor: Any, order: dict[str, Any], evidence: list[int]) -> None:
    validate_bound_evidence(cursor, organization_id=int(order["organization_id"]), entity_type="sales:order", entity_id=int(order["id"]), evidence_ids=evidence)
