# Full-project quality audit — 19 November 2026

Status: **not release-ready**, `main` unchanged. The strict quality audit is an intentional release gate; never hide failures by disabling Ruff/mypy rules.

## Verified CI evidence

Initial full audit: https://github.com/LuwnFM/psinka-bot/actions/runs/44537833086

Updated audit after targeted fixes: https://github.com/LuwnFM/psinka-bot/actions/runs/44538798942

- **Compilation:** all tracked Python sources compile.
- **Runtime import:** `psinkamain` imports successfully with installed project requirements and no Discord/API/database secrets; all 19 slash commands register.
- **pytest:** **72 passed, 1 warning**, Python 3.12; Python 3.10 also runs tests once the full checkout fix was applied.
- **Initial Ruff (full project): 548 findings**; 406 were marked automatically fixable. **Updated audit: 527 findings**. Review safe fixes with behavior tests before applying.
- **Ruff format: initially 28 files; updated audit 26 files** fail the formatting check.
- **mypy: initially 284 errors in 14 files; updated audit 280 errors in 13 files** (30 sources checked initially).
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

## Incremental corrections after audit

- Rewrote the pending AI model CSV repository with explicit return types, concrete filesystem/CSV exception handling, and stable header behavior, preserving the existing successful persistence tests.
- Modernized XLSX writer type annotations and guarded workbook initialization; tidied the jail time helper.
- Expanded the separate quality gate to verify these newly modernized infrastructure modules.
- Startup smoke now loads the real bundled mercenary workbook and validates search behavior without production credentials.

No full CI green status is claimed: only the regression workflow and selected-module quality gate currently pass. The intentionally strict full-project quality checks still fail.


## Ruff safe-fix pass — 20 November 2026

- Full-audit baseline for the pass: **527 Ruff findings, 394 marked safe-fixable**, plus **8 unsafe suggestions**.
- Executed pinned **Ruff 0.17.6** with **`ruff check --fix .`**, and **never** passed `--unsafe-fixes`.
- Ruff reported **422 applied edits** after cascading corrections, affecting 10 Python files. The exact code commit is [ffda147](https://github.com/LuwnFM/psinka-bot/commit/ffda147).
- Structural compatibility tests were strengthened to normalize only equivalent type-annotation spellings and dictionary-key iteration. Function bodies remain compared, and separate tests prove that changed argument defaults or logic still fail these checks.
- The one-time write-enabled workflow was deleted after successful use, avoiding unexpected repeated automatic commits.
- New full audit: **112 remaining Ruff findings**, **283 mypy errors in 13 files**, and **28 files requiring Ruff formatting**.
- All **83 pytest tests pass on Python 3.10 and 3.12**, and the credential-free runtime import validates all 19 slash commands.
- Full audit: https://github.com/LuwnFM/psinka-bot/actions/runs/44816966055
- Passing regression and selected-module quality checks: https://github.com/LuwnFM/psinka-bot/actions/runs/44816966000

These automatic edits do not prove all live Discord/provider/PostgreSQL paths work. The remaining warnings require a separate manual review, especially any changes that could alter game behavior. The PR must stay a draft.
