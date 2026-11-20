"""Persisted post-count configuration must remain backward compatible."""

from services.post_count_settings import pc_empty_settings, pc_normalize_settings


def test_defaults_for_missing_or_corrupt_payload() -> None:
    assert pc_empty_settings() == {"guilds": {}}
    for value in (None, [], "bad", {"guilds": []}):
        assert pc_normalize_settings(value) == {"guilds": {}}


def test_guild_ids_and_role_ids_are_sanitized() -> None:
    data = {
        "guilds": {
            "123": {"categories": ["3", 3, -1, "abc"], "roles": [7, 2, 7]},
            "invalid": {"roles": [4]},
            "456": "invalid",
        }
    }
    assert pc_normalize_settings(data) == {
        "guilds": {
            "123": {"categories": [3], "roles": [2, 7]},
        }
    }


def test_unknown_settings_keys_are_not_persisted() -> None:
    data = {"guilds": {"99": {"categories": [4], "roles": [], "unknown": "ignored"}}}
    assert pc_normalize_settings(data) == {"guilds": {"99": {"categories": [4], "roles": []}}}
