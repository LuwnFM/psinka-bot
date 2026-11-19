"""Seeded regression tests for author-defined DiceParser semantics."""

import random

import pytest

from services.dice import DiceParser
from services.dice_format import _dice_paginate, _dice_result_block


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("1d6", [6.0]),
        ("2d6+3", [10.0]),
        ("attack", [4.0]),
        ("4d6 k3", [13.0]),
        ("2d10 r2+1d6 e6+3", [14.0]),
        ("1d20+5; 2d6+1d4", [9.0, 10.0]),
    ],
)
def test_seeded_dice_total_matches_author_rules(formula: str, expected: list[float]) -> None:
    random.seed(42)
    assert [result.total for result in DiceParser().parse(formula)] == expected


def test_dndstats_returns_six_independent_results() -> None:
    random.seed(42)
    results = DiceParser().parse("dndstats")
    assert [result.total for result in results] == [13, 7, 18, 14, 4, 12]


def test_separate_formulas_remain_independent() -> None:
    random.seed(42)
    results = DiceParser().parse("1d20+5; 2d6+1d4")
    assert [result.formula_count for result in results] == [2, 2]
    assert [result.formula_index for result in results] == [0, 1]
    assert all("Итог" in _dice_result_block(result) for result in results)


def test_output_is_paginated_within_discord_size_limit() -> None:
    pages = _dice_paginate("Результаты", ["A" * 20, "B" * 20], max_chars=32)
    assert pages
    assert all(len(page) <= 32 for page in pages)
