"""Validation and normalization of persisted post-counting settings."""

from typing import Any

GuildPostCountSettings = dict[str, list[int]]
PostCountSettings = dict[str, dict[str, GuildPostCountSettings]]



def pc_empty_settings() -> PostCountSettings:
    return {"guilds": {}}


def pc_normalize_settings(data: Any) -> PostCountSettings:
    if not isinstance(data, dict):
        return pc_empty_settings()

    guilds = data.get("guilds")
    if not isinstance(guilds, dict):
        return pc_empty_settings()

    normalized: PostCountSettings = {"guilds": {}}
    for guild_id, raw_guild in guilds.items():
        if not str(guild_id).isdigit() or not isinstance(raw_guild, dict):
            continue

        guild_data: GuildPostCountSettings = {"categories": [], "roles": []}
        for key in ("categories", "roles"):
            raw_values = raw_guild.get(key, [])
            if not isinstance(raw_values, list):
                continue
            values: set[int] = set()
            for value in raw_values:
                try:
                    value_id = int(value)
                except (TypeError, ValueError):
                    continue
                if value_id > 0:
                    values.add(value_id)
            guild_data[key] = sorted(values)

        normalized["guilds"][str(guild_id)] = guild_data

    return normalized
