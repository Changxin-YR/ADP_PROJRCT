from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from backend.layers.common.governance.lifecycle import DomainError


def normalize_evidence_ids(value: Any) -> list[int]:
    if value in (None, ""):
        return []
    if not isinstance(value, (list, tuple)):
        raise DomainError("EVIDENCE_INVALID", "凭据编号必须是数组", 400)
    evidence: list[int] = []
    try:
        for item in value:
            if isinstance(item, bool):
                raise ValueError("boolean is not an attachment id")
            number = Decimal(str(item))
            if not number.is_finite() or number < 1 or number != number.to_integral_value():
                raise ValueError("attachment id must be a positive integer")
            normalized = int(number)
            if normalized not in evidence:
                evidence.append(normalized)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DomainError("EVIDENCE_INVALID", "凭据编号无效", 400) from exc
    return evidence


def evidence_from_payload(payload: Any, fallback: Any = None) -> list[int]:
    if payload is not None and not isinstance(payload, dict):
        raise DomainError("PAYLOAD_INVALID", "请求内容必须是对象", 400)
    value = payload["evidence_attachment_ids"] if payload and "evidence_attachment_ids" in payload else fallback
    return normalize_evidence_ids(value)


def validate_bound_evidence(
    cursor: Any,
    *,
    organization_id: int,
    entity_type: str | tuple[str, ...],
    entity_id: int,
    evidence_ids: Any,
    invalid_status: int = 400,
    invalid_message: str = "凭据不存在或未绑定当前业务记录",
) -> list[int]:
    evidence = normalize_evidence_ids(evidence_ids)
    if not evidence:
        return evidence
    placeholders = ",".join(["%s"] * len(evidence))
    entity_types = (entity_type,) if isinstance(entity_type, str) else tuple(dict.fromkeys(entity_type))
    if not entity_types:
        raise DomainError("EVIDENCE_INVALID", invalid_message, invalid_status)
    if len(entity_types) == 1:
        type_clause, type_params = "entity_type=%s", entity_types
    else:
        type_clause = f"entity_type IN ({','.join(['%s'] * len(entity_types))})"
        type_params = entity_types
    cursor.execute(
        f"SELECT COUNT(*) AS total FROM attachments WHERE organization_id=%s AND {type_clause} "
        f"AND entity_id=%s AND id IN ({placeholders})",
        (organization_id, *type_params, entity_id, *evidence),
    )
    if int((cursor.fetchone() or {}).get("total", 0)) != len(evidence):
        raise DomainError("EVIDENCE_INVALID", invalid_message, invalid_status)
    return evidence
