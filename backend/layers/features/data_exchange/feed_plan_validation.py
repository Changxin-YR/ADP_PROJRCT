from __future__ import annotations

from typing import Any

from backend.layers.features.data_exchange.import_refs import _int
from backend.layers.features.production.production_relations import feed_plan_relation_valid


def check_feed_plan_relations(
    cursor: Any,
    _organization_id: int,
    rows: list[dict[str, Any]],
    row_numbers: list[int],
    errors: list[dict[str, Any]],
) -> None:
    for row, number in zip(rows, row_numbers):
        if not all(_int(row.get(field)) for field in ("pond_id", "batch_id", "material_id")):
            continue
        if not feed_plan_relation_valid(cursor, row):
            errors.append({
                "row": number,
                "column": "batch_id",
                "message": "投喂计划必须关联同企业、同塘口的已核验批次和可用饲料",
                "value": row.get("batch_id"),
            })
