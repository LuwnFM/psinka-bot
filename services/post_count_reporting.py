"""Pure aggregation and public summary formatting for post-count statistics."""

from collections.abc import Iterable, Sequence
from typing import Protocol

from services.post_count_metrics import pc_empty_group, pc_empty_surface_stats
from services.post_count_templates import PCPeriod
from services.post_count_types import (
    ChannelCounters,
    ChannelCounter,
    CountResult,
    FamilyStats,
    SurfaceStats,
    TemplateMessage,
)
from services.post_count_templates import PC_LABELS, pc_length_enabled_for_family

PC_PUBLIC_REPORT_CHUNK_CHARS = 3900


class ReportUser(Protocol):
    """Only the properties required from a Discord user."""

    @property
    def id(self) -> int:
        """Discord snowflake ID."""

    @property
    def mention(self) -> str:
        """Discord mention string."""


def pc_merge_channel_counters(target: ChannelCounters, source: ChannelCounters) -> None:
    for key, item in (source or {}).items():
        current = target.setdefault(
            key,
            {
                "id": item.get("id"),
                "label": item.get("label") or "неизвестный канал",
                "messages": 0,
            },
        )
        current["messages"] += int(item.get("messages", 0))


def pc_merge_surface_stats(target: SurfaceStats, source: SurfaceStats) -> None:
    target["occurrences"] += int(source.get("occurrences", 0))
    target["messages"] += int(source.get("messages", 0))
    pc_merge_channel_counters(
        target["channels"],
        source.get("channels", {}),
    )


def pc_merge_stats(
    results: Sequence[CountResult], families: Sequence[str]
) -> dict[str, FamilyStats]:
    merged: dict[str, FamilyStats] = {
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

    for result in results:
        for family in families:
            source = result["families"].get(family)
            if source is None:
                continue
            target = merged[family]
            target["messages"] += int(source.get("messages", 0))
            target["occurrences"] += int(source.get("occurrences", 0))
            target["long"] += int(source.get("long", 0))
            target["short"] += int(source.get("short", 0))
            pc_merge_channel_counters(
                target["channels"],
                source.get("channels", {}),
            )

            for key, source_group in source["groups"].items():
                group = target["groups"].setdefault(
                    key,
                    pc_empty_group(source_group["canonical"]),
                )
                group["occurrences"] += int(source_group.get("occurrences", 0))
                group["messages"] += int(source_group.get("messages", 0))
                group["long"] += int(source_group.get("long", 0))
                group["short"] += int(source_group.get("short", 0))
                pc_merge_channel_counters(
                    group["channels"],
                    source_group.get("channels", {}),
                )
                pc_merge_surface_stats(
                    group["exact"],
                    source_group["exact"],
                )

                for variant, source_variant in source_group["variants"].items():
                    variant_target = group["variants"].setdefault(
                        variant,
                        pc_empty_surface_stats(),
                    )
                    pc_merge_surface_stats(
                        variant_target,
                        source_variant,
                    )

    return merged


def pc_merge_lengths(results: Sequence[CountResult]) -> dict[str, int]:
    return {
        "long": sum(item.get("lengths", {}).get("long", 0) for item in results),
        "short": sum(item.get("lengths", {}).get("short", 0) for item in results),
    }


def pc_collect_template_records(results: Sequence[CountResult]) -> list[TemplateMessage]:
    records: list[TemplateMessage] = []
    seen = set()

    for result in results:
        for record in result.get("template_messages", []):
            identity = (
                record.get("id")
                or record.get("jump_url")
                or (f"{record.get('channel_id')}:{record.get('created_at')}:{len(records)}")
            )
            if identity in seen:
                continue
            seen.add(identity)
            records.append(record)

    return records


def pc_percent(part: int, total: int) -> float:
    return (part * 100.0 / total) if total else 0.0


def pc_public_clip(value: object, limit: int = 240) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 16)] + "… [полностью в TXT]"


def pc_sorted_channels(channels: ChannelCounters | None) -> list[ChannelCounter]:
    return sorted(
        (channels or {}).values(),
        key=lambda item: (
            -int(item.get("messages", 0)),
            str(item.get("label") or "").casefold(),
            str(item.get("id") or ""),
        ),
    )


def pc_channel_report_lines(
    channels: ChannelCounters | None, indent: str = "  "
) -> list[str]:
    rendered = []
    for item in pc_sorted_channels(channels):
        channel_id = item.get("id")
        label = pc_public_clip(item.get("label"), 220)
        location = f"<#{channel_id}> — {label}" if channel_id else label
        rendered.append(f"{indent}• `{item.get('messages', 0)}` — {location}")
    return rendered or [f"{indent}• Совпадений нет."]


