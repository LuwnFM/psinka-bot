"""Regression fixtures for the unchanged new and ancient auction formats."""

from services.auction_lots import parse_ancient_auction_lot, parse_new_auction_lot


def build_info(text: str) -> dict[str, object]:
    return {"text": text, "raw": {}, "author": "A"}


def test_new_lot_without_bids_is_not_reported_as_sale() -> None:
    result = parse_new_auction_lot(build_info("📦 ЛОТ №12\nНачальная стоимость: 1 000"))
    assert result is not None
    assert result["lot"] == 12
    assert result["type"] == "no_bid"
    assert result["start_price"] == 1000


def test_new_lot_last_bid_and_person_are_retained() -> None:
    text = "Лот 12\nНачальная стоимость: 100\nПоследняя ставка: 350\nОт: Иван"
    result = parse_new_auction_lot(build_info(text))
    assert result is not None
    assert (result["lot"], result["type"], result["price"], result["bidder"]) == (
        12, "new", 350, "Иван"
    )
    assert result["is_auctioneer"] is False


def test_returned_lot_not_counted_as_sale() -> None:
    result = parse_new_auction_lot(build_info("Лот №23\nПредмет возвращен продавцу"))
    assert result is not None
    assert result["type"] == "returned"
    assert result["price"] is None


def test_ancient_lot_keeps_its_separate_price_interpretation() -> None:
    result = parse_ancient_auction_lot(
        build_info("Номер лота: 25\nНазвание: Лук\nНачальная стоимость: 700")
    )
    assert result is not None
    assert result["type"] == "ancient"
    assert result["lot"] == 25
    assert result["price"] == 700
