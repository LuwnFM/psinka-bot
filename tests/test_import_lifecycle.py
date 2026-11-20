"""Import lifecycle safeguards: no package installs or DB writes at import time."""

import ast
from pathlib import Path


def test_db_is_only_initialized_inside_guarded_entrypoint() -> None:
    source = Path("psinkamain.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    module_calls = [
        node
        for statement in tree.body
        for node in ast.walk(statement)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "init_db"
        and not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    # The guarded __main__ block is the only permitted module-scope caller.
    guarded = [
        node
        for statement in tree.body
        if isinstance(statement, ast.If) and "__main__" in ast.unparse(statement.test)
        for node in ast.walk(statement)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "init_db"
    ]
    assert len(module_calls) == len(guarded) == 1


def test_runtime_never_installs_dependencies() -> None:
    source = Path("psinkamain.py").read_text(encoding="utf-8")
    assert "_upgrade_g4f_before_import" not in source
    assert "subprocess.run" not in source
