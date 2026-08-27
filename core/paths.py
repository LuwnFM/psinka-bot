from __future__ import annotations

import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"
STATE_DIR = ROOT_DIR / "state"

BOT_ERROR_LOG = LOG_DIR / "bot_errors.log"
ANALYSIS_LOG_FILE = LOG_DIR / "analysis_debug.log"
PENDING_TEST_LOG = STATE_DIR / "test_pending.csv"
POST_COUNT_SETTINGS_FILE = STATE_DIR / "post_count_settings.json"
MERCENARY_DB_FILE = DATA_DIR / "mercenary_command_database_v2.xlsx"
ENV_FILE = ROOT_DIR / ".env"


def _ensure_dirs() -> None:
    for directory in (DATA_DIR, LOG_DIR, STATE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def _migrate_legacy_file(source_name: str, destination: Path) -> None:
    """Best-effort migration of files that previously lived beside psinkamain.py."""
    source = ROOT_DIR / source_name
    if destination.exists() or not source.exists() or source == destination:
        return
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
    except OSError:
        # Runtime state must never prevent the bot from starting. If migration is
        # impossible (read-only FS, cross-device restrictions), the caller can
        # still create a fresh file at the normalized destination.
        pass


_ensure_dirs()
for _legacy_name, _destination in (
    ("bot_errors.log", BOT_ERROR_LOG),
    ("analysis_debug.log", ANALYSIS_LOG_FILE),
    ("test_pending.csv", PENDING_TEST_LOG),
    ("post_count_settings.json", POST_COUNT_SETTINGS_FILE),
):
    _migrate_legacy_file(_legacy_name, _destination)
