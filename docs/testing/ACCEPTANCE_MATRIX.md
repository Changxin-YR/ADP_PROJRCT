# ADP Final Acceptance Matrix

Date: 2026-09-09
Verification tree: final delivery commit reported in the handoff plus the listed
acceptance tests and reports.

## Backend / Gate 1

| Item | Result | Fresh evidence |
| --- | --- | --- |
| MySQL 8.0 | PASS | `589 passed`, 0 failed, 0 skipped on disposable `33080` |
| MySQL 8.4 | PASS | `589 passed`, 0 failed, 0 skipped on disposable `33084` |
| Fresh migration bootstrap | PASS | Empty disposable databases migrated through 032 and seeded in both runs |
| Collection parity | PASS | Both versions collected `589` tests with identical node IDs |
| Coverage | PASS | Fresh 8.4 run: `86.05%`, 20,311 statements, `589 passed` |
| Fresh final acceptance/equivalence subset | PASS | The current tree's 28 acceptance/equivalence tests passed on both `33080` and `33084`; 0 failed, 0 skipped |

## Frontend

| Item | Result | Evidence |
| --- | --- | --- |
| Unit | PASS | `117 passed` |
| Production build | PASS | `vue-tsc --noEmit && vite build` exit 0 |
| Playwright E2E | PASS | `34 passed` (16 regular + 18 W4) |

## Agent / Gate 2

| Item | Result | Fresh evidence |
| --- | --- | --- |
| Permission parity | PASS | Existing registry parity test remains `171/171` |
| Deterministic execution | PASS | Full backend suite and Agent Gateway tests pass on both MySQL versions |
| Live DeepSeek query | PASS | Bundled runtime, authenticated query, HTTP 200 and assistant response |
| Live permission denial | PASS | Bundled runtime, low-permission user, backend denial attempts and no write observed |
| Live confirmed write | OPEN | Current live prompts did not produce a confirmation token; deterministic confirmation tests PASS |
| Multi-turn / broad query | OPEN | Historical evidence exists; current bundled smoke was not closed for all required turns |

## Security / Gate 3

| Item | Result | Evidence |
| --- | --- | --- |
| Prompt Injection | PASS (historical live PI-001..PI-008) | No identity, scope or DB bypass in recorded chain |
| Tool Injection | PASS | Registry unknown-tool and parameter validation tests |
| DataScope | PASS | Cross-organization, area, personal, import and attachment scope tests |
| Confirmation | PASS | CONF-001..004 pass on both MySQL versions |
| Idempotency | PASS | Payment, receipt, inventory and import sequential/concurrent/timeout replay pass on both versions |
| Audit | PASS | Representative success, denial, failure and replay trace classes pass on both versions |
| IDOR | OPEN | Pond/attachment/export two-user REST evidence PASS; full resource/action and Agent natural-language matrix remains unexecuted |
| Overall | BLOCKED | IDOR and current live confirmed-write evidence gaps remain |

## Business Equivalence / Gate 4

See `MANUAL_AGENT_EQUIVALENCE.md`. All applicable module scenarios and the
three mixed workflows are PASS; Health/Device and multipart Agent import/upload
are formally `NOT_APPLICABLE` with written trigger evidence.

| Gate | Result |
| --- | --- |
| Gate 1 Management | PASS |
| Gate 2 Agent | BLOCKED by live-write/multi-turn evidence |
| Gate 3 Security | BLOCKED by IDOR evidence |
| Gate 4 Business Equivalence | PASS |

## Acceptance Gaps

1. Complete two-user REST/action/foreign-key IDOR matrix and Agent natural-language IDOR.
2. Current-head live DeepSeek confirmed-write and required multi-turn/broad-query smoke closure.

Final grade is `C` until both evidence gaps are executed and pass.
