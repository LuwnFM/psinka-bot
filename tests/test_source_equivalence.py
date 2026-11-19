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
    "services/auction_text.py",
    "services/auction_lots.py",
    "services/dice.py",
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
    """Guard registration names, parameter metadata, and decorators."""
    def commands(source: str) -> dict[str, list[str]]:
        tree = ast.parse(source)
        return {
            node.name: [ast.dump(d, include_attributes=False) for d in node.decorator_list]
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and any("slash_command" in ast.unparse(d) for d in node.decorator_list)
        }

    current = Path(ORIGINAL_FILE).read_text(encoding="utf-8")
    baseline = source_from_main()
    assert len(commands(baseline)) == 19
    assert commands(current) == commands(baseline)
