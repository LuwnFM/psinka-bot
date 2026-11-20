"""Check that extraction did not modify original command decorators or function bodies.

The baseline is the main branch (git fetch-depth: 0 in GitHub Actions).
This is deliberately structural, not a replacement for behavior tests.
"""

import ast
import subprocess
from pathlib import Path

ORIGINAL_FILE = "psinkamain.py"
EXTRACTED_FILES = (
    "services/post_count_templates.py",
    "services/post_count_settings.py",
    "services/post_count_metrics.py",
    "services/post_count_reporting.py",
    "db/models.py",
    "services/auction_text.py",
    "services/auction_lots.py",
    "services/dice.py",
    "services/mercenary_normalize.py",
    "services/jail_time.py",
    "services/dice_format.py",
)


def definitions(source: str) -> dict[str, ast.AST]:
    """Return top-level function and class definitions indexed by name."""
    tree = ast.parse(source)
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def source_from_main() -> str:
    """Read the original entrypoint from main without importing bot dependencies."""
    return subprocess.check_output(
        ["git", "show", f"origin/main:{ORIGINAL_FILE}"], text=True
    )


def test_extracted_logic_matches_original_ast() -> None:
    """Ensure every moved function or class has the same executable AST."""
    original = definitions(source_from_main())
    for path in EXTRACTED_FILES:
        for name, node in definitions(Path(path).read_text(encoding="utf-8")).items():
            assert name in original, f"{name} is not in baseline main"
            assert ast.dump(node, include_attributes=False) == ast.dump(
                original[name], include_attributes=False
            ), f"Logic changed while extracting {name}"


def test_slash_command_contract_matches_main() -> None:
    """Protect the full Discord API, including original argument defaults.

    Name-only checks can miss a breaking change to parameter type, order,
    autocomplete binding, choices, or default values.
    """

    def command_contracts(source: str) -> dict[str, tuple[str, str]]:
        tree = ast.parse(source)
        return {
            node.name: (
                ast.dump(node.args, include_attributes=False),
                ast.dump(ast.Module(body=node.decorator_list, type_ignores=[]), include_attributes=False),
            )
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and any("slash_command" in ast.unparse(decorator) for decorator in node.decorator_list)
        }

    current = Path(ORIGINAL_FILE).read_text(encoding="utf-8")
    baseline = source_from_main()
    assert len(command_contracts(baseline)) == 19
    assert command_contracts(current) == command_contracts(baseline)


def test_discord_listener_bindings_match_main() -> None:
    """Do not silently lose reaction handlers or scheduled ready listeners."""

    def listeners(source: str) -> dict[str, tuple[str, ...]]:
        tree = ast.parse(source)
        registered: dict[str, tuple[str, ...]] = {}
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            decorators = tuple(
                ast.dump(item, include_attributes=False)
                for item in node.decorator_list
                if "bot.listen" in ast.unparse(item) or "bot.event" in ast.unparse(item)
            )
            if decorators:
                registered[node.name] = decorators
        return registered

    current = Path(ORIGINAL_FILE).read_text(encoding="utf-8")
    baseline = source_from_main()
    assert listeners(current) == listeners(baseline)
