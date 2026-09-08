# Acceptance Bugs

| Priority | ID | Description | Status |
| --- | --- | --- | --- |
| P0 | - | No P0 business defect found | 0 |
| P1 | AGENT-IDEMP-001 | Concurrent first writers could surface MySQL deadlock `1213` instead of a safe duplicate-request outcome | FIXED; regression and MySQL 8.0/8.4 evidence added |
| P1 | COVERAGE-001 | Backend coverage is below the 85% delivery gate | OPEN; latest full baseline is 82.42% |
| P1 | LIVE-001 | Live DeepSeek provider E2E | FAIL_AGENT_RESPONSE; Machine-scope key is configured and real turns run, but one broad query exceeded the 75s client timeout |
| P1 | EQUIV-001 | Full 16-module manual/Agent equivalence matrix | OPEN; pond scenario is proven |
| P1 | IDOR-001 | Full two-user REST and Agent IDOR matrix | OPEN; pond service/MySQL rejection is proven |
| P1 | CONF-001 | Confirmation business/ledger/audit exactly-once concurrency | OPEN; exactly-one token claim is proven |
| P1 | IDEMP-002 | Payment/receipt/inventory/import Agent request-id idempotency | OPEN; generic operation exactly-once is proven |
| P1 | AUDIT-001 | Full Agent instruction-to-before/after reconstruction across every high-risk write | OPEN; logger persistence and live failure audit are proven |
| P2 | DOC-001 | Final acceptance evidence consolidation | PASS; reports include fresh MySQL 8.0/8.4, frontend, live agent and security evidence |
| P3 | - | None | 0 |
