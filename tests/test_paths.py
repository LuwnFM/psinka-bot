"""Filesystem lifecycle regression tests for existing bot installations."""

import importlib.util
import shutil
from pathlib import Path

from core import paths


def test_importing_path_constants_does_not_create_directories(tmp_path: Path) -> None:
    """Importing settings must be safe in read-only deployment environments."""
    isolated = tmp_path / "core" / "paths.py"
    isolated.parent.mkdir()
    shutil.copyfile(paths.__file__, isolated)
    spec = importlib.util.spec_from_file_location("isolated_bot_paths", isolated)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "logs").exists()
    assert not (tmp_path / "state").exists()


def test_explicit_startup_migrates_legacy_state_without_overwriting(tmp_path: Path, monkeypatch) -> None:
    """Old CSV/JSON and logs retain original bytes during first launch."""
    monkeypatch.setattr(paths, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(paths, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(paths, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(paths, "BOT_ERROR_LOG", tmp_path / "logs" / "bot_errors.log")
    monkeypatch.setattr(paths, "ANALYSIS_LOG_FILE", tmp_path / "logs" / "analysis_debug.log")
    monkeypatch.setattr(paths, "PENDING_TEST_LOG", tmp_path / "state" / "test_pending.csv")
    monkeypatch.setattr(paths, "POST_COUNT_SETTINGS_FILE", tmp_path / "state" / "post_count_settings.json")

    original = '{"guilds":{"123":{"roles":[11],"categories":[22]}}}'
    (tmp_path / "post_count_settings.json").write_text(original, encoding="utf-8")
    (tmp_path / "test_pending.csv").write_text(
        "provider,model,latency_ms,timestamp\nGroq,model-x,123,2026-01-01\n",
        encoding="utf-8",
    )
    paths.initialize_paths()
    assert paths.POST_COUNT_SETTINGS_FILE.read_text(encoding="utf-8") == original
    assert "model-x" in paths.PENDING_TEST_LOG.read_text(encoding="utf-8")
    assert not (tmp_path / "post_count_settings.json").exists()
    assert not (tmp_path / "test_pending.csv").exists()

    paths.POST_COUNT_SETTINGS_FILE.write_text("newer value", encoding="utf-8")
    (tmp_path / "post_count_settings.json").write_text("stale backup", encoding="utf-8")
    paths.initialize_paths()
    assert paths.POST_COUNT_SETTINGS_FILE.read_text(encoding="utf-8") == "newer value"
    assert (tmp_path / "post_count_settings.json").read_text(encoding="utf-8") == "stale backup"
