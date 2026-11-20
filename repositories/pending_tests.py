"""Durable CSV staging area for successful AI model probes."""

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class PendingTestManager:
    """Manage temporary model observations without import-time file access."""

    def __init__(self, filename: str) -> None:
        """Store the CSV path without creating it during construction."""
        self.filename = filename

    def initialize(self) -> None:
        """Create the parent directory and header before the first write."""
        path = Path(self.filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.stat().st_size == 0:
            with path.open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerow(["provider", "model", "latency_ms", "timestamp"])

    def log_success(self, provider: str, model: str, latency_ms: int) -> None:
        """Append one provider/model latency observation for later import."""
        try:
            self.initialize()
            with Path(self.filename).open("a", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerow(
                    [provider, model, latency_ms, datetime.now(timezone.utc).isoformat()]
                )
        except OSError:
            logger.exception("Ошибка записи во временный лог тестов")

    def read_records(self) -> list[tuple[str, str, int]]:
        """Read saved observations, skipping incomplete rows."""
        path = Path(self.filename)
        if not path.exists():
            return []
        try:
            with path.open("r", newline="", encoding="utf-8") as stream:
                reader = csv.reader(stream)
                next(reader, None)
                return [
                    (row[0], row[1], int(row[2]))
                    for row in reader
                    if len(row) >= 3 and row[2].strip().lstrip("-").isdigit()
                ]
        except (OSError, UnicodeError, csv.Error):
            logger.exception("Ошибка чтения временного лога тестов")
            return []

    def clear(self) -> bool:
        """Truncate the log and confirm success instead of hiding disk errors."""
        try:
            with Path(self.filename).open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerow(["provider", "model", "latency_ms", "timestamp"])
            return True
        except OSError:
            logger.exception("Ошибка очистки временного лога тестов")
            return False

    def read_and_clear(self) -> list[tuple[str, str, int]]:
        """Read current records and clear the CSV only when records were found."""
        results = self.read_records()
        if results:
            self.clear()
        return results

    def get_pending_models(self) -> list[tuple[str, str]]:
        """Return ordered, distinct provider/model pairs from the pending file."""
        path = Path(self.filename)
        if not path.exists():
            return []
        try:
            with path.open("r", newline="", encoding="utf-8") as stream:
                reader = csv.reader(stream)
                next(reader, None)
                seen: set[tuple[str, str]] = set()
                results: list[tuple[str, str]] = []
                for row in reader:
                    if len(row) < 2:
                        continue
                    key = (row[0], row[1])
                    if key not in seen:
                        seen.add(key)
                        results.append(key)
                return results
        except (OSError, UnicodeError, csv.Error):
            logger.exception("Ошибка чтения списка ожидающих моделей")
            return []
