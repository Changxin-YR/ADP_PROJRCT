from pathlib import Path

from tools.audit_source import scan_tree


ROOT = Path(__file__).parents[2]


def test_handwritten_sources_do_not_exceed_300_lines() -> None:
    offenders = [
        (finding.path, finding.text)
        for finding in scan_tree(ROOT).findings
        if finding.category == "over_300_lines"
    ]

    assert offenders == []

