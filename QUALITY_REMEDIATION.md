# Ruff and mypy: comprehensive remediation ledger

Branch: `refactor/modularization-ci-2026-11-19` (draft PR #6; do not merge until all gates pass).

CI baseline (20 November 2026, run 44816966055):
- Ruff: 112 remaining findings after the previous 422 safe edits.
- mypy: 283 errors in 13 files. Largest concentration: psinkamain.py (209).
- Formatter: 28 Python files.
- Tests: 83/83 passed on Python 3.10 and 3.12.
- Runtime smoke: 19 slash commands registered.

Categories recovered from job logs (Python 3.12): mypy no-untyped-def 143, name-defined 33, union-attr 27, assignment 21, var-annotated 17, arg-type 15, no-any-return 6; Ruff BLE001 31, C901 24, S311 11, E402 10, B023 6, S110 5, E701 4, E722 4.

## Bulk remediation procedure

1. Capture entire Ruff/mypy output before modifications.
2. Run safe Ruff fixes (never use `--unsafe-fixes`) and one full-project formatter pass.
3. Capture complete after-output; run full pytest, compile, and slash registration checks prior to committing any autochanges.
4. Address remaining mypy type defects by causes, especially nullable Discord entities, missing types, and incorrectly inferred collections; avoid blanket suppressions.
5. Address behavioral Ruff diagnostics (broad exception handling, random security checks, complexity, loop captures) with tests.
6. Final acceptance: Ruff, Ruff format and mypy clean on entire active project; regression CI green on Python 3.10 and 3.12, followed by staging Discord and PostgreSQL validation.

Bulk workflow: `.github/workflows/bulk-quality-pass.yml`. It commits to the refactor branch only after successful unit tests and writes diagnostic artifacts for the full project. This pass is not a release and does not imply the project is fully type-safe.

## Consolidated refactoring progress — 21 November 2026

- Restored the user-supplied AGENTS.md development requirements from the previous chat.
- Applied all safe Ruff autofixes and whole-project formatting in one tested CI pass (commit 1f475aed).
- Modernized SQLAlchemy declarative model typing, settings and jail repositories, auction normalization, dice rendering, and template parsing.
- Replaced dynamic post-counting structures with TypedDict models shared by metrics and reporting.
- Corrected missing initialization for the periodic settings flush task.
- Imported concrete Disnake interaction types; added access validation for DM users and nullable guilds.
- Fixed three progress-message edit paths to ask Discord for the sent message (wait=True).
- Added explicit return types to 36 command and lifecycle functions.
- Preserved all 19 slash-command definitions and kept the branch as a draft.
- Full mypy improved from 283 errors to 133 in the 3db5ab2 audit; later changes require a fresh audit.
- Full Ruff was still 95 findings at that audit; broad exception handling and complex legacy functions remain.
- Do not merge: live Discord and PostgreSQL staging checks have not been run.

GitHub Actions regression and full audit workflows remain authoritative for subsequent commits.
