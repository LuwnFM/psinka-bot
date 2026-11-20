"""Pending AI model observations must be durable, never created during import."""

from repositories.pending_tests import PendingTestManager


def test_constructor_has_no_filesystem_side_effect(tmp_path) -> None:
    location = tmp_path / "nested" / "pending.csv"
    manager = PendingTestManager(str(location))
    assert not location.exists()
    assert manager.read_records() == []
    assert manager.get_pending_models() == []


def test_initialize_and_record_round_trip(tmp_path) -> None:
    location = tmp_path / "nested" / "pending.csv"
    manager = PendingTestManager(str(location))
    manager.initialize()
    assert location.read_text(encoding="utf-8").startswith("provider,model,latency_ms,timestamp")
    manager.log_success("Groq", "fast-model", 20)
    manager.log_success("Groq", "fast-model", 30)
    manager.log_success("OpenRouter", "other-model", 40)
    assert manager.get_pending_models() == [("Groq", "fast-model"), ("OpenRouter", "other-model")]
    assert manager.read_records() == [("Groq", "fast-model", 20), ("Groq", "fast-model", 30), ("OpenRouter", "other-model", 40)]
    assert manager.read_and_clear() == [("Groq", "fast-model", 20), ("Groq", "fast-model", 30), ("OpenRouter", "other-model", 40)]
    assert manager.get_pending_models() == []
    assert manager.read_records() == []


def test_log_success_without_explicit_initialize_preserves_header(tmp_path) -> None:
    location = tmp_path / "pending.csv"
    manager = PendingTestManager(str(location))
    manager.log_success("Groq", "fallback", 12)
    assert location.read_text(encoding="utf-8").splitlines()[0] == "provider,model,latency_ms,timestamp"


def test_clear_signals_filesystem_failure(tmp_path) -> None:
    """Never claim that the pending CSV was cleared when it was not."""
    manager = PendingTestManager(str(tmp_path))
    assert manager.clear() is False
