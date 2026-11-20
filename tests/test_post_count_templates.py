"""Regression tests for the extracted post-counting domain parser."""

from datetime import date, datetime, timezone

import pytest

from services.post_count_templates import (
    PC_ALL_FAMILIES,
    PCDateError,
    pc_compact,
    pc_damerau,
    pc_find_templates,
    pc_normalize_text,
    pc_parse_period,
    pc_template_mode,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ГМ-ПОСТ", "гмпост"),
        ("**ДРП-вердикт**", "дрпвердикт"),
        ("Полит_верд", "политверд"),
        ("  ГМ\u200bпост ", "гмпост"),
    ],
)
def test_normalization_and_aliases(raw: str, expected: str) -> None:
    assert pc_compact(raw) == expected
    assert pc_template_mode(raw) is not None


def test_unicode_and_transposition() -> None:
    assert pc_normalize_text("**ГМ\u200bПОСТ**") == "гмпост"
    assert pc_damerau("гмпсот", "гмпост") == 1


def test_period_uses_moscow_timezone_and_inclusive_end_date() -> None:
    period = pc_parse_period("01.01.2026", "03.01.2026")
    assert period.start_date == date(2026, 1, 1)
    assert period.end_date == date(2026, 1, 3)
    assert period.start_utc == datetime(2025, 12, 31, 21, tzinfo=timezone.utc)
    assert period.end_exclusive_utc == datetime(2026, 1, 3, 21, tzinfo=timezone.utc)
    assert not period.end_was_clamped


def test_invalid_start_date_rejected() -> None:
    with pytest.raises(PCDateError, match="начальная дата"):
        pc_parse_period("31.02.2026", "03.03.2026")


def test_end_date_clamped_to_last_day_of_month() -> None:
    period = pc_parse_period("01.02.2026", "31.02.2026")
    assert period.end_date == date(2026, 2, 28)
    assert period.end_was_clamped


def test_absent_template_yields_no_matches() -> None:
    assert pc_find_templates("Обычная реплика без RP-маркеров", PC_ALL_FAMILIES) == []
