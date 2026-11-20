"""Original auction lot classification and price parsing, independent of Discord."""

import re
from typing import Any

from services.auction_text import (
    auction_money_to_int,
    clean_auction_text,
    norm_auction_text,
)

AUCTIONEER_IDS = {839258901249523723, 754615336682127372}
AUCTIONEER_USERNAMES = {"aukcionistfirewell", "lagyshka22"}

NEW_AUCTION_LOT_RE = re.compile(
    r"(?:📦\s*)?(?:л\s*о\s*т|lot)\s*(?:№|#|n\s*o\.?|no\.?|nº|n°|номер)?\s*[:\-–—]?\s*(\d{1,8})",
    re.IGNORECASE,
)

ANCIENT_AUCTION_LOT_RE = re.compile(
    r"Номер\s+лота\s*:\s*(\d{1,8})",
    re.IGNORECASE,
)

AUCTION_LAST_BID_RE = re.compile(
    r"Последняя\s+ставка[^\d]{0,180}([0-9][0-9 \u00A0]*)",
    re.IGNORECASE | re.DOTALL,
)

AUCTION_START_PRICE_RE = re.compile(
    r"Начальная\s+стоимость[^\d]{0,120}([0-9][0-9 \u00A0]*)",
    re.IGNORECASE | re.DOTALL,
)


def raw_field_candidates(raw_message: dict[str, Any], field_name_part: str) -> list[str]:
    result = []
    target = norm_auction_text(field_name_part)

    for embed in raw_message.get("embeds") or []:
        if not isinstance(embed, dict):
            continue

        for field in embed.get("fields") or []:
            if not isinstance(field, dict):
                continue

            name = field.get("name", "")
            value = field.get("value", "")

            if target in norm_auction_text(name):
                result.append(clean_auction_text(value))
                result.append(clean_auction_text(f"{name}\n{value}"))

    return [x for x in result if x]


def raw_title_candidates(raw_message: dict[str, Any]) -> list[str]:
    result = []

    for embed in raw_message.get("embeds") or []:
        if isinstance(embed, dict):
            title = embed.get("title")
            if title:
                result.append(clean_auction_text(title))

    return result


def extract_new_lot_number(text: str, raw_message: dict[str, Any] | None = None) -> int | None:
    candidates = []

    if raw_message:
        candidates.extend(raw_title_candidates(raw_message))

    candidates.append(text)

    for candidate in candidates:
        lot_match = NEW_AUCTION_LOT_RE.search(candidate)
        if lot_match:
            return int(lot_match.group(1))

    lower = norm_auction_text(text)

    # Запасной режим: если это точно новый лот, но слово "Лот" API отдало криво.
    if "последняя ставка" in lower and "начальная стоимость" in lower:
        fallback = re.search(r"(?:№|#|nº|n°|no\.?|n\s*o\.?)\s*(\d{1,8})", text, re.IGNORECASE)
        if fallback:
            return int(fallback.group(1))

    return None


def extract_between_labels(text: str, start_label: str, stop_labels: list[str]) -> str:
    stop_part = "|".join(re.escape(label) for label in stop_labels)

    pattern = re.compile(
        rf"{re.escape(start_label)}\s*:?\s*(.*?)(?=\n\s*(?:{stop_part})\s*:|\n\s*=+|\Z)",
        re.IGNORECASE | re.DOTALL,
    )

    match = pattern.search(text)
    if not match:
        return ""

    return clean_auction_text(match.group(1))


