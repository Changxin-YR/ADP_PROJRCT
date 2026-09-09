# Confirmation Business Exactly-Once

Verification scope: current working tree, migration 032, disposable MySQL 8.0
(`33080`) and MySQL 8.4 (`33084`). The full backend suites on both versions
completed with `589 passed` and no skipped tests.

| ID | Scenario | 8.0 | 8.4 | Assertions | Result |
| --- | --- | --- | --- | --- | --- |
| CONF-001 | Same confirmation token, 20 concurrent claims | PASS | PASS | One winner; terminal confirmation state | PASS |
| CONF-002 | Warehouse receipt confirmation, 20 concurrent claims | PASS | PASS | One document effect, one inventory ledger effect, one success audit | PASS |
| CONF-003 | Payment confirmation, 20 concurrent claims | PASS | PASS | One payment effect, one payable transition, one success audit | PASS |
| CONF-004 | Claim succeeds, real business validation/concurrency failure | PASS | PASS | Confirmation and idempotency become `failed`; business and ledger unchanged; failure audit retained; token replay rejected | PASS |

The accepted transaction semantic is design A: a successful claim followed by
a real business failure is terminal `failed`; the caller starts a new
operation. No `UNKNOWN` state or partial ledger write was observed.

Evidence tests: `test_confirmation_claim_then_real_business_failure_is_terminal`,
`test_agent_confirmation_concurrency_posts_inventory_and_cost_once`,
`test_agent_confirmation_payment_effects_are_exactly_once`, and
`test_confirmation_business_mutation_and_audit_are_exactly_once`.
