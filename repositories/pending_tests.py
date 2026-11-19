"""CSV-backed pending model observations, initialized only when needed."""

import csv
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

class PendingTestManager:
    def __init__(self, filename: str):
        """Hold the path without creating files during module import."""
        self.filename = filename

    def initialize(self) -> None:
        """Create the CSV header on application startup, never at import time."""
        path = Path(self.filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.stat().st_size == 0:
            with path.open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerow(["provider", "model", "latency_ms", "timestamp"])

    def log_success(self, provider: str, model: str, latency_ms: int):
        try:
            self.initialize()
            with open(self.filename, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([provider, model, latency_ms, datetime.now(timezone.utc).isoformat()])
        except Exception as e:
            logger.error(f"Ошибка записи во временный лог тестов: {e}")

    def read_records(self) -> List[Tuple[str, str, int]]:
        results = []
        if not os.path.exists(self.filename):
            return results
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if len(row) >= 3:
                        results.append((row[0], row[1], int(row[2])))
            return results
        except Exception as e:
            logger.error(f"Ошибка чтения временного лога: {e}")
            return []

    def clear(self):
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                f.write('provider,model,latency_ms,timestamp\n')
        except Exception as e:
            logger.error(f"Ошибка очистки временного лога: {e}")

    def read_and_clear(self) -> List[Tuple[str, str, int]]:
        results = self.read_records()
        if results:
            self.clear()
        return results

    def get_pending_models(self) -> List[Tuple[str, str]]:
        models = []
        if not os.path.exists(self.filename):
            return models
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)
                seen = set()
                for row in reader:
                    if len(row) >= 2:
                        key = (row[0], row[1])
                        if key not in seen:
                            models.append(key)
                            seen.add(key)
            return models
        except:
            return []


