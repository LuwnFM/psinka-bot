"""Короткие приказы Псинка для RP-модерации.

Короткая форма переписывается в полную RP-фразу. Логика и права остаются в прежних обработчиках.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

DEFAULT_REASON = "Причина не указана"

# Полные фразы ограничивают число цифр срока. Больший срок урезаем, чтобы обработчик ответил ошибкой срока.
MAX_JAIL_MINUTES_DIGITS = 999_999
MAX_CARCER_MINUTES_DIGITS = 99_999

HELP = "help"
JAIL = "jail"
JAIL_RELEASE = "jail_release"
CARCER = "carcer"
CARCER_RELEASE = "carcer_release"
KICK = "kick"
UNBAN = "unban"
ROLE_GRANT = "role_grant"
ROLE_REMOVE = "role_remove"

_COMMANDS = {
    "справка": HELP,
    "снять мут": JAIL_RELEASE,
    "снять та": CARCER_RELEASE,
    "снять бан": UNBAN,
    "выдать роль": ROLE_GRANT,
    "снять роль": ROLE_REMOVE,
    "мут": JAIL,
    "та": CARCER,
    "кик": KICK,
}

USAGE = {
    JAIL: "`Псинка мут @участник 15 причина` (срок: `15`/`15м` - минуты, `2ч` - часы, `1д` - сутки)",
    CARCER: "`Псинка та @участник 15 причина` (срок: `15`/`15м` - минуты, `2ч` - часы, `1д` - сутки)",
    UNBAN: "`Псинка снять бан 123456789012345678 причина`",
    ROLE_GRANT: "`Псинка выдать роль @участник @Роль причина`",
    ROLE_REMOVE: "`Псинка снять роль @участник @Роль причина`",
}

_MENTION = r"<@!?\d{15,25}>"

SHORT_RE = re.compile(
    rf"^\s*(?:(?P<pre>{_MENTION})\s*[,\u2014\u2013-]?\s*)?"
    r"пси{1,2}нка\s*,?\s+"
    r"(?P<cmd>справка|снять\s+мут|снять\s+та|снять\s+бан|выдать\s+роль|снять\s+роль|мут|та|кик)"
    r"(?:\s+(?P<rest>.*?))?\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)

_LEADING_MENTION_RE = re.compile(rf"^(?P<mention>{_MENTION})\s*[,\u2014\u2013-]?\s*(?P<rest>.*)$", re.DOTALL)

_TERM_RE = re.compile(
    r"^(?P<amount>\d{1,9})\s*"
    r"(?:(?P<unit>минут[аы]?|мин\.?|м|час(?:а|ов)?|ч|сут(?:ки|ок)?|дн(?:я|ей)|день|д)(?=\s|$))?"
    r"\s*(?P<reason>.*)$",
    flags=re.IGNORECASE | re.DOTALL,
)

_UNBAN_RE = re.compile(r"^(?:<@!?)?(?P<user_id>\d{15,25})>?(?:\s+(?P<reason>.*))?$", re.DOTALL)


@dataclass(frozen=True)
class ShortCommand:
    action: str
    # None, если приказ записан с ошибкой.
    phrase: Optional[str]
    error: Optional[str] = None


def _one_line(value: Optional[str]) -> str:
    # Полные фразы без DOTALL, схлопываем переносы.
    return " ".join((value or "").split())


def _reason(value: Optional[str]) -> str:
    return _one_line(value) or DEFAULT_REASON


def _term_minutes(amount: int, unit: Optional[str]) -> int:
    unit_cf = (unit or "").casefold()
    if unit_cf.startswith("ч"):
        return amount * 60
    if unit_cf.startswith("д") or unit_cf.startswith("сут"):
        return amount * 24 * 60
    return amount


def _split_role(rest: str, role_names: Iterable[str]) -> tuple[str, str]:
    """Отделяет роль от причины по самому длинному совпадению с ролями сервера."""
    rest_cf = rest.casefold()
    best = ""
    for name in role_names:
        name_cf = _one_line(name).casefold()
        if not name_cf or len(name_cf) <= len(best):
            continue
        if rest_cf == name_cf or rest_cf.startswith(name_cf + " "):
            best = name_cf
    if not best:
        # Роль не найдена, отдаём всё обработчику.
        return rest, ""
    return rest[: len(best)], rest[len(best):]


def parse_short_command(content: str, role_names: Iterable[str] = ()) -> Optional[ShortCommand]:
    """Разбирает короткий приказ. None, если это не он."""
    match = SHORT_RE.fullmatch(content or "")
    if match is None:
        return None

    action = _COMMANDS[" ".join(match.group("cmd").casefold().split())]
    rest = _one_line(match.group("rest"))

    if action == HELP:
        if rest:
            return None
        return ShortCommand(action, "Огласи устав Гвардии")

    if action == UNBAN:
        unban = _UNBAN_RE.fullmatch(rest)
        if unban is None:
            return ShortCommand(action, None, f"Укажи ID пользователя: {USAGE[UNBAN]}")
        return ShortCommand(
            action,
            f"Врата Фаервелла вновь открыты для {unban.group('user_id')} за {_reason(unban.group('reason'))}",
        )

    mention = match.group("pre")
    inner = _LEADING_MENTION_RE.fullmatch(rest)
    if inner is not None:
        if mention is not None:
            return ShortCommand(action, None, "Укажи участника один раз: до слова «Псинка» или после команды.")
        mention = inner.group("mention")
        rest = inner.group("rest")
    prefix = f"{mention} " if mention else ""

    if action in (JAIL, CARCER):
        term = _TERM_RE.fullmatch(rest)
        if term is None:
            return ShortCommand(action, None, f"Укажи срок: {USAGE[action]}")
        minutes = _term_minutes(int(term.group("amount")), term.group("unit"))
        reason = _reason(term.group("reason"))
        if action == JAIL:
            minutes = min(minutes, MAX_JAIL_MINUTES_DIGITS)
            return ShortCommand(action, f"{prefix}Ты отправляешься в темницу на {minutes} минут за {reason}")
        minutes = min(minutes, MAX_CARCER_MINUTES_DIGITS)
        return ShortCommand(action, f"{prefix}Ты отправляешься в карцер на {minutes} минут за {reason}")

    if action == JAIL_RELEASE:
        return ShortCommand(action, f"{prefix}Ты освобождаешься из темницы за {_reason(rest)}")
    if action == CARCER_RELEASE:
        return ShortCommand(action, f"{prefix}Ты освобождаешься из карцера за {_reason(rest)}")
    if action == KICK:
        return ShortCommand(action, f"{prefix}Ты изгоняешься из Фаервелла за {_reason(rest)}")

    # Выдача и снятие роли.
    if not rest:
        return ShortCommand(action, None, f"Укажи роль: {USAGE[action]}")
    role, reason = _split_role(rest, role_names)
    verb = "На тебя возлагается знак" if action == ROLE_GRANT else "С тебя снимается знак"
    return ShortCommand(action, f"{prefix}{verb} {role} за {_reason(reason)}")


def expand_short_command(content: str, role_names: Iterable[str] = ()) -> str:
    """Полная фраза для короткого приказа, иначе исходный текст."""
    short = parse_short_command(content, role_names)
    if short is None or short.phrase is None:
        return content
    return short.phrase
