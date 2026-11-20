"""Check that extraction did not modify original command decorators or function bodies.

The baseline is the main branch (git fetch-depth: 0 in GitHub Actions).
This is deliberately structural, not a replacement for behavior tests.
"""

import ast
import copy
import subprocess
from pathlib import Path

ORIGINAL_FILE = "psinkamain.py"
# These modules retain strict structural equivalence. Intentionally rewritten
# modules are covered by behavioral persistence, dice and auction tests instead.
EXTRACTED_FILES = (
    "services/post_count_templates.py",
    "services/auction_lots.py",
    "services/dice.py",
    "services/mercenary_normalize.py",
    "services/jail_time.py",
)


class _AnnotationStyleNormalizer(ast.NodeTransformer):
    """Normalize type spelling only; never normalize executable statements."""

    _typing_aliases = {
        "Dict": "dict",
        "List": "list",
        "Tuple": "tuple",
        "Set": "set",
        "FrozenSet": "frozenset",
        "Type": "type",
    }

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id in self._typing_aliases:
            node.id = self._typing_aliases[node.id]
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "disnake":
            if node.attr in {"CommandInteraction", "ApplicationCommandInteraction"}:
                return ast.Name(id="ApplicationCommandInteraction", ctx=ast.Load())
            if node.attr == "MessageInteraction":
                return ast.Name(id="MessageInteraction", ctx=ast.Load())
        return node

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "Optional":
            return ast.BinOp(
                left=node.slice,
                op=ast.BitOr(),
                right=ast.Constant(value=None),
            )
        return node


def _canonical_ast(original: ast.AST, *, allow_added_annotations: bool = False) -> str:
    """Compare code, allowing only equivalent typing spellings.

    Optional[T] and T | None are equivalent in Python 3.10 and later.
    Function bodies, argument defaults, and decorators stay checked.
    """
    node = copy.deepcopy(original)
    normalizer = _AnnotationStyleNormalizer()
    for descendant in list(ast.walk(node)):
        if isinstance(descendant, ast.arg) and descendant.annotation is not None:
            descendant.annotation = normalizer.visit(descendant.annotation)
        elif isinstance(descendant, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if descendant.returns is not None:
                descendant.returns = normalizer.visit(descendant.returns)
        elif isinstance(descendant, ast.AnnAssign):
            descendant.annotation = normalizer.visit(descendant.annotation)
        elif isinstance(descendant, (ast.For, ast.AsyncFor, ast.comprehension)):
            # Ruff SIM118: iterating a dictionary equals iterating its .keys()
            # method. Normalize only iteration targets, never arbitrary calls.
            iterator = descendant.iter
            if (
                isinstance(iterator, ast.Call)
                and isinstance(iterator.func, ast.Attribute)
                and iterator.func.attr == "keys"
                and not iterator.args
                and not iterator.keywords
            ):
                descendant.iter = iterator.func.value
    if allow_added_annotations:
        # Type-only additions do not alter executable function behavior.
        # Command signatures are checked separately WITHOUT this relaxation.
        for descendant in ast.walk(node):
            if isinstance(descendant, ast.arg):
                descendant.annotation = None
            elif isinstance(descendant, (ast.FunctionDef, ast.AsyncFunctionDef)):
                descendant.returns = None
    return ast.dump(node, include_attributes=False)


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
    return subprocess.check_output(["git", "show", f"origin/main:{ORIGINAL_FILE}"], text=True)


def test_extracted_logic_matches_original_ast() -> None:
    """Ensure every moved function or class has the same executable AST."""
    original = definitions(source_from_main())
    for path in EXTRACTED_FILES:
        for name, node in definitions(Path(path).read_text(encoding="utf-8")).items():
            assert name in original, f"{name} is not in baseline main"
            assert _canonical_ast(node, allow_added_annotations=True) == _canonical_ast(
                original[name], allow_added_annotations=True
            ), f"Executable logic changed while extracting {name}"


def test_slash_command_contract_matches_main() -> None:
    """Protect the full Discord API, including original argument defaults.

    Name-only checks can miss a breaking change to parameter type, order,
    autocomplete binding, choices, or default values.
    """

    def command_contracts(source: str) -> dict[str, tuple[str, str]]:
        tree = ast.parse(source)
        return {
            node.name: (
                _canonical_ast(node.args),
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


def test_type_style_normalization_preserves_command_defaults() -> None:
    """Changing Optional to X | None is safe; changing a default is not."""
    original = ast.parse("def check(x: Optional[str] = None): return x").body[0]
    modern = ast.parse("def check(x: str | None = None): return x").body[0]
    changed = ast.parse("def check(x: str | None = 'changed'): return x").body[0]
    assert _canonical_ast(original) == _canonical_ast(modern)
    assert _canonical_ast(original) != _canonical_ast(changed)


def test_dictionary_iteration_style_does_not_hide_logic_changes() -> None:
    """Dictionary iteration spelling is equivalent; algorithm changes are not."""
    original = ast.parse("def check(values):\n    for value in values.keys():\n        print(value)").body[0]
    modern = ast.parse("def check(values):\n    for value in values:\n        print(value)").body[0]
    changed = ast.parse("def check(values):\n    for value in values:\n        print(str(value))").body[0]
    assert _canonical_ast(original) == _canonical_ast(modern)
    assert _canonical_ast(original) != _canonical_ast(changed)


def test_added_annotations_do_not_mask_changed_executable_logic() -> None:
    """Compare real bodies even when harmless type hints were introduced."""
    original = ast.parse("def f(value):\n    return value + 1").body[0]
    annotated = ast.parse("def f(value: int) -> int:\n    return value + 1").body[0]
    modified = ast.parse("def f(value: int) -> int:\n    return value + 2").body[0]
    assert _canonical_ast(original, allow_added_annotations=True) == _canonical_ast(
        annotated, allow_added_annotations=True
    )
    assert _canonical_ast(original, allow_added_annotations=True) != _canonical_ast(
        modified, allow_added_annotations=True
    )
