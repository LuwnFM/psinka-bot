# Refactoring status — November 19, 2026

This branch is an **incremental**, unmerged refactor. It is **not** a complete AGENTS.md-compliant rewrite.

## Completed

- Extracted the post-counting template parser (periods, aliases, typo-tolerant prefixes, text normalization) into `services/post_count_templates.py`.
- Extracted persisted post-count settings normalization into `services/post_count_settings.py`.
- Extracted per-message post-count statistics and cross-channel reporting into `services/post_count_metrics.py` and `services/post_count_reporting.py`.
- Extracted auction text, nested embed flattening, price parsing, and author normalization into `services/auction_text.py`.
- Extracted new and ancient auction lot classification and bidder parsing into `services/auction_lots.py`.
- Extracted original dice parser and roll-output formatting into `services/dice.py` and `services/dice_format.py`, preserving all class and function ASTs; added seeded regression fixtures.
- Removed import-time `pip install --upgrade g4f` so dependencies are installed during deployment, not at module import.
- Moved PostgreSQL connection and table creation out of module import to the guarded startup path, after ORM models are defined.
- Replaced handwritten ZIP/XML Excel generation with `openpyxl`, with tests opening output XLSX files.
- Centralized typed environment settings in `core/config.py`.
- The entrypoint imports the same exported names, preserving command registration and original matching algorithms.
- Introduced isolated regression tests and GitHub Actions checks on Python 3.10 and 3.12.
- Added structural AST comparisons to the source on `origin/main`, guarding original function/class bodies and the 19 slash-command decorator contracts.
- These checks do **not** verify full Discord/PostgreSQL integration, runtime imports, or full compliance with Ruff/mypy.
- Original `main` remains unchanged. No production secrets are required for the isolated tests.

## Still required before production deployment

- Complete separation of AI-provider clients, auction/prison/mercenary workflows, storage, and Discord handlers.
- Replace synchronous database and HTTP operations in async handlers.
- Cover command behavior and persistent state with mocked Discord/PostgreSQL integration tests.
- Type annotate public APIs and pass Ruff and mypy for the **entire** application. These linters have **not** passed for the current legacy monolith.
- Complete full end-to-end integration testing: the current green CI checks isolated services, code structure, and syntax, not Discord production behavior.
- Verify no runtime regression on a staging Discord guild with test credentials.

**Do not merge until these checks and an integration review are complete.**
