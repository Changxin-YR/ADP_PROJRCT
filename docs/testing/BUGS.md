# Acceptance Bugs

## Confirmed Bugs

| Priority | ID | Description | Status |
| --- | --- | --- | --- |
| P0 | - | No P0 business defect found in final current-head regression | 0 open |
| P1 | AGENT-IDEMP-001 | Concurrent first writers could surface MySQL deadlock `1213` instead of a safe duplicate-request outcome | FIXED and regression-covered |
| P1 | LIVE-001 | Broad-query latency regression | FIXED by bounded read path and live smoke |
| P1 | IDOR-RET-001 | Return store resolved only organization scope, allowing cross-area return access | FIXED; purchase and sales return scope regressions PASS |
| P1 | LIVE-WRITE-002 | Harness sidecar hid confirmation payloads nested in tool-result events | FIXED; 3/3 live confirmation regressions PASS |

## Open Bugs

P0: `0`
P1: `0`
P2: `0`
P3: `0`

## Acceptance Gaps

`0` (`IDOR-001` PASS; `LIVE-WRITE-001` PASS)
