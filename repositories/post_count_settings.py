"""Atomic JSON persistence for post-count preferences without import-time I/O."""

import asyncio
import json
import logging
import os
from pathlib import Path

from services.post_count_settings import pc_empty_settings, pc_normalize_settings

logger = logging.getLogger(__name__)


def load_settings(path: str | Path) -> dict:
    """Return validated settings, falling back to an empty document on I/O errors."""
    file = Path(path)
    if not file.exists():
        return pc_empty_settings()
    try:
        with file.open("r", encoding="utf-8") as stream:
            return pc_normalize_settings(json.load(stream))
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.exception("Не удалось прочитать настройки подсчёта из %s", path)
        return pc_empty_settings()


def write_settings(path: str | Path, data: dict) -> None:
    """Atomically replace settings file after flushing and syncing the temp file."""
    filename = Path(path)
    filename.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(filename) + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, filename)


class PCSettingsStore:
    """Concurrency-safe guild preferences, persisted after every mutation."""

    def __init__(self, filename: str) -> None:
        """Create in-memory defaults without reading files or creating directories."""
        self.filename = filename
        self.data = pc_empty_settings()
        self.dirty = False
        self.lock = asyncio.Lock()

    def initialize(self) -> None:
        """Load saved guild configuration during the bot startup lifecycle."""
        self.data = load_settings(self.filename)
        self.dirty = False

    def _guild_data(self, guild_id: int) -> dict:
        guilds = self.data.setdefault("guilds", {})
        return guilds.setdefault(str(guild_id), {"categories": [], "roles": []})

    def values(self, guild_id: int, key: str) -> set[int]:
        """Return the configured category/role IDs for a guild."""
        guild_data = self._guild_data(guild_id)
        return {int(value) for value in guild_data.get(key, [])}

    async def _save_locked(self) -> bool:
        try:
            await asyncio.to_thread(write_settings, self.filename, self.data)
        except (OSError, TypeError, ValueError):
            self.dirty = True
            logger.exception("Не удалось записать настройки подсчёта в %s", self.filename)
            return False
        self.dirty = False
        return True

    async def _modify(self, guild_id: int, key: str, desired: set[int]) -> None:
        guild_data = self._guild_data(guild_id)
        guild_data[key] = sorted(desired)
        self.dirty = True
        if not await self._save_locked():
            raise OSError(f"не удалось записать {self.filename}")

    async def add(self, guild_id: int, key: str, value_id: int) -> bool:
        """Insert a unique role/category ID and persist it."""
        async with self.lock:
            values = self.values(guild_id, key)
            if value_id in values:
                return False
            values.add(value_id)
            await self._modify(guild_id, key, values)
            return True

    async def remove(self, guild_id: int, key: str, value_id: int) -> bool:
        """Remove a configured ID, returning False if absent."""
        async with self.lock:
            values = self.values(guild_id, key)
            if value_id not in values:
                return False
            values.remove(value_id)
            await self._modify(guild_id, key, values)
            return True

    async def clear(self, guild_id: int, key: str) -> int:
        """Remove all configured IDs and return the previous count."""
        async with self.lock:
            values = self.values(guild_id, key)
            if not values:
                return 0
            await self._modify(guild_id, key, set())
            return len(values)

    async def flush_if_dirty(self) -> bool:
        """Retry pending writes during the periodic flush cycle."""
        async with self.lock:
            if not self.dirty:
                return True
            return await self._save_locked()
