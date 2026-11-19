# Full-project quality audit — 19 November 2026

Status: **not release-ready**, `main` unchanged. The strict quality audit is an intentional release gate; never hide failures by disabling Ruff/mypy rules.

## Verified CI evidence

Full audit run: https://github.com/LuwnFM/psinka-bot/actions/runs/44537833086

- **Compilation:** all tracked Python sources compile.
- **Runtime import:** `psinkamain` imports successfully with installed project requirements and no Discord/API/database secrets; all 19 slash commands register.
- **pytest:** **72 passed, 1 warning**, Python 3.12; Python 3.10 also runs tests once the full checkout fix was applied.
- **Ruff (full project): 548 findings**; 406 were marked automatically fixable by Ruff but should be reviewed with behavior tests before applying.
- **Ruff format (full project): 28 Python files** fail the formatting check.
- **mypy (full project): 284 errors in 14 files** (30 sources checked).
- **Selected infrastructure modules:** the separate `quality-new-modules` job passes Ruff and mypy, but does **not** mean whole-project quality passes.

The first full-audit iteration checked out a shallow Git history and caused two test-only AST comparisons to fail because `origin/main` was unavailable. The audit workflow now uses `fetch-depth: 0`; the subsequent complete test suite succeeds.

## What the findings mean

A reported lint/type issue is **not automatically a confirmed runtime failure**. Nevertheless, mypy has identified concrete unsafe patterns involving nullable Discord entities, optional input values, and inconsistent inferred types. These warrant explicit validation, not blanket `type: ignore`.

Ruff findings include legacy `typing.List/Dict/Tuple/Optional` syntax, unused imports, import ordering, and other maintainability violations. Safe mechanical improvements should be applied in small reviewed commits, guarded by AST/behavioral checks.

## File-size principle

The 300–500-line module guidance from AGENTS.md is a maintainability signal, **not an instruction to split a cohesive module at arbitrary line boundaries**. It is acceptable to keep one moderately sized focused module if it improves readability and preserves domain invariants. Long complicated functions and mixed presentation/business/persistence responsibilities remain refactoring priorities.

## Release gates still missing

1. Resolve real unsafe accesses revealed by mypy; reach clean full-project type checking.
2. Fix Ruff violations and formatting with review rather than suppressing checks.
3. Cover every slash command, event listener, AI fallback path, jail and mercenary state transition with integration tests.
4. Run a real Discord staging guild and PostgreSQL staging environment (not performed by CI: secrets are intentionally absent).
5. Review runtime resource lifecycle, logging, API client timeouts, file state, and shut-down paths before a merge.

Current live audit workflow: `.github/workflows/full-audit.yml`; original regression workflow: `.github/workflows/regression.yml`. Draft PR: https://github.com/LuwnFM/psinka-bot/pull/6
