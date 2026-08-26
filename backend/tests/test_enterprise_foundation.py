from pathlib import Path

import pytest

from backend.layers.common.files.attachments import AttachmentError, prepare_attachment
from backend.layers.common.governance.idempotency import request_hash, validate_replay
from backend.layers.common.governance.lifecycle import DomainError, policy, verify_version
from backend.layers.common.governance.revisions import build_revision


ROOT = Path(__file__).parents[2]


def test_submitted_record_is_editable_but_not_deletable() -> None:
    rules = policy("submitted")

    assert rules.can_edit is True
    assert rules.can_delete is False
    assert rules.allowed_actions == ("view", "edit", "verify")


def test_verified_record_is_read_only() -> None:
    rules = policy("verified")

    assert rules.can_edit is False
    assert rules.can_delete is False
    assert "edit" not in rules.allowed_actions
    assert "delete" not in rules.allowed_actions


def test_stale_verification_is_rejected_as_conflict() -> None:
    with pytest.raises(DomainError) as caught:
        verify_version(expected_version=2, current_version=3)

    assert caught.value.code == "VERSION_CONFLICT"
    assert caught.value.status == 409


def test_revision_uses_next_version_and_keeps_before_after() -> None:
    revision = build_revision(
        entity_type="feed_plan",
        entity_id=9,
        current_version=2,
        before={"amount": "10.00"},
        after={"amount": "12.00"},
        actor_user_id=7,
    )

    assert revision.version_no == 3
    assert revision.before == {"amount": "10.00"}
    assert revision.after == {"amount": "12.00"}


def test_idempotency_hash_is_stable_and_replay_body_must_match() -> None:
    first = request_hash({"amount": "10.00", "pond_id": 2})
    second = request_hash({"pond_id": 2, "amount": "10.00"})

    assert first == second
    validate_replay(stored_request_hash=first, incoming_request_hash=second)
    with pytest.raises(DomainError, match="IDEMPOTENCY_CONFLICT"):
        validate_replay(stored_request_hash=first, incoming_request_hash=request_hash({"amount": "11.00"}))


def test_attachment_storage_name_is_private_and_server_generated() -> None:
    metadata = prepare_attachment(
        original_name="采购付款凭证-客户A.pdf",
        media_type="application/pdf",
        content=b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n",
    )

    assert metadata.original_name == "采购付款凭证-客户A.pdf"
    assert "客户A" not in metadata.storage_name
    assert len(metadata.storage_name) == 32
    assert metadata.size_bytes == len(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n")
    with pytest.raises(AttachmentError):
        prepare_attachment(original_name="empty.pdf", media_type="application/pdf", content=b"")


def test_attachment_extension_must_match_declared_and_detected_media_type() -> None:
    with pytest.raises(AttachmentError, match="扩展名与声明类型不一致"):
        prepare_attachment(
            original_name="伪装凭证.pdf",
            media_type="image/png",
            content=b"\x89PNG\r\n\x1a\n" + b"image-bytes",
        )


def test_enterprise_migrations_declare_scope_revision_and_immutability_contracts() -> None:
    scope_sql = (ROOT / "database/migrations/006_organizations_and_scopes.sql").read_text(encoding="utf-8")
    governance_sql = (ROOT / "database/migrations/007_revisions_idempotency_attachments.sql").read_text(encoding="utf-8")
    combined = scope_sql + governance_sql

    for marker in (
        "CREATE TABLE organizations",
        "CREATE TABLE farms",
        "CREATE TABLE pond_groups",
        "CREATE TABLE ponds",
        "CREATE TABLE record_revisions",
        "UNIQUE KEY uq_record_revisions_entity_version",
        "CREATE TABLE idempotency_keys",
        "UNIQUE KEY uq_idempotency_user_action_key",
        "CREATE TABLE attachments",
        "storage_name CHAR(32)",
        "sha256 CHAR(64)",
        "target_version INT UNSIGNED",
        "CREATE TRIGGER audit_logs_no_update",
        "CREATE TRIGGER audit_logs_no_delete",
    ):
        assert marker in combined

