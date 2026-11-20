"""Pure post-counting template parser, preserving original matching behavior."""

import calendar as pc_calendar
import re
import unicodedata as pc_unicodedata
from collections.abc import Iterable, Iterator, Sequence
from datetime import date, datetime, timedelta, timezone

PC_MOSCOW_TZ = timezone(timedelta(hours=3), name="MSK")
PC_COUNT_LENGTH_FOR_ALL_TEMPLATES = False

PC_DATE_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})\s*$")
PC_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
PC_MARKDOWN_RE = re.compile(r"[*_~|`]")
PC_SEGMENT_RE = re.compile(r"[^\s,;]+", re.UNICODE)
PC_OUTER_PAYLOAD = "#*_~|` \\t\\r\\n-–—_=+()[]{}<>:;,.!?/\\"
PC_VARIANT_LEFT = "*_~|` "
PC_VARIANT_RIGHT = "*_~|` \t\r\n,;:.!?"

PC_GM = "gm"
PC_DRP = "drp"
PC_POLIT = "polit"
PC_ALL_FAMILIES = (PC_GM, PC_DRP, PC_POLIT)
PC_LABELS = {
    PC_GM: "ГМ-пост",
    PC_DRP: "ДРП-вердикт",
    PC_POLIT: "Полит-вердикт",
}
PC_PREFIXES = {
    PC_GM: ("гмпост",),
    PC_DRP: ("дрпвердикт", "дрпверд"),
    PC_POLIT: ("политвердикт", "политверд"),
}
PC_MODE_ALIASES = {
    "гмпост": (PC_GM,),
    "дрпверд": (PC_DRP,),
    "дрпвердикт": (PC_DRP,),
    "политверд": (PC_POLIT,),
    "политвердикт": (PC_POLIT,),
    "тришаблона": PC_ALL_FAMILIES,
}


class PCDateError(ValueError):
    pass


