"""Protect AI routing against late-binding model IDs across cancelled worker threads."""

import ast
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


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


def test_g4f_worker_keeps_provider_and_request_after_loop_moves(monkeypatch) -> None:
    """The synchronous g4f fallback freezes provider and request options."""
    functions = [
        node for node in _sync_call_nodes()
        if any(argument.arg == "provider_class" for argument in node.args.args)
    ]
    assert len(functions) == 1

    recorded: list[tuple[str | None, dict]] = []

    class FakeClient:
        def __init__(self, provider=None) -> None:
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: recorded.append((provider, kwargs))
                )
            )

    package = ModuleType("g4f")
    package.__path__ = []
    module = ModuleType("g4f.client")
    module.Client = FakeClient
    monkeypatch.setitem(sys.modules, "g4f", package)
    monkeypatch.setitem(sys.modules, "g4f.client", module)

    namespace = {"provider_class": "first-provider", "kwargs": {"model": "first-model"}}
    target = ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[]))
    exec(compile(target, "<isolated-g4f-worker>", "exec"), namespace)
    namespace["provider_class"] = "next-provider"
    namespace["kwargs"] = {"model": "next-model"}
    namespace["sync_call"]()
    assert recorded == [("first-provider", {"model": "first-model"})]
