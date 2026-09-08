# Acceptance Bugs

| Priority | ID | Description | Status |
| --- | --- | --- | --- |
| P0 | - | No P0 business defect found | 0 |
| P1 | AGENT-IDEMP-001 | Concurrent first writers could surface MySQL deadlock `1213` instead of a safe duplicate-request outcome | FIXED; regression and MySQL 8.0/8.4 evidence added |
| P1 | COVERAGE-001 | Backend coverage is below the 85% delivery gate | OPEN; latest full baseline is 82% |
| P1 | LIVE-001 | Live DeepSeek provider E2E | FAIL_AGENT_RESPONSE; Machine-scope key is configured and real turns run, but one broad query exceeded the 75s client timeout |
| P1 | EQUIV-001 | Full 16-module manual/Agent equivalence matrix | OPEN; pond scenario is proven |
| P1 | AUDIT-001 | Full Agent instruction-to-before/after reconstruction across every high-risk write | PASS for exercised write and failure paths; broader business-module evidence remains open |
| P2 | DOC-001 | Final acceptance evidence consolidation | PASS; reports include fresh MySQL 8.0/8.4, frontend, live agent and security evidence |
| P3 | - | None | 0 |
