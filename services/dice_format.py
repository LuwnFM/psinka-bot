"""Formatting and Discord pagination of dice results."""

from services.dice import DiceResult, DiceTermResult


def _dice_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(round(value, 2))


def _dice_roll_list(values: list[int]) -> str:
    return "[" + ", ".join(map(str, values)) + "]"


def _dice_term_lines(term: DiceTermResult, is_first: bool = False) -> list[str]:
    sign_text = "" if is_first and term.sign > 0 else ("+" if term.sign > 0 else "−")
    label_prefix = f"{sign_text} " if sign_text else ""
    if term.kind == "number":
        value = _dice_number(term.number_value or 0.0)
        contribution = _dice_number(term.sign * (term.number_value or 0.0))
        return [f"🧮 `{label_prefix}{value}` → вклад **{contribution}**"]

    lines = [f"🎲 `{label_prefix}{term.source}`: исходно `{_dice_roll_list(term.base_rolls)}`"]

    if term.reroll_sequences:
        rerolls = []
        for die_index, sequence in term.reroll_sequences:
            chain = [term.base_rolls[die_index], *sequence]
            rerolls.append(f"#{die_index + 1} " + "→".join(map(str, chain)))
        lines.append("↪️ перебросы: " + "; ".join(rerolls))

    if term.exploded_rolls:
        lines.append(f"💥 добавочные броски: `{_dice_roll_list(term.exploded_rolls)}`")

    if term.kept_dice or term.dropped_dice:
        lines.append(f"📌 засчитано: `{_dice_roll_list(term.final_rolls)}`")
        if term.dropped_dice:
            lines.append(f"🗑 отброшено: `{_dice_roll_list(term.dropped_dice)}`")
    elif term.reroll_sequences or term.exploded_rolls:
        lines.append(f"📌 после эффектов: `{_dice_roll_list(term.final_rolls)}`")

    if term.target is not None:
        lines.append(
            f"🎯 цель ≥{term.target}: **{term.successes}** успех., {term.failures} провал., {term.botches} единиц"
        )

    if term.details:
        lines.append("⚙️ " + "; ".join(term.details))

    contribution = term.sign * term.subtotal
    lines.append(f"➡️ вклад в формулу: **{_dice_number(contribution)}**")

    for warning in term.warnings:
        lines.append(f"⚠️ {warning}")
    return lines


def _dice_result_block(result: DiceResult) -> str:
    lines = []
    if result.set_count > 1:
        lines.append(f"**Набор {result.set_index + 1}/{result.set_count}**")
    else:
        lines.append("**Результат**")

    for term_index, term in enumerate(result.terms):
        lines.extend(_dice_term_lines(term, is_first=(term_index == 0)))

    if result.global_modifier:
        op, value, before = result.global_modifier
        lines.append(
            f"🧮 итог до `{op}`: {_dice_number(before)} {op} {_dice_number(value)} = **{_dice_number(result.total)}**"
        )

    for warning in result.warnings:
        if warning not in {warning for term in result.terms for warning in term.warnings}:
            lines.append(f"⚠️ {warning}")

    if result.comment:
        lines.append(f"💬 _{result.comment}_")

    lines.append(f"🏁 **Итог: {_dice_number(result.total)}**")
    return "\n".join(lines)


def _dice_paginate(header: str, blocks: list[str], max_chars: int = 3900) -> list[str]:
    pages: list[str] = []
    current = header.strip()
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pages.append(current)
        if len(block) <= max_chars:
            current = block
        else:
            # Защитный fallback для крайне длинной цепочки перебросов/взрывов.
            chunks = [block[i : i + max_chars] for i in range(0, len(block), max_chars)]
            pages.extend(chunks[:-1])
            current = chunks[-1]
    if current:
        pages.append(current)
    return pages
