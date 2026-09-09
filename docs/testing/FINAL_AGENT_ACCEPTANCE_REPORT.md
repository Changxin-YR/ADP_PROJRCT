# Final Agent Acceptance Report

Date: 2026-09-09

## Final Grade

`C`

The current working tree has fresh MySQL 8.0/8.4 and business-equivalence
evidence, but it is not eligible for A because the complete two-user IDOR
matrix and current-head live confirmed-write/multi-turn evidence are not
closed. No implementation P0 or P1 defect is open.

## Git / Backend Evidence

* Branch: `main`; final delivery commit is reported in the Git section of this handoff.
* MySQL 8.0: `589 passed`, `0 failed`, `0 skipped`.
* MySQL 8.4: `589 passed`, `0 failed`, `0 skipped`.
* Collection parity: `589` identical node IDs.
* Fresh coverage: `86.05%` on 8.4, 20,311 statements.
* Frontend: unit `117 passed`, build PASS, Playwright `34 passed`.
* Fresh final acceptance/equivalence subset: `28 passed` on each of MySQL 8.0 and
  8.4, with zero failures and zero skips.

## Gate 2 Agent

Deterministic permission parity, Agent Gateway execution and all backend Agent
tests pass on both MySQL versions. A real bundled DeepSeek runtime query
returned HTTP 200 for an authenticated user, and a low-permission denial smoke
returned without a business mutation. The current live confirmed-write prompt
did not yield a confirmation token, and the combined multi-turn/broad smoke
timed out after repeated model tool calls; these are acceptance gaps, not
implementation failures.

## Gate 3 Security

Prompt Injection PI-001..PI-008 historical evidence, Tool Injection, DataScope,
confirmation failure semantics, Payment/Receipt/Inventory/Import idempotency,
and representative audit trace classes are PASS. The two-user REST test proves
same-permission cross-area rejection for Pond path/actions, foreign-area body
ID, attachment metadata/download and export scope. The full resource/action
IDOR matrix and Agent natural-language IDOR remain OPEN.

## Gate 4 Business Equivalence

Pond, Fish Batch, Feeding, Inspection, Inventory, Cost, Purchase, Purchase
Return, Payment, Sales, Sales Return, Receipt, Attachment metadata and Data
Exchange export equivalence pass on both MySQL versions. Health/Diagnosis and
Device are `NOT_APPLICABLE` because the repository has no corresponding
business table, API or Agent tool. Attachment Agent upload and Data Exchange
multipart import are `NOT_APPLICABLE` only for the Agent path; their REST
capabilities remain separately classified. Mixed Production, Mixed Purchase
and Mixed Sales all pass.

## Confirmed Bugs

* Open P0: 0
* Open P1: 0
* Fixed this round: no new implementation bug; acceptance tests and evidence
  docs were added.

## Acceptance Gaps

* `IDOR-001`: execute and record all applicable two-user REST/action/foreign-key
  rows plus representative natural-language Agent IDOR.
* `LIVE-WRITE-001`: close current-head live DeepSeek confirmed write and
  required multi-turn/broad smoke.

Until both rows are PASS, the correct rating is `C`, not `A`.