class PCSearchUnavailable(RuntimeError):
    """Быстрый поиск Discord недоступен; нужно повторить, делить пакет или перейти на history()."""

    def __init__(self, message: str, status: int | None = None, code: int | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class PCPeriod:
    def __init__(
        self,
        start_local: datetime,
        end_exclusive_local: datetime,
        start_utc: datetime,
        end_exclusive_utc: datetime,
        end_was_clamped: bool,
        requested_end_day: int,
        actual_end_day: int,
    ) -> None:
        self.start_local = start_local
        self.end_exclusive_local = end_exclusive_local
        self.start_utc = start_utc
        self.end_exclusive_utc = end_exclusive_utc
        self.end_was_clamped = end_was_clamped
        self.requested_end_day = requested_end_day
        self.actual_end_day = actual_end_day

    @property
    def start_date(self) -> date:
        return self.start_local.date()

    @property
    def end_date(self) -> date:
        return (self.end_exclusive_local - timedelta(microseconds=1)).date()


class PCTemplateMatch:
    def __init__(
        self,
        family: str,
        payload_key: str,
        canonical: str,
        raw_variant: str,
        exact_surface: bool,
        span_start: int,
        span_end: int,
    ) -> None:
        self.family = family
        self.payload_key = payload_key
        self.canonical = canonical
        self.raw_variant = raw_variant
        self.exact_surface = exact_surface
        # Границы метки в нормализованном тексте сообщения.
        self.span_start = span_start
        self.span_end = span_end


def pc_parse_date_parts(raw: str) -> tuple[int, int, int]:
    match = PC_DATE_RE.fullmatch(raw or "")
    if not match:
        raise PCDateError("нечитаемый формат")
    day = int(match.group(1))
    month = int(match.group(2))
    year_raw = match.group(3)
    year = 2000 + int(year_raw) if len(year_raw) == 2 else int(year_raw)
    if not 1 <= month <= 12:
        raise PCDateError("месяц существует только от 1 до 12")
    if day < 1:
        raise PCDateError("нулевой или отрицательный день календарю не предложили")
    if not 2000 <= year <= 9999:
        raise PCDateError("год вне поддерживаемого диапазона")
    return day, month, year


def pc_parse_period(start_raw: str, end_raw: str) -> PCPeriod:
    start_day, start_month, start_year = pc_parse_date_parts(start_raw)
    start_last = pc_calendar.monthrange(start_year, start_month)[1]
    if start_day > start_last:
        raise PCDateError("начальная дата не существует")

    requested_end_day, end_month, end_year = pc_parse_date_parts(end_raw)
    end_last = pc_calendar.monthrange(end_year, end_month)[1]
    actual_end_day = min(requested_end_day, end_last)

    start_local = datetime(start_year, start_month, start_day, tzinfo=PC_MOSCOW_TZ)
    end_exclusive_local = datetime(end_year, end_month, actual_end_day, tzinfo=PC_MOSCOW_TZ) + timedelta(
        days=1
    )
    if end_exclusive_local <= start_local:
        raise PCDateError("конечная дата раньше начальной")

    return PCPeriod(
        start_local=start_local,
        end_exclusive_local=end_exclusive_local,
        start_utc=start_local.astimezone(timezone.utc),
        end_exclusive_utc=end_exclusive_local.astimezone(timezone.utc),
        end_was_clamped=requested_end_day != actual_end_day,
        requested_end_day=requested_end_day,
        actual_end_day=actual_end_day,
    )


def pc_normalize_text(value: str) -> str:
    text = pc_unicodedata.normalize("NFKC", value or "")
    text = PC_ZERO_WIDTH_RE.sub("", text)
    text = PC_MARKDOWN_RE.sub("", text)
    return text.casefold()


def pc_word_pattern(value: str) -> re.Pattern[str]:
    normalized = pc_normalize_text(value).strip()
    if not normalized:
        raise ValueError("пустое значение")
    return re.compile(rf"(?<!\w){re.escape(normalized)}(?!\w)", re.UNICODE)


def pc_compact(value: str) -> str:
    return "".join(ch for ch in pc_normalize_text(value) if ch.isalnum())


def pc_template_mode(value: str) -> tuple[str, ...] | None:
    return PC_MODE_ALIASES.get(pc_compact(value))


def pc_damerau(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    matrix = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for i in range(len(left) + 1):
        matrix[i][0] = i
    for j in range(len(right) + 1):
        matrix[0][j] = j
    for i in range(1, len(left) + 1):
        for j in range(1, len(right) + 1):
            cost = 0 if left[i - 1] == right[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + cost,
            )
            if i > 1 and j > 1 and left[i - 1] == right[j - 2] and left[i - 2] == right[j - 1]:
                matrix[i][j] = min(matrix[i][j], matrix[i - 2][j - 2] + 1)
    return matrix[-1][-1]


def pc_alnum_positions(value: str, start: int) -> tuple[str, list[int]]:
    chars, positions = [], []
    for index in range(start, len(value)):
        if value[index].isalnum():
            chars.append(value[index].casefold())
            positions.append(index)
    return "".join(chars), positions


def pc_candidate_starts(segment: str) -> Iterator[int]:
    for index, char in enumerate(segment):
        if char.isalnum() and (index == 0 or not segment[index - 1].isalnum()):
            yield index


def pc_best_prefix(compact: str, positions: Sequence[int], families: Iterable[str]) -> tuple[str, int] | None:
    best = None
    for family in families:
        for canonical in PC_PREFIXES[family]:
            for consumed in (len(canonical) - 1, len(canonical), len(canonical) + 1):
                if consumed < 1 or consumed >= len(compact) or consumed > len(positions):
                    continue
                distance = pc_damerau(compact[:consumed], canonical)
                if distance > 1:
                    continue
                boundary_penalty = 0 if positions[consumed] - positions[consumed - 1] > 1 else 1
                key = (
                    distance,
                    boundary_penalty,
                    abs(consumed - len(canonical)),
                    -len(canonical),
                    consumed,
                    family,
                )
                if best is None or key < best:
                    best = key
    if best is None:
        return None
    return best[5], best[4]


def pc_clean_payload(raw: str) -> tuple[str, str]:
    value = pc_unicodedata.normalize("NFKC", raw or "")
    value = PC_ZERO_WIDTH_RE.sub("", value)
    value = PC_MARKDOWN_RE.sub("", value).strip(PC_OUTER_PAYLOAD)
    key = "".join(ch.casefold() for ch in value if ch.isalnum())
    if not key:
        return "", ""
    display = "".join(ch for ch in value if ch != "_" and not ch.isspace() and ch not in "()[]{}<>").strip(
        "-–—_=+.:/\\"
    )
    return key, (display or key).upper()


def pc_variant(segment: str, start: int) -> str:
    display_start = start
    while display_start > 0 and segment[display_start - 1] in "#([{" + PC_VARIANT_LEFT:
        display_start -= 1
    return segment[display_start:].strip(PC_VARIANT_LEFT).rstrip(PC_VARIANT_RIGHT)


def pc_is_exact_surface(raw_variant: str, canonical: str) -> bool:
    value = pc_unicodedata.normalize("NFKC", raw_variant or "")
    value = PC_ZERO_WIDTH_RE.sub("", value)
    value = PC_MARKDOWN_RE.sub("", value).strip()
    if value.startswith("#"):
        value = value[1:].strip()
    return value.casefold() == canonical.casefold()


def pc_find_templates(content: str, families: Iterable[str]) -> list[PCTemplateMatch]:
    selected = tuple(f for f in families if f in PC_ALL_FAMILIES)
    if not selected:
        return []
    text = pc_unicodedata.normalize("NFKC", content or "")
    text = PC_ZERO_WIDTH_RE.sub("", text)
    found, seen = [], set()

    for segment_match in PC_SEGMENT_RE.finditer(text):
        segment = segment_match.group(0)
        for start in pc_candidate_starts(segment):
            compact, positions = pc_alnum_positions(segment, start)
            if not compact:
                continue
            if any(compact == prefix for family in selected for prefix in PC_PREFIXES[family]):
                continue
            prefix = pc_best_prefix(compact, positions, selected)
            if prefix is None:
                continue
            family, consumed = prefix
            payload_key, payload_display = pc_clean_payload(segment[positions[consumed - 1] + 1 :])
            if not payload_key:
                continue
            location = (segment_match.start() + start, segment_match.end(), family)
            if location in seen:
                continue
            seen.add(location)
            canonical = f"{PC_LABELS[family]}-{payload_display}"

            display_start = start
            while display_start > 0 and segment[display_start - 1] in "#([{" + PC_VARIANT_LEFT:
                display_start -= 1

            raw_variant = pc_variant(segment, start)
            found.append(
                PCTemplateMatch(
                    family=family,
                    payload_key=payload_key,
                    canonical=canonical,
                    raw_variant=raw_variant,
                    exact_surface=pc_is_exact_surface(raw_variant, canonical),
                    span_start=segment_match.start() + display_start,
                    span_end=segment_match.end(),
                )
            )
            break
    return found


def pc_template_body_length(content: str, matches: Sequence[PCTemplateMatch]) -> int:
    """
    Считает длину сообщения после удаления всех найденных шаблонных меток.
    Оставшиеся пробелы, переносы, пунктуация и Discord-разметка считаются
    символами; пробелы по краям сообщения не считаются.
    """
    text = pc_unicodedata.normalize("NFKC", content or "")
    text = PC_ZERO_WIDTH_RE.sub("", text)

    spans = []
    for match in matches:
        start = max(0, min(len(text), int(match.span_start)))
        end = max(start, min(len(text), int(match.span_end)))
        if end > start:
            spans.append((start, end))

    if not spans:
        return len(text.strip())

    spans.sort()
    merged = []  # type: list[list[int]]
    for start, end in spans:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    parts = []
    cursor = 0
    for start, end in merged:
        parts.append(text[cursor:start])
        parts.append(" ")
        cursor = end
    parts.append(text[cursor:])

    return len("".join(parts).strip())


def pc_length_enabled_for_family(family: str) -> bool:
    return bool(PC_COUNT_LENGTH_FOR_ALL_TEMPLATES or family == PC_GM)


def pc_any_length_enabled(families: Iterable[str]) -> bool:
    return bool(families) and any(pc_length_enabled_for_family(family) for family in families)