def extract_new_item_text(text: str, raw_message: dict[str, Any]) -> str:
    raw_items = raw_field_candidates(raw_message, "Предмет")

    for item in raw_items:
        # Берём именно value поля, а не "Предмет\nvalue", если получилось.
        cleaned = clean_auction_text(item)
        if cleaned and norm_auction_text(cleaned) != "предмет":
            cleaned = re.sub(r"^\s*Предмет\s*\n", "", cleaned, flags=re.IGNORECASE).strip()
            return clean_auction_text(cleaned.lstrip("> ").strip())

    patterns = [
        r"(?:^|\n)\s*#+\s*Предмет\s*\n\s*>?\s*(.*?)(?=\n\s*(?:💰|⏳|#+\s*Последняя|Последняя\s+ставка|\*\*Торги|Торги\s+завершены|Лот\s+проверяется|-#\s*Опубликовано)|\Z)",
        r"(?:^|\n)\s*Предмет\s*\n\s*>?\s*(.*?)(?=\n\s*(?:💰|⏳|#+\s*Последняя|Последняя\s+ставка|\*\*Торги|Торги\s+завершены|Лот\s+проверяется|-#\s*Опубликовано)|\Z)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return clean_auction_text(match.group(1).lstrip("> ").strip())

    return ""


def extract_ancient_name(text: str) -> str:
    return extract_between_labels(
        text,
        "Наименование",
        ["Описание", "Начальная стоимость", "Конец торгов", "Скриншот-подтверждение владения", "Скриншот"],
    )


def extract_ancient_description(text: str) -> str:
    return extract_between_labels(
        text,
        "Описание",
        ["Начальная стоимость", "Конец торгов", "Скриншот-подтверждение владения", "Скриншот"],
    )


def extract_start_price(text: str, raw_message: dict[str, Any]) -> int | None:
    candidates = []
    candidates.extend(raw_field_candidates(raw_message, "Начальная стоимость"))
    candidates.append(text)

    for candidate in candidates:
        match = AUCTION_START_PRICE_RE.search(candidate)
        if match:
            return auction_money_to_int(match.group(1))

        # Если field name = "💰 Начальная стоимость", а value = "`700` бонкоинов"
        if "начальная" in norm_auction_text(candidate):
            price = auction_money_to_int(candidate)
            if price is not None:
                return price

    return None


def extract_last_bid_price_and_area(text: str, raw_message: dict[str, Any]) -> tuple[int | None, str]:
    candidates = []
    candidates.extend(raw_field_candidates(raw_message, "Последняя ставка"))
    candidates.append(text)

    for candidate in candidates:
        match = AUCTION_LAST_BID_RE.search(candidate)
        if match:
            return auction_money_to_int(match.group(1)), candidate

        if "последняя ставка" in norm_auction_text(candidate):
            price = auction_money_to_int(candidate)
            if price is not None:
                return price, candidate

    return None, ""


def extract_bidder(text: str, raw_message: dict[str, Any], bid_area: str) -> str:
    candidates = []

    if bid_area:
        candidates.append(bid_area)

    candidates.extend(raw_field_candidates(raw_message, "Последняя ставка"))

    last_bid_match = re.search(r"Последняя\s+ставка", text, re.IGNORECASE)
    if last_bid_match:
        candidates.append(text[last_bid_match.end() : last_bid_match.end() + 2000])

    candidates.append(text)

    for candidate in candidates:
        match = re.search(
            r"(?:^|\n|\s)(?:\*\*)?\s*От\s*:(?:\*\*)?\s*(.*?)(?=\n|$)",
            candidate,
            re.IGNORECASE | re.DOTALL,
        )

        if match:
            bidder = clean_auction_text(match.group(1))
            bidder = bidder.replace("**", "").strip()
            if bidder:
                return bidder

    return ""


def is_auctioneer_bidder(bidder: str, bid_area: str, text: str) -> bool:
    area = norm_auction_text(f"{bidder}\n{bid_area}\n{text[:1200]}")
    area = area.replace("*", "")

    for auctioneer_id in AUCTIONEER_IDS:
        if f"<@{auctioneer_id}>" in area or f"<@!{auctioneer_id}>" in area:
            return True

    return any(nick.lower() in area for nick in AUCTIONEER_USERNAMES)


def parse_new_auction_lot(info: dict[str, Any]) -> dict[str, Any] | None:
    text = info["text"]
    raw_message = info["raw"]

    lot_no = extract_new_lot_number(text, raw_message)
    if lot_no is None:
        return None

    lower = norm_auction_text(text)

    start_price = extract_start_price(text, raw_message)
    item = extract_new_item_text(text, raw_message)

    base = {
        "lot": lot_no,
        "item": item,
        "start_price": start_price,
        "author": info.get("author", ""),
        "author_id": info.get("author_id", ""),
        "message_id": info.get("message_id", ""),
        "message_url": info.get("message_url", ""),
        "created_at": info.get("created_at", ""),
        "embeds_count": info.get("embeds_count", 0),
        "raw_text": text,
    }

    if "предмет возвращен продавцу" in lower:
        return {
            **base,
            "type": "returned",
            "status": "Возврат продавцу",
            "price": None,
            "bidder": "",
            "is_auctioneer": False,
            "closed": "торги завершены" in lower,
        }

    price, bid_area = extract_last_bid_price_and_area(text, raw_message)

    if price is None:
        if "лот проверяется администратором" in lower or "проверяется администратором" in lower:
            status = "Проверяется администратором, ставки ещё нет"
        else:
            status = "Нет последней ставки"

        return {
            **base,
            "type": "no_bid",
            "status": status,
            "price": None,
            "bidder": "",
            "is_auctioneer": False,
            "closed": "торги завершены" in lower,
        }

    bidder = extract_bidder(text, raw_message, bid_area)
    is_auctioneer = is_auctioneer_bidder(bidder, bid_area, text)

    return {
        **base,
        "type": "new",
        "status": "Засчитан: аукционист" if is_auctioneer else "Засчитан: люди",
        "price": price,
        "bidder": bidder or "не найдено поле От",
        "is_auctioneer": is_auctioneer,
        "closed": "торги завершены" in lower,
    }


def parse_ancient_auction_lot(info: dict[str, Any]) -> dict[str, Any] | None:
    text = info["text"]

    ancient_match = ANCIENT_AUCTION_LOT_RE.search(text)
    if not ancient_match:
        return None

    lot_no = int(ancient_match.group(1))
    name = extract_ancient_name(text)
    description = extract_ancient_description(text)

    start_match = AUCTION_START_PRICE_RE.search(text)
    price = auction_money_to_int(start_match.group(1)) if start_match else None

    if price is None:
        return {
            "type": "ancient_bad_price",
            "lot": lot_no,
            "name": name,
            "description": description,
            "price": None,
            "author": info.get("author", ""),
            "message_id": info.get("message_id", ""),
            "message_url": info.get("message_url", ""),
            "created_at": info.get("created_at", ""),
            "raw_text": text,
        }

    return {
        "type": "ancient",
        "lot": lot_no,
        "name": name,
        "description": description,
        "price": price,
        "author": info.get("author", ""),
        "message_id": info.get("message_id", ""),
        "message_url": info.get("message_url", ""),
        "created_at": info.get("created_at", ""),
        "raw_text": text,
    }
