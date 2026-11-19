"""Timezone normalization for persisted jail deadlines."""

from datetime import datetime, timezone

def normalize_jail_datetime(value: datetime) -> datetime:
    """Приводит дату к UTC с часовым поясом."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


