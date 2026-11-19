"""Pure text and author normalization used by auction price extraction."""

import re
from typing import Any, Dict, List, Optional

def auction_money_to_int(raw: Optional[str]) -> Optional[int]:
    digits = re.sub(r"\D+", "", raw or "")
    return int(digits) if digits else None


def clean_auction_text(text: Any) -> str:
    text = "" if text is None else str(text)

    # Убираем невидимые символы, которые часто ломают regex.
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", text)

    text = text.replace("\u00A0", " ")
    text = text.replace("Ｎ", "N")
    text = text.replace("ｏ", "o")
    text = text.replace("О", "О")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def norm_auction_text(text: Any) -> str:
    return clean_auction_text(text).lower().replace("ё", "е")


def append_unique_text(parts: List[str], value: Any):
    if value is None:
        return

    text = clean_auction_text(value)
    if not text:
        return

    if text not in parts:
        parts.append(text)


def flatten_any_strings(value: Any) -> List[str]:
    result = []

    if value is None:
        return result

    if isinstance(value, str):
        if value.strip():
            result.append(value)
        return result

    if isinstance(value, dict):
        for item in value.values():
            result.extend(flatten_any_strings(item))
        return result

    if isinstance(value, (list, tuple)):
        for item in value:
            result.extend(flatten_any_strings(item))
        return result

    return result


def get_raw_author_name(raw_message: Dict[str, Any]) -> str:
    author = raw_message.get("author") or {}
    username = author.get("username") or ""
    global_name = author.get("global_name") or ""
    discriminator = author.get("discriminator") or ""

    if global_name and username:
        return f"{global_name} | {username}"

    if username and discriminator and discriminator != "0":
        return f"{username}#{discriminator}"

    return username or global_name or ""


def get_raw_author_id(raw_message: Dict[str, Any]) -> str:
    author = raw_message.get("author") or {}
    return str(author.get("id") or "")


