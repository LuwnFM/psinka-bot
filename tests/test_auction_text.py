"""Auction normalization behavior preserved after extraction."""

from services.auction_text import (
    append_unique_text,
    auction_money_to_int,
    clean_auction_text,
    flatten_any_strings,
    get_raw_author_id,
    get_raw_author_name,
    norm_auction_text,
)


def test_money_parsing_keeps_only_digits() -> None:
    assert auction_money_to_int("1 250 000 монет") == 1250000
    assert auction_money_to_int(None) is None


def test_unicode_cleanup_and_normalization() -> None:
    assert clean_auction_text("  Цена\u200b:\u00a01   000  ") == "Цена: 1 000"
    assert norm_auction_text("ЁЖ") == "еж"


def test_nested_embed_strings_flatten_in_order() -> None:
    assert flatten_any_strings({"title": "Лот", "fields": ["Цена", {"value": "500"}]}) == [
        "Лот",
        "Цена",
        "500",
    ]


def test_unique_text_deduplication() -> None:
    values: list[str] = []
    append_unique_text(values, " Лот ")
    append_unique_text(values, "Лот")
    assert values == ["Лот"]


def test_author_name_uses_display_name_and_id() -> None:
    raw = {"author": {"username": "dog", "global_name": "Пёс", "id": "789"}}
    assert get_raw_author_name(raw) == "Пёс | dog"
    assert get_raw_author_id(raw) == "789"
