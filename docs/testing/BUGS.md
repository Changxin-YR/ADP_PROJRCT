# Acceptance Bugs

## Confirmed Bugs

| Priority | ID | Description | Status |
| --- | --- | --- | --- |
| P0 | - | No P0 business defect found in the final 8.0/8.4 runs | 0 open |
| P1 | AGENT-IDEMP-001 | Concurrent first writers could surface MySQL deadlock `1213` instead of a safe duplicate-request outcome | FIXED and covered by regression |
| P1 | LIVE-001 | Broad-query latency regression | FIXED in the existing bounded read path; current direct live query smoke returned HTTP 200 |

## Acceptance Gaps

| ID | Gap | Evidence status |
| --- | --- | --- |
| IDOR-001 | Full two-user REST/action matrix for every applicable resource, plus natural-language Agent IDOR | Representative Pond/attachment/export REST and service scope tests PASS; full matrix remains OPEN |
| LIVE-WRITE-001 | Current bundled-runtime live DeepSeek confirmed-write smoke did not produce a confirmation token; deterministic Gateway confirmed-write tests PASS | OPEN; do not claim live confirmed-write PASS |

No implementation P0/P1 defect is open. The two rows above are acceptance
evidence gaps, not inferred business bugs.
