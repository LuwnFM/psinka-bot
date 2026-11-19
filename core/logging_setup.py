"""Single runtime logging configuration for the bot and analysis diagnostics."""

import logging
from pathlib import Path


def configure_logging(error_log: str | Path, analysis_log: str | Path) -> None:
    """Set up handlers during startup, without mutating third-party logger setup."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    if not root.handlers:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)
    error_file = Path(error_log)
    error_file.parent.mkdir(parents=True, exist_ok=True)
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(error_file.resolve()) for h in root.handlers):
        handler = logging.FileHandler(error_file, encoding="utf-8", delay=True)
        handler.setFormatter(formatter)
        root.addHandler(handler)

    analysis = logging.getLogger("analysis_debug")
    analysis.setLevel(logging.INFO)
    if not analysis.handlers:
        file = Path(analysis_log)
        file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(file, mode="w", encoding="utf-8", delay=True)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        analysis.addHandler(handler)
