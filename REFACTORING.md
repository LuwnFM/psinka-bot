# Refactoring progress — 19 November 2026

**Status: extensive work in progress. Draft PR #6; DO NOT MERGE.** The default `main` branch has not changed. The work here is real, tested incremental refactoring, **not a completed full refactor**.

## Implemented

- Removed import-time `pip install`, database connections, logging file creation and mercenary Excel loading. Explicit initialization now happens before `bot.run`.
- Centralized typed configuration (`core/config.py`) and runtime logging (`core/logging_setup.py`), including idempotent handler setup and one heartbeat task per running bot.
- Extracted SQLAlchemy models (`db/models.py`), initialization (`db/session.py`), AI-provider metrics (`repositories/model_success.py`) and jail sentence persistence (`repositories/jail.py`). Existing jail scheduler uses repository wrappers and still runs database operations in worker threads.
- Extracted CSV model test state (`repositories/pending_tests.py`) and atomic, serialized JSON post-count settings (`repositories/post_count_settings.py`), with startup initialization and async-safe disk operations.
- Preserved dice parsing and formatting (`services/dice.py`, `services/dice_format.py`), auction text/lot parsing (`services/auction_text.py`, `services/auction_lots.py`), template recognition, counting and reporting (`services/post_count_*.py`).
- Replaced manual XLSX ZIP/XML writer and mercenary workbook reader with `openpyxl`; mercenary lookup normalization is separated from Discord in `services/mercenary_normalize.py`.
- Moved user-visible `/кубик`, `/погавкай` and `/статус` response logic into `handlers/utility_commands.py`; the original 19 slash registrations and their decorators remain in the entrypoint.
- Offloaded several blocking SQLAlchemy and CSV writes from asynchronous event handlers using `asyncio.to_thread`.

## Compatibility checks in GitHub Actions

The `Regression checks` workflow runs on **Python 3.10 and 3.12**. It compiles all active packages and runs a pytest suite with realistic SQLite sessions, real Excel workbooks, file persistence/restart cases, concurrent settings mutations, seeded dice rolls, and mocked Discord interactions. It also compares **unchanged extracted function/class ASTs** and **all 19 slash-command decorators** with the original `main` branch. Intentionally rewritten repositories are guarded by behavioral tests instead of AST identity.

A separate quality job runs **Ruff and mypy** on the modernized, selected infrastructure modules. **Do not interpret this as clean lint/type checking for the entire legacy codebase.**

These tests require no Discord token or production database and have **not** run a full Discord bot startup, real API calls, or live PostgreSQL guild workflows.

## Remaining blocking work

1. Break down the still-large `psinkamain.py` into domain-specific cogs, service classes and dependency-injected repositories, particularly AI routing, mercenary generation, jail command orchestration, auction network fetching, admin flows, and post search.
2. Move remaining file/SQL/network blocking operations off the event loop, reuse HTTP/model clients, add explicit network timeouts, and remove broad/bare exception catches throughout the remaining handlers.
3. Reach full AGENTS.md Ruff/mypy compliance across all active modules, including the legacy entrypoint; remove hardcoded lookup tables and large prompts from Python modules.
4. Add end-to-end and integration tests for every command, Discord events, restarts, provider failover, exception paths and database migrations. Validate on a staging Discord guild before production deployment.

**Never merge while any of the above release gates are unverified.**
