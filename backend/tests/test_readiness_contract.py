from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import json

import pytest

from backend.scripts.readiness.common import (
    ReadinessFailure,
    evidence,
    percentile,
    require_disposable_database_name,
    safe_remove_tree,
)
from backend.scripts.readiness.database_drill import (
    DatabaseSnapshot,
    compare_snapshots,
    dump_arguments,
    require_database_tools,
)
from backend.scripts.readiness.load_probe import assess_load, generate_workload
from backend.scripts.readiness.run_all import summarize_results


def test_percentile_and_evidence_status_are_deterministic() -> None:
    assert percentile([0.1, 0.2, 0.3, 0.4], 95) == pytest.approx(0.4)

    result = evidence("probe", {"success": 500, "total": 500}, passed=True)

    assert result["probe"] == "probe"
    assert result["status"] == "PASS"
    assert result["metrics"]["total"] == 500
    assert "started_at" in result and "finished_at" in result


@pytest.mark.parametrize(
    "name",
    ["adp_auth", "production", "adp_readiness_x;DROP DATABASE x"],
)
def test_database_cleanup_requires_random_readiness_prefix(name: str) -> None:
    with pytest.raises(ReadinessFailure):
        require_disposable_database_name(name)


def test_database_cleanup_accepts_only_known_random_prefixes() -> None:
    name = "adp_readiness_source_012345abcdef"

    assert require_disposable_database_name(name) == name


def test_tree_cleanup_refuses_workspace_or_parent(tmp_path: Path) -> None:
    with pytest.raises(ReadinessFailure):
        safe_remove_tree(tmp_path, allowed_parent=tmp_path)


def test_evidence_recursively_redacts_secret_fields() -> None:
    result = evidence(
        "probe",
        {
            "password": "plain",
            "nested": {"csrfToken": "token-value", "safe": "visible"},
        },
        passed=False,
    )

    assert result["status"] == "FAIL"
    assert result["metrics"]["password"] == "[REDACTED]"
    assert result["metrics"]["nested"] == {
        "csrfToken": "[REDACTED]",
        "safe": "visible",
    }


def test_database_snapshot_comparison_names_exact_difference() -> None:
    source = DatabaseSnapshot(
        migrations={"024_pond_extended_fields": "abc"},
        table_counts={"ponds": 2},
        aggregates={"inventory_quantity": "30.000"},
    )

    assert compare_snapshots(source, source) == []
    assert compare_snapshots(
        source,
        replace(source, table_counts={"ponds": 1}),
    ) == ["table_counts.ponds: source=2 restore=1"]


def test_database_dump_uses_production_consistency_flags() -> None:
    assert dump_arguments("source") == [
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--set-gtid-purged=OFF",
        "source",
    ]


def test_database_drill_requires_explicit_disposable_permission() -> None:
    with pytest.raises(ReadinessFailure, match="ALLOW_DISPOSABLE"):
        require_database_tools({})


def test_hard_load_gate_requires_every_request_and_both_percentiles() -> None:
    accepted = assess_load(
        total=500,
        successes=500,
        latencies=[0.1] * 475 + [2.9] * 20 + [4.9] * 5,
        server_errors=0,
        write_expected=50,
        write_actual=50,
        p95_limit=3,
        p99_limit=5,
    )
    assert accepted.passed
    assert not assess_load(
        total=500,
        successes=499,
        latencies=[0.1] * 500,
        server_errors=0,
        write_expected=50,
        write_actual=50,
        p95_limit=3,
        p99_limit=5,
    ).passed
    assert not assess_load(
        total=500,
        successes=500,
        latencies=[0.1] * 474 + [3.001] * 26,
        server_errors=0,
        write_expected=50,
        write_actual=50,
        p95_limit=3,
        p99_limit=5,
    ).passed
    assert not assess_load(
        total=500,
        successes=500,
        latencies=[0.1] * 494 + [5.001] * 6,
        server_errors=0,
        write_expected=50,
        write_actual=50,
        p95_limit=3,
        p99_limit=5,
    ).passed


def test_workload_has_exact_write_ratio_and_unique_safe_codes() -> None:
    workload = generate_workload(500, stage=500, run_id="abcdef123456")

    assert len(workload) == 500
    writes = [item for item in workload if item.method == "POST"]
    assert len(writes) == 50
    assert len({item.payload["code"] for item in writes if item.payload}) == 50
    serialized = json.dumps([item.__dict__ for item in workload])
    assert "password" not in serialized.lower()
    assert "token" not in serialized.lower()


def test_readiness_summary_never_promotes_not_run_or_failure() -> None:
    passing = [
        {"probe": probe, "status": "PASS", "metrics": {}}
        for probe in ("database-drill", "attachment-security", "large-export", "http-load")
    ]
    assert summarize_results(passing)["status"] == "PASS"
    passing[-1] = {"probe": "http-load", "status": "NOT_RUN", "metrics": {}}
    assert summarize_results(passing)["status"] == "FAIL"
    passing[-1] = {"probe": "http-load", "status": "FAIL", "metrics": {}}
    assert summarize_results(passing)["status"] == "FAIL"
