"""Reusable text normalization and table parsing for mercenary catalog entries."""

import re


def normalize_lookup_text(text: str) -> str:
    """
    Единая нормализация для поиска:
    - не зависит от регистра;
    - ё = е;
    - дефисы/тире считаются пробелами;
    - номера в конце убираются;
    - лишняя пунктуация не ломает поиск.
    """
    text = (text or "").strip().lower().replace("ё", "е")
    text = re.sub(r"\s*[-–—]\s*\d+\s*$", "", text)
    text = re.sub(r"\s+\d+\s*$", "", text)
    text = re.sub(r"[-–—]+", " ", text)
    text = re.sub(r"[«»\"'`.,:;!?()\[\]{}]+", " ", text)
    return " ".join(text.split())


def dedupe_preserve_order(items: list[str]) -> list[str]:
    """Убирает дубли, сохраняя первое написание."""
    result: list[str] = []
    seen = set()
    for item in items:
        item = str(item or "").strip()
        key = normalize_lookup_text(item)
        if key and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def split_multi_field(value: str) -> list[str]:
    """Разбивает поля вида 'А; Б, В\nГ'."""
    if not value:
        return []
    parts = re.split(r"[;,\n]+", str(value))
    return dedupe_preserve_order([part.strip() for part in parts if part.strip()])


def _rows_to_dicts(rows: list[list[str]], required_header: str) -> list[dict[str, str]]:
    header_index = None
    for i, row in enumerate(rows):
        if required_header in row:
            header_index = i
            break
    if header_index is None:
        return []

    headers = [str(x or "").strip() for x in rows[header_index]]
    data: list[dict[str, str]] = []
    for row in rows[header_index + 1 :]:
        item: dict[str, str] = {}
        for idx, header in enumerate(headers):
            if header:
                item[header] = str(row[idx] if idx < len(row) else "").strip()
        if any(item.values()):
            data.append(item)
    return data


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(float(str(value or "").replace("%", "").replace(",", ".").strip()))
    except Exception:  # noqa: BLE001 - preserve original extracted parser behavior
        return default


def _yes(value: str) -> bool:
    return normalize_lookup_text(value) in {"да", "yes", "true", "1", "есть"}


def _resolve_existing_profession_name(name: str, mercs: dict[str, list[str]]) -> str | None:
    """Находит профессию в базе без учёта регистра/ё/дефисов."""
    key = normalize_lookup_text(name)
    if not key:
        return None
    for profession in mercs:
        if normalize_lookup_text(profession) == key:
            return profession
    return None


def _clean_profession_targets(targets: list[str], mercs: dict[str, list[str]]) -> list[str]:
    """Оставляет только профессии, которые реально есть в Excel-базе."""
    cleaned: list[str] = []
    for target in targets:
        resolved = _resolve_existing_profession_name(target, mercs)
        if resolved:
            cleaned.append(resolved)
    return dedupe_preserve_order(cleaned)
