"""Regression tests for atomic and concurrent post-count settings repository."""

import asyncio
import json
from pathlib import Path

import pytest

from repositories.post_count_settings import PCSettingsStore


def test_settings_constructor_never_touches_disk(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "guilds.json"
    store = PCSettingsStore(str(path))
    assert store.values(12, "roles") == set()
    assert not path.exists()


@pytest.mark.asyncio
async def test_add_remove_clear_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "guilds.json"
    store = PCSettingsStore(str(path))
    store.initialize()
    assert await store.add(123, "categories", 50) is True
    assert await store.add(123, "categories", 50) is False
    assert await store.add(123, "roles", 10) is True
    assert await store.add(123, "roles", 20) is True
    assert await store.remove(123, "roles", 99) is False
    assert await store.remove(123, "roles", 20) is True
    assert store.values(123, "roles") == {10}
    assert await store.clear(123, "roles") == 1
    assert await store.clear(123, "roles") == 0
    assert await store.flush_if_dirty() is True
    assert not store.dirty
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["guilds"]["123"] == {"categories": [50], "roles": []}
    restarted = PCSettingsStore(str(path))
    restarted.initialize()
    assert restarted.values(123, "categories") == {50}


@pytest.mark.asyncio
async def test_concurrent_changes_are_serialized(tmp_path: Path) -> None:
    store = PCSettingsStore(str(tmp_path / "guilds.json"))
    await asyncio.gather(*(store.add(10, "roles", value) for value in range(1, 13)))
    assert store.values(10, "roles") == set(range(1, 13))
    restarted = PCSettingsStore(store.filename)
    restarted.initialize()
    assert restarted.values(10, "roles") == set(range(12))


def test_malformed_json_falls_back_to_empty(tmp_path: Path) -> None:
    path = tmp_path / "guilds.json"
    path.write_text("{ invalid", encoding="utf-8")
    store = PCSettingsStore(str(path))
    store.initialize()
    assert store.data == {"guilds": {}}
