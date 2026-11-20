"""Structural types for post-count results shared by parsing and reports."""

from typing import TypedDict


class ChannelCounter(TypedDict):
    """Message count for one Discord channel."""

    id: int | None
    label: str
    messages: int


ChannelCounters = dict[str, ChannelCounter]


class SurfaceStats(TypedDict):
    """Occurrences and unique message counts for one spelling."""

    occurrences: int
    messages: int
    channels: ChannelCounters


class GroupStats(TypedDict):
    """Statistics for a canonical template, including all its surfaces."""

    canonical: str
    occurrences: int
    messages: int
    long: int
    short: int
    channels: ChannelCounters
    exact: SurfaceStats
    variants: dict[str, SurfaceStats]


class FamilyStats(TypedDict):
    """Aggregate message and template counts for one family."""

    messages: int
    occurrences: int
    long: int
    short: int
    channels: ChannelCounters
    groups: dict[str, GroupStats]


class TemplateMatchRecord(TypedDict):
    """Recognized spelling in the detailed TXT report."""

    family: str
    payload_key: str
    canonical: str
    exact: bool
    surface: str


class TemplateMessage(TypedDict):
    """One matching Discord message serialized for report generation."""

    id: str
    channel_id: str
    channel: str
    created_at: str
    jump_url: str
    content: str
    body_length: int | None
    length_kind: str | None
    matches: list[TemplateMatchRecord]


class CountResult(TypedDict):
    """One target channel's scanning output."""

    label: str
    channel_id: int | None
    matched: int
    scanned: int
    error: str | None
    families: dict[str, FamilyStats]
    lengths: dict[str, int]
    template_messages: list[TemplateMessage]
