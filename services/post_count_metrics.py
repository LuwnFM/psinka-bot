"""Pure per-message post counting, grouping and length classification."""

from datetime import datetime, timezone

from services.post_count_templates import (
    pc_find_templates,
    pc_length_enabled_for_family,
    pc_normalize_text,
    pc_template_body_length,
)

PC_LONG_POST_MIN_CHARS = 300

def pc_channel_counter_add(counter, channel_id, label, amount=1):
    key = str(channel_id) if channel_id is not None else f"label:{label}"
    item = counter.setdefault(
        key,
        {
            "id": int(channel_id) if channel_id is not None else None,
            "label": str(label or "неизвестный канал"),
            "messages": 0,
        },
    )
    item["messages"] += int(amount)


def pc_empty_surface_stats():
    return {
        "occurrences": 0,
        "messages": 0,
        "channels": {},
    }


def pc_empty_group(canonical):
    return {
        "canonical": canonical,
        "occurrences": 0,
        "messages": 0,
        # Для ГМ это отдельная статистика длины конкретной арки/метки.
        # Общая статистика семейства выше при этом сохраняется без изменений.
        "long": 0,
        "short": 0,
        "channels": {},
        "exact": pc_empty_surface_stats(),
        "variants": {},
    }


def pc_empty_result(label, families, channel_id=None):
    result = {
        "label": label,
        "channel_id": int(channel_id) if channel_id is not None else None,
        "matched": 0,
        "scanned": 0,
        "error": None,
        "families": {},
        # Общая длина считается только для семейств, разрешённых
        # PC_COUNT_LENGTH_FOR_ALL_TEMPLATES.
        "lengths": {"long": 0, "short": 0},
        # Полные записи нужны только для подробного TXT-отчёта.
        "template_messages": [],
    }
    if families:
        result["families"] = {
            family: {
                "messages": 0,
                "occurrences": 0,
                "long": 0,
                "short": 0,
                "channels": {},
                "groups": {},
            }
            for family in families
        }
    return result


def pc_iso_datetime(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value or "")


def pc_apply_content(
    result,
    content,
    word_pattern,
    families,
    *,
    message_id=None,
    channel_id=None,
    guild_id=None,
    created_at=None,
    jump_url=None,
):
    """Проверяет одно сообщение уже выбранного пользователя."""
    result["scanned"] += 1
    content = content or ""

    if families:
        matches = pc_find_templates(content, families)
        if not matches:
            return

        result["matched"] += 1
        message_families = {match.family for match in matches}
        channel_id = (
            int(channel_id)
            if channel_id is not None
            else result.get("channel_id")
        )
        channel_label = result.get("label") or "неизвестный канал"

        length_families = {
            family
            for family in message_families
            if pc_length_enabled_for_family(family)
        }
        body_length = None
        length_kind = None

        if length_families:
            body_length = pc_template_body_length(content, matches)
            length_kind = (
                "long"
                if body_length >= PC_LONG_POST_MIN_CHARS
                else "short"
            )
            # Одно сообщение учитывается в общей статистике длины один раз,
            # даже если содержит несколько учитываемых семейств.
            result["lengths"][length_kind] += 1

        group_message_keys = set()
        surface_message_keys = set()
        record_matches = []

        for match in matches:
            family_data = result["families"][match.family]
            family_data["occurrences"] += 1

            group = family_data["groups"].setdefault(
                match.payload_key,
                pc_empty_group(match.canonical),
            )
            group["occurrences"] += 1
            group_message_keys.add((match.family, match.payload_key))

            if match.exact_surface:
                surface = group["exact"]
                surface["occurrences"] += 1
                surface_message_keys.add(
                    (match.family, match.payload_key, "exact", "")
                )
                surface_name = match.canonical
            else:
                surface = group["variants"].setdefault(
                    match.raw_variant,
                    pc_empty_surface_stats(),
                )
                surface["occurrences"] += 1
                surface_message_keys.add(
                    (
                        match.family,
                        match.payload_key,
                        "variant",
                        match.raw_variant,
                    )
                )
                surface_name = match.raw_variant

            record_matches.append({
                "family": match.family,
                "payload_key": match.payload_key,
                "canonical": match.canonical,
                "exact": bool(match.exact_surface),
                "surface": surface_name,
            })

        # Сообщение в статистике семейства и канала считается один раз.
        for family in message_families:
            family_data = result["families"][family]
            family_data["messages"] += 1
            pc_channel_counter_add(
                family_data["channels"],
                channel_id,
                channel_label,
            )

            if (
                length_kind is not None
                and pc_length_enabled_for_family(family)
            ):
                family_data[length_kind] += 1

        # Сообщение в каждой канонической группе считается один раз,
        # даже если одинаковая метка повторена несколько раз.
        for family, payload_key in group_message_keys:
            group = result["families"][family]["groups"][payload_key]
            group["messages"] += 1
            if length_kind is not None and pc_length_enabled_for_family(family):
                group[length_kind] += 1
            pc_channel_counter_add(
                group["channels"],
                channel_id,
                channel_label,
            )

        # То же правило применяется отдельно к точному написанию
        # и к каждой фактической вариации.
        for family, payload_key, surface_kind, surface_name in surface_message_keys:
            group = result["families"][family]["groups"][payload_key]
            if surface_kind == "exact":
                surface = group["exact"]
            else:
                surface = group["variants"][surface_name]
            surface["messages"] += 1
            pc_channel_counter_add(
                surface["channels"],
                channel_id,
                channel_label,
            )

        if jump_url is None and guild_id and channel_id and message_id:
            jump_url = (
                f"https://discord.com/channels/"
                f"{guild_id}/{channel_id}/{message_id}"
            )

        result["template_messages"].append({
            "id": str(message_id or ""),
            "channel_id": str(channel_id or ""),
            "channel": channel_label,
            "created_at": pc_iso_datetime(created_at),
            "jump_url": str(jump_url or ""),
            "content": content,
            "body_length": body_length,
            "length_kind": length_kind,
            "matches": record_matches,
        })

    elif word_pattern.search(pc_normalize_text(content)):
        result["matched"] += 1


