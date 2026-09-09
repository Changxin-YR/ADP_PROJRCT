# Acceptance Bugs

| Priority | ID | Description | Status |
| --- | --- | --- | --- |
| P0 | - | No P0 business defect found | 0 |
| P1 | AGENT-IDEMP-001 | Concurrent first writers could surface MySQL deadlock `1213` instead of a safe duplicate-request outcome | FIXED; regression and MySQL 8.0/8.4 evidence added |
| P1 | COVERAGE-001 | Backend coverage is below the preferred 86% buffer | RESOLVED for the delivery gate; fresh value is `85.04370673538477%` (above 85%) |
| P1 | LIVE-001 | Live DeepSeek provider E2E | FIXED; fresh broad-query smoke is 5/5 HTTP 200 with 3.10–14.61s latency |
| P1 | EQUIV-001 | Full 16-module manual/Agent equivalence matrix | BLOCKED; production, inventory and attachment applicability evidence exists, but the complete module/mixed matrix is not executed |
| P1 | IDOR-001 | Full two-user REST and Agent IDOR matrix | BLOCKED; service/Agent pond rejection passes, complete REST/action/export matrix lacks an isolated 8.0/8.4 run |
| P1 | CONF-001 | Confirmation business/ledger/audit exactly-once concurrency | PASS for the executed disposable regression; 8.0/8.4 rerun remains required |
| P1 | IDEMP-002 | Payment/receipt/inventory/import Agent request-id idempotency | PASS for the executed disposable regression; 8.0/8.4 rerun remains required |
| P1 | AUDIT-001 | Full Agent instruction-to-before/after reconstruction across every high-risk write | PASS for representative shared-pipeline classes; 8.0/8.4 rerun remains required |
| P2 | DOC-001 | Final acceptance evidence consolidation | BLOCKED until required 8.0/8.4 and complete IDOR/equivalence evidence is available |
| P3 | - | None | 0 |
