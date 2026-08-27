# Structural hardening and real-environment verification

## Goal

Close the remaining verified Web defects that can be fixed without changing product design, and make the real MySQL/E2E gates executable in CI. Preserve the local `BLOCKED` result when required external services are unavailable.

## Scope

1. Reproduce the two current Playwright failures and fix the smallest contract mismatch.
2. Verify migration history/checksum behavior and ensure new authorization changes live in a new migration.
3. Add a disposable MySQL service to CI and run the real integration fixture with explicit environment variables.
4. Add regression coverage for each production fix, then run backend, frontend, build, and E2E checks.
5. Re-scan the touched call chains and report any remaining structural items as `BLOCKED` or known issues rather than claiming closure.

## Constraints

- Web scope only.
- No SQLite substitution for MySQL integration tests.
- No hard-coded organization or warehouse fallback.
- Minimal edits; preserve existing API and UI contracts.
