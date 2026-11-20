"""Logging initialization has no filesystem side effects before startup."""

import logging

from core.logging_setup import configure_logging


def test_logging_configuration_is_explicit_and_idempotent(tmp_path) -> None:
    err = tmp_path / "log" / "errors.log"
    analysis = tmp_path / "log" / "analysis.log"
    assert not err.exists() and not analysis.exists()
    root = logging.getLogger()
    before = list(root.handlers)
    diagnostic = logging.getLogger("analysis_debug")
    diagnostic_before = list(diagnostic.handlers)
    try:
        configure_logging(err, analysis)
        configure_logging(err, analysis)
        assert (
            sum(
                1
                for handler in root.handlers
                if isinstance(handler, logging.FileHandler) and handler.baseFilename == str(err.resolve())
            )
            == 1
        )
        assert (
            sum(
                1
                for handler in diagnostic.handlers
                if isinstance(handler, logging.FileHandler)
                and handler.baseFilename == str(analysis.resolve())
            )
            == 1
        )
        diagnostic.info("log test")
        assert "log test" in analysis.read_text(encoding="utf-8")
    finally:
        for handler in root.handlers:
            if handler not in before:
                root.removeHandler(handler)
                handler.close()
        for handler in diagnostic.handlers:
            if handler not in diagnostic_before:
                diagnostic.removeHandler(handler)
                handler.close()
