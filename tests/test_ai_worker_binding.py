"""Protect AI routing against late-binding model IDs across cancelled worker threads."""

import ast
from pathlib import Path
from types import SimpleNamespace


def _sync_call_nodes() -> list[ast.FunctionDef]:
    tree = ast.parse(Path("psinkamain.py").read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "sync_call"
    ]


def test_all_provider_worker_closures_bind_loop_parameters() -> None:
    """A worker may still run after wait_for cancels its awaiting coroutine."""
    functions = _sync_call_nodes()
    assert len(functions) == 3
    bound_names = [
        {argument.arg for argument in function.args.args[-len(function.args.defaults):]}
        for function in functions
    ]
    assert {"provider_class", "kwargs"} in bound_names
    assert sum("model" in names for names in bound_names) == 2


def test_fallback_model_workers_keep_their_original_model() -> None:
    """Executing a queued model call must use the model at scheduling time."""
    calls: list[dict] = []
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs))
        )
    )
    for function in _sync_call_nodes():
        if not any(arg.arg == "model" for arg in function.args.args):
            continue
        module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        namespace = {"client": client, "model": "original", "messages": []}
        exec(compile(module, "<isolated-ai-worker>", "exec"), namespace)
        namespace["model"] = "next-fallback"
        namespace["sync_call"]()
        assert calls[-1]["model"] == "original"


def test_batch_request_closure_binds_prompt_before_next_iteration() -> None:
    tree = ast.parse(Path("psinkamain.py").read_text(encoding="utf-8"))
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "try_request"
    ]
    assert len(functions) == 1
    default_args = {arg.arg for arg in functions[0].args.args[-len(functions[0].args.defaults):]}
    assert "user_prompt" in default_args
