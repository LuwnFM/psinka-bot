"""Durable CSV staging area for successful AI model probes."""

import csv
import logging
import os
import tempfile
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
HEADER = ["provider", "model", "latency_ms", "timestamp"]


class PendingTestManager:
    """Maintain temporary model observations without import-time file access."""

    def __init__(self, filename: str) -> None:
        """Store a path and serialize operations on this file within the process."""
        self.filename = filename
        self._lock = threading.RLock()

    def initialize(self) -> None:
        """Create the parent directory and header before the first write."""
        with self._lock:
            path = Path(self.filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or path.stat().st_size == 0:
                with path.open("w", newline="", encoding="utf-8") as stream:
                    csv.writer(stream).writerow(HEADER)

    def log_success(self, provider: str, model: str, latency_ms: int) -> None:
        """Append one model success observation for later import."""
        try:
            with self._lock:
                self.initialize()
                with Path(self.filename).open("a", newline="", encoding="utf-8") as stream:
                    csv.writer(stream).writerow(
                        [provider, model, latency_ms, datetime.now(timezone.utc).isoformat()]
                    )
        except OSError:
            logger.exception("Ошибка записи во временный лог тестов")

    def read_records(self) -> list[tuple[str, str, int]]:
        """Read valid saved observations, skipping incomplete CSV rows."""
        with self._lock:
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
        """Clear the entire file and report whether that operation succeeded."""
        try:
            with self._lock, Path(self.filename).open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerow(HEADER)
            return True
        except OSError:
            logger.exception("Ошибка очистки временного лога тестов")
            return False

    def acknowledge_records(self, records: list[tuple[str, str, int]]) -> bool:
        """Remove only committed observations, preserving newer concurrent writes.

        The transaction into the DB happens first. After it succeeds, this
        method atomically rewrites the CSV with only unprocessed rows left.
        Duplicate rows are accounted for individually rather than as a set.
        """
        if not records:
            return True

        with self._lock:
            path = Path(self.filename)
            if not path.exists():
                logger.error("Не удалось подтвердить перенос: временный CSV не найден")
                return False

            temporary_path: Path | None = None
            try:
                remaining = Counter(records)
                retained: list[list[str]] = []
                with path.open("r", newline="", encoding="utf-8") as stream:
                    reader = csv.reader(stream)
                    header = next(reader, HEADER)
                    for row in reader:
                        key: tuple[str, str, int] | None = None
                        if len(row) >= 3:
                            try:
                                key = (row[0], row[1], int(row[2]))
                            except ValueError:
                                key = None
                        if key is not None and remaining[key] > 0:
                            remaining[key] -= 1
                        else:
                            retained.append(row)

                if any(remaining.values()):
                    logger.error("Временный CSV изменился: не все перенесённые записи найдены")
                    return False

                with tempfile.NamedTemporaryFile(
                    mode="w",
                    newline="",
                    encoding="utf-8",
                    dir=path.parent,
                    prefix=".pending-",
                    suffix=".tmp",
                    delete=False,
                ) as stream:
                    temporary_path = Path(stream.name)
                    writer = csv.writer(stream)
                    writer.writerow(header)
                    writer.writerows(retained)
                    stream.flush()
                    os.fsync(stream.fileno())

                os.replace(temporary_path, path)
                return True
            except (OSError, UnicodeError, csv.Error):
                logger.exception("Не удалось подтвердить перенос временных результатов")
                return False
            finally:
                if temporary_path is not None:
                    try:
                        temporary_path.unlink(missing_ok=True)
                    except OSError:
                        logger.warning("Не удалось очистить временный файл %s", temporary_path)

    def read_and_clear(self) -> list[tuple[str, str, int]]:
        """Read observations and acknowledge precisely those entries."""
        results = self.read_records()
        if results:
            self.acknowledge_records(results)
        return results

    def get_pending_models(self) -> list[tuple[str, str]]:
        """Return ordered distinct provider/model pairs from the pending file."""
        with self._lock:
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