def pc_template_channel_report_lines(
    stats: dict[str, FamilyStats], families: Sequence[str]
) -> list[str]:
    """
    Формирует публичную часть шаблонного отчёта.

    В Discord показываются только:
    - общая статистика каждого семейства;
    - распределение семейства по каналам;
    - каждый канонический шаблон;
    - распределение канонического шаблона по каналам.

    Количество меток, точные написания, опечатки и другие фактические
    варианты выводятся только в подробном TXT-отчёте.
    """
    lines = [
        "Числа возле каналов — количество сообщений.",
        "",
    ]

    for family in families:
        data = stats[family]
        messages = int(data.get("messages", 0))
        groups_count = len(data.get("groups", {}))
        channels_count = len(data.get("channels", {}))

        if messages == 0:
            lines.extend(
                [
                    f"## {PC_LABELS[family]} — совпадений нет.",
                    "",
                ]
            )
            continue

        lines.append(
            f"## {PC_LABELS[family]} — сообщений `{messages}`, "
            f"шаблонов `{groups_count}`, каналов `{channels_count}`"
        )

        if pc_length_enabled_for_family(family):
            long_count = int(data.get("long", 0))
            short_count = int(data.get("short", 0))
            total_length = long_count + short_count
            lines.append(
                f"**Длина без меток:** длинных "
                f"`{long_count}` (`{pc_percent(long_count, total_length):.1f}%`), "
                f"коротких `{short_count}` "
                f"(`{pc_percent(short_count, total_length):.1f}%`)."
            )

        lines.append("**Все сообщения семейства по каналам:**")
        lines.extend(pc_channel_report_lines(data.get("channels", {})))

        groups = sorted(
            data.get("groups", {}).values(),
            key=lambda item: (
                -int(item.get("messages", 0)),
                -int(item.get("occurrences", 0)),
                str(item.get("canonical") or "").casefold(),
            ),
        )

        for group in groups:
            canonical = pc_public_clip(group.get("canonical"), 300)
            group_channels = group.get("channels", {})
            lines.extend(
                [
                    "",
                    (f"### {canonical} — сообщений `{group['messages']}`, каналов `{len(group_channels)}`"),
                ]
            )
            if pc_length_enabled_for_family(family):
                group_long = int(group.get("long", 0))
                group_short = int(group.get("short", 0))
                group_total = group_long + group_short
                lines.append(
                    f"**Длина по арке:** длинных `{group_long}` "
                    f"(`{pc_percent(group_long, group_total):.1f}%`), "
                    f"коротких `{group_short}` "
                    f"(`{pc_percent(group_short, group_total):.1f}%`)."
                )
            lines.append("**По каналам:**")
            lines.extend(pc_channel_report_lines(group_channels))

        lines.append("")

    return lines


def pc_template_public_report_lines(
    user: ReportUser,
    mode_value: str,
    period: PCPeriod,
    matched: int,
    scanned: int,
    successful_targets: int,
    total_targets: int,
    stats: dict[str, FamilyStats],
    families: Sequence[str],
    elapsed: float,
    extra_notes: Iterable[str] | None = None,
) -> list[str]:
    """Объединяет итоговую сводку и распределение по каналам."""
    lines = [
        f"**Пользователь:** {user.mention} (`{user.id}`)",
        f"**Режим:** `{str(mode_value)[:200]}`",
        (f"**Период (МСК):** `{period.start_date:%d.%m.%Y}` — `{period.end_date:%d.%m.%Y}` включительно"),
        (
            f"**Итог:** найдено сообщений `"
            f"{matched}` • проверено сообщений пользователя `{scanned}` • "
            f"каналов/веток успешно `{successful_targets}/{total_targets}`"
        ),
        "",
    ]

    lines.extend(pc_template_channel_report_lines(stats, families))

    for note in extra_notes or ():
        if note:
            lines.append(str(note))

    lines.append(f"Время выполнения: `{elapsed:.1f} сек.`")
    return lines


def pc_split_lines_for_discord(
    lines: Iterable[str],
    max_chars: int = PC_PUBLIC_REPORT_CHUNK_CHARS,
) -> list[str]:
    chunks = []
    current: list[str] = []
    current_size = 0

    for raw_line in lines:
        line = str(raw_line or "")

        # Динамические названия выше заранее ограничены, поэтому эта ветка —
        # последняя защита от патологически длинной строки.
        if len(line) > max_chars:
            line = pc_public_clip(line, max_chars - 4)

        added = len(line) + (1 if current else 0)
        if current and current_size + added > max_chars:
            chunks.append("\n".join(current))
            current = [line]
            current_size = len(line)
        else:
            current.append(line)
            current_size += added

    if current:
        chunks.append("\n".join(current))

    return chunks
