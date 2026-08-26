from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Revision:
    entity_type: str
    entity_id: int
    version_no: int
    before: dict[str, Any]
    after: dict[str, Any]
    actor_user_id: int


def build_revision(
    *,
    entity_type: str,
    entity_id: int,
    current_version: int,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    actor_user_id: int,
) -> Revision:
    if current_version < 1:
        raise ValueError("current_version must be positive")
    return Revision(
        entity_type=entity_type,
        entity_id=entity_id,
        version_no=current_version + 1,
        before=dict(before),
        after=dict(after),
        actor_user_id=actor_user_id,
    )


def save_revision(connection: Any, revision: Revision) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO record_revisions
                (entity_type, entity_id, version_no, before_json, after_json, actor_user_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                revision.entity_type,
                revision.entity_id,
                revision.version_no,
                json.dumps(revision.before, ensure_ascii=False, default=str),
                json.dumps(revision.after, ensure_ascii=False, default=str),
                revision.actor_user_id,
            ),
        )

