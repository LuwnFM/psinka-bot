"""Legacy dice parser and RP game roll rules, extracted unchanged from entrypoint."""

import random
import re


class DiceTermResult:
    def __init__(self, source: str, sign: int = 1):
        self.source = source.strip()
        self.sign = 1 if sign >= 0 else -1
        self.kind = "dice"
        self.num_dice = 0
        self.num_sides = 0
        self.base_rolls: list[int] = []
        self.final_rolls: list[int] = []
        self.all_rolls: list[int] = []
        self.exploded_rolls: list[int] = []
        self.kept_dice: list[int] = []
        self.dropped_dice: list[int] = []
        self.reroll_sequences: list[tuple[int, list[int]]] = []
        self.details: list[str] = []
        self.warnings: list[str] = []
        self.successes = 0
        self.failures = 0
        self.botches = 0
        self.target: int | None = None
        self.subtotal = 0.0
        self.number_value: float | None = None


class DiceResult:
    def __init__(self):
        self.total = 0.0
        self.dice_rolls: list[int] = []
        self.all_rolls: list[int] = []
        self.details: list[str] = []
        self.comment = ""
        self.exploded_rolls: list[int] = []
        self.kept_dice: list[int] = []
        self.dropped_dice: list[int] = []
        self.rerolled = False
        self.successes: int = 0
        self.failures: int = 0
        self.botches: int = 0
        self.terms: list[DiceTermResult] = []
        self.warnings: list[str] = []
        self.expression = ""
        self.formula_raw = ""
        self.formula_expanded = ""
        self.formula_index = 0
        self.formula_count = 1
        self.set_index = 0
        self.set_count = 1
        self.global_modifier: tuple[str, float, float] | None = None


class DiceParser:
    MAX_SIDES = 100
    MAX_DICE_PER_SET = 100
    MAX_SETS = 20
    MAX_FORMULAS = 4
    MAX_EXTRA_ROLLS = 100
    MAX_INPUT_LENGTH = 2000
    MAX_COMMENT_LENGTH = 500

    def __init__(self):
        self.aliases = {
            "dndstats": "6 4d6 k3",
            "attack": "1d20",
            "+d20": "2d20 d1",
            "-d20": "2d20 kl1",
            "stat": "4d6 k3",
            "save": "1d20 + 5",
        }

    def parse(self, command_str: str) -> list[DiceResult]:
        if not command_str or not command_str.strip():
            return []
        if len(command_str) > self.MAX_INPUT_LENGTH:
            raise ValueError(f"Формула слишком длинная: максимум {self.MAX_INPUT_LENGTH} символов.")

        formulas = [part.strip() for part in command_str.split(";") if part.strip()]
        if not formulas:
            return []
        if len(formulas) > self.MAX_FORMULAS:
            raise ValueError(f"Можно указать максимум {self.MAX_FORMULAS} отдельные формулы через `;`.")

        results: list[DiceResult] = []
        formula_count = len(formulas)
        for formula_index, raw_formula in enumerate(formulas):
            parsed = self._parse_expression(raw_formula)
            for result in parsed:
                result.formula_raw = raw_formula
                result.formula_index = formula_index
                result.formula_count = formula_count
            results.extend(parsed)

        return results

    def _expand_alias(self, expression: str) -> str:
        parts = expression.strip().split(maxsplit=1)
        if not parts:
            return expression.strip()
        alias = parts[0].lower()
        if alias not in self.aliases:
            return expression.strip()
        tail = parts[1] if len(parts) > 1 else ""
        return (self.aliases[alias] + (" " + tail if tail else "")).strip()

    def _parse_expression(self, expression: str) -> list[DiceResult]:
        comment = ""
        if "!" in expression:
            expression, comment = expression.split("!", 1)
            expression = expression.strip()
            comment = comment.strip()
            if len(comment) > self.MAX_COMMENT_LENGTH:
                raise ValueError(
                    f"Комментарий после `!` должен быть не длиннее {self.MAX_COMMENT_LENGTH} символов."
                )
        if not expression:
            raise ValueError("Перед комментарием `!` должна быть формула броска.")

        expanded = self._expand_alias(expression)

        num_sets = 1
        set_match = re.match(r"^(\d+)\s+(.+)$", expanded)
        if set_match:
            possible_sets = int(set_match.group(1))
            remainder = set_match.group(2).strip()
            first_token = remainder.split(maxsplit=1)[0].lower() if remainder else ""
            if "d" in remainder.lower() or first_token in self.aliases:
                if not 1 <= possible_sets <= self.MAX_SETS:
                    raise ValueError(f"Количество наборов должно быть от 1 до {self.MAX_SETS}.")
                num_sets = possible_sets
                expanded = self._expand_alias(remainder)

        results: list[DiceResult] = []
        for set_index in range(num_sets):
            result = self._roll_once(expanded)
            result.comment = comment
            result.formula_expanded = expanded
            result.set_index = set_index
            result.set_count = num_sets
            results.append(result)
        return results

    def _extract_global_modifier(self, expression: str) -> tuple[str, tuple[str, float] | None]:
        match = re.search(r"\s*([*/])\s*(-?\d+(?:\.\d+)?)\s*$", expression)
        if not match:
            return expression.strip(), None
        core = expression[: match.start()].strip()
        if not core:
            raise ValueError("Перед `*` или `/` должна быть формула.")
        return core, (match.group(1), float(match.group(2)))

    def _split_additive_terms(self, expression: str) -> list[tuple[int, str]]:
        if not expression.strip():
            raise ValueError("Пустая формула броска.")

        terms: list[tuple[int, str]] = []
        current: list[str] = []
        sign = 1
        saw_content = False

        for ch in expression:
            if ch in "+-":
                text = "".join(current).strip()
                if text:
                    terms.append((sign, text))
                    current = []
                    sign = 1 if ch == "+" else -1
                    saw_content = True
                elif not saw_content and not terms:
                    sign = 1 if ch == "+" else -1
                    saw_content = True
                else:
                    raise ValueError("Некорректная последовательность `+`/`-` в формуле.")
            else:
                current.append(ch)
                if not ch.isspace():
                    saw_content = True

        text = "".join(current).strip()
        if not text:
            raise ValueError("Формула не может заканчиваться оператором `+` или `-`.")
        terms.append((sign, text))
        return terms

    def _parse_flags(self, tail: str, num_sides: int) -> dict[str, tuple[str, int]]:
        flags: dict[str, tuple[str, int]] = {}
        pos = 0
        pattern = re.compile(r"(ie|ir|kh|kl|dh|dl|e|r|k|d|t)\s*(\d+)?", re.IGNORECASE)
        category_for = {
            "r": "reroll",
            "ir": "reroll",
            "e": "explode",
            "ie": "explode",
            "k": "keepdrop",
            "kh": "keepdrop",
            "kl": "keepdrop",
            "d": "keepdrop",
            "dl": "keepdrop",
            "dh": "keepdrop",
            "t": "target",
        }

        while pos < len(tail):
            while pos < len(tail) and tail[pos].isspace():
                pos += 1
            if pos >= len(tail):
                break
            match = pattern.match(tail, pos)
            if not match:
                fragment = tail[pos:].strip()
                raise ValueError(f"Не понял часть формулы: `{fragment}`.")
            end = match.end()
            if end < len(tail) and not tail[end].isspace():
                fragment = tail[pos:].strip()
                raise ValueError(f"Не понял часть формулы: `{fragment}`.")

            flag = match.group(1).lower()
            category = category_for[flag]
            if category in flags:
                raise ValueError(
                    f"Нельзя указывать два модификатора одного типа в одном кубике: `{tail.strip()}`."
                )

            default_value = num_sides if category in {"explode", "target"} else 1
            value = int(match.group(2)) if match.group(2) is not None else default_value
            if category in {"reroll", "explode", "target"} and not 1 <= value <= num_sides:
                raise ValueError(
                    f"Значение `{flag}{value}` должно быть от 1 до {num_sides} для d{num_sides}."
                )
            if flag == "ir" and value >= num_sides:
                raise ValueError(
                    f"`ir{value}` для d{num_sides} никогда не сможет завершиться: порог должен быть ниже {num_sides}."
                )

            flags[category] = (flag, value)
            pos = end

        return flags

    def _parse_term(self, text: str, sign: int) -> DiceTermResult:
        term = DiceTermResult(text, sign)
        number_match = re.fullmatch(r"\d+(?:\.\d+)?", text.strip())
        if number_match:
            term.kind = "number"
            term.number_value = float(number_match.group(0))
            term.subtotal = term.number_value
            return term

        dice_match = re.fullmatch(r"(\d*)d(\d+)(.*)", text.strip(), re.IGNORECASE)
        if not dice_match:
            raise ValueError(
                f"Не удалось разобрать часть `{text}`. Используйте вид `XdY`, число или их сумму."
            )

        num_dice = int(dice_match.group(1) or 1)
        num_sides = int(dice_match.group(2))
        if not 1 <= num_dice <= self.MAX_DICE_PER_SET:
            raise ValueError(
                f"В одном кубиковом терме можно бросить от 1 до {self.MAX_DICE_PER_SET} кубиков."
            )
        if not 2 <= num_sides <= self.MAX_SIDES:
            raise ValueError(f"Количество граней должно быть от 2 до {self.MAX_SIDES}.")

        term.num_dice = num_dice
        term.num_sides = num_sides
        flags = self._parse_flags(dice_match.group(3), num_sides)

        rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
        term.base_rolls = rolls.copy()
        term.all_rolls = rolls.copy()
        working_rolls = rolls.copy()

        reroll = flags.get("reroll")
        if reroll:
            flag, threshold = reroll
            infinite = flag == "ir"
            budget = self.MAX_EXTRA_ROLLS
            for index, original in enumerate(list(working_rolls)):
                if original > threshold or budget <= 0:
                    continue
                sequence: list[int] = []
                while working_rolls[index] <= threshold and budget > 0:
                    new_value = random.randint(1, num_sides)
                    working_rolls[index] = new_value
                    term.all_rolls.append(new_value)
                    sequence.append(new_value)
                    budget -= 1
                    if not infinite:
                        break
                if sequence:
                    term.reroll_sequences.append((index, sequence))
            if budget == 0 and infinite and any(value <= threshold for value in working_rolls):
                term.warnings.append(
                    f"Достигнут защитный лимит {self.MAX_EXTRA_ROLLS} дополнительных перебросов."
                )
            if term.reroll_sequences:
                count = sum(len(seq) for _, seq in term.reroll_sequences)
                term.details.append(f"переброс ≤{threshold}: {count}")

        explode = flags.get("explode")
        if explode:
            flag, threshold = explode
            infinite = flag == "ie"
            to_check = list(working_rolls)
            budget = self.MAX_EXTRA_ROLLS
            while to_check and budget > 0:
                current = to_check.pop(0)
                if current >= threshold:
                    new_roll = random.randint(1, num_sides)
                    working_rolls.append(new_roll)
                    term.all_rolls.append(new_roll)
                    term.exploded_rolls.append(new_roll)
                    budget -= 1
                    if infinite and new_roll >= threshold:
                        to_check.append(new_roll)
            if budget == 0 and infinite and to_check:
                term.warnings.append(
                    f"Достигнут защитный лимит {self.MAX_EXTRA_ROLLS} дополнительных взрывов."
                )
            if term.exploded_rolls:
                term.details.append(f"взрыв ≥{threshold}: +{len(term.exploded_rolls)}")

        selected_rolls = working_rolls.copy()
        keepdrop = flags.get("keepdrop")
        if keepdrop:
            flag, amount = keepdrop
            if amount > len(selected_rolls):
                raise ValueError(
                    f"`{flag}{amount}` нельзя применить: после перебросов/взрывов доступно только {len(selected_rolls)} кубиков."
                )
            indexed = list(enumerate(selected_rolls))
            if flag in ("k", "kh"):
                keep_indexes = (
                    {idx for idx, _ in sorted(indexed, key=lambda x: x[1], reverse=True)[:amount]}
                    if amount
                    else set()
                )
                term.details.append(f"оставлено лучших: {amount}")
            elif flag == "kl":
                keep_indexes = (
                    {idx for idx, _ in sorted(indexed, key=lambda x: x[1])[:amount]} if amount else set()
                )
                term.details.append(f"оставлено худших: {amount}")
            elif flag in ("d", "dl"):
                drop_indexes = (
                    {idx for idx, _ in sorted(indexed, key=lambda x: x[1])[:amount]} if amount else set()
                )
                keep_indexes = {idx for idx, _ in indexed if idx not in drop_indexes}
                term.details.append(f"сброшено худших: {amount}")
            else:  # dh
                drop_indexes = (
                    {idx for idx, _ in sorted(indexed, key=lambda x: x[1], reverse=True)[:amount]}
                    if amount
                    else set()
                )
                keep_indexes = {idx for idx, _ in indexed if idx not in drop_indexes}
                term.details.append(f"сброшено лучших: {amount}")

            term.kept_dice = [value for idx, value in indexed if idx in keep_indexes]
            term.dropped_dice = [value for idx, value in indexed if idx not in keep_indexes]
            selected_rolls = term.kept_dice.copy()

        term.final_rolls = selected_rolls.copy()

        target = flags.get("target")
        if target:
            _, target_value = target
            term.target = target_value
            term.successes = sum(1 for value in selected_rolls if value >= target_value)
            term.failures = len(selected_rolls) - term.successes
            term.botches = sum(1 for value in selected_rolls if value == 1)
            term.subtotal = float(term.successes)
            term.details.append(f"цель ≥{target_value}: {term.successes} успех., {term.failures} провал.")
        else:
            term.subtotal = float(sum(selected_rolls))

        return term

    def _roll_once(self, expression: str) -> DiceResult:
        res = DiceResult()
        res.expression = expression.strip()
        core_expression, global_modifier = self._extract_global_modifier(res.expression)
        additive_terms = self._split_additive_terms(core_expression)

        parsed_terms: list[DiceTermResult] = []
        total_base_dice = 0
        for sign, text in additive_terms:
            term = self._parse_term(text, sign)
            if term.kind == "dice":
                total_base_dice += term.num_dice
            parsed_terms.append(term)

        if total_base_dice > self.MAX_DICE_PER_SET:
            raise ValueError(
                f"В одном наборе можно бросить максимум {self.MAX_DICE_PER_SET} базовых кубиков суммарно."
            )

        res.terms = parsed_terms
        res.total = sum(term.sign * term.subtotal for term in parsed_terms)

        if global_modifier:
            op, value = global_modifier
            before = res.total
            if op == "*":
                res.total *= value
                res.global_modifier = (op, value, before)
            elif value == 0:
                res.warnings.append("Деление на ноль пропущено; итог оставлен без изменения.")
            else:
                res.total /= value
                res.global_modifier = (op, value, before)

        for term in parsed_terms:
            if term.kind != "dice":
                continue
            res.dice_rolls.extend(term.final_rolls)
            res.all_rolls.extend(term.all_rolls)
            res.exploded_rolls.extend(term.exploded_rolls)
            res.kept_dice.extend(term.kept_dice)
            res.dropped_dice.extend(term.dropped_dice)
            res.rerolled = res.rerolled or bool(term.reroll_sequences)
            res.successes += term.successes
            res.failures += term.failures
            res.botches += term.botches
            res.warnings.extend(term.warnings)

        return res

    def get_help_text(self) -> str:
        return """
🎲 **Команда `/кубик` — продвинутая система бросков**

**Базовые формулы:**
• `XdY` — X кубиков с Y гранями: `2d6`
• `1d6 + 1d4` — складывать разные типы кубиков в одном результате
• `2d6 + 1d8 + 5` — кубики и обычные числовые модификаторы
• `1d20 * 2` / `1d20 / 2` — умножить или разделить итог всей формулы
• `N XdY` — N независимых наборов: `6 4d6 k3`
• `A; B; C` — отдельные формулы; каждая выводится отдельно и не суммируется с соседними
• `! текст` — комментарий к конкретной формуле

**Модификаторы кубиков** *(относятся к кубику непосредственно перед ними)*:
• `eZ` — один взрыв при результате ≥ Z: `3d6 e6`
• `ieZ` — цепные взрывы
• `kZ` / `khZ` — оставить Z лучших: `4d6 k3`
• `klZ` — оставить Z худших
• `dZ` / `dlZ` — сбросить Z худших
• `dhZ` — сбросить Z лучших
• `rZ` — один раз перебросить кубики ≤ Z
• `irZ` — повторять переброс ≤ Z до выхода выше порога или защитного лимита
• `tZ` — считать успехи при ≥ Z вместо суммы данного кубикового терма

**Примеры:**
• `1d6 + 1d4`
• `4d6 k3 + 1d8`
• `2d10 r2 + 1d6 e6 + 3`
• `1d20 + 5; 2d6 + 1d4 ! урон`

**Алиасы:**
• `dndstats` — 6 наборов 4d6 k3
• `attack` — 1d20
• `+d20` — преимущество, 2d20 d1
• `-d20` — помеха, 2d20 kl1
• `stat` — 4d6 k3
• `save` — 1d20 + 5

**Ограничения:** до 100 базовых кубиков суммарно на набор, до 100 граней, до 20 наборов и до 4 формул через `;`.
Неверные или неоднозначные части формулы теперь отклоняются с понятной причиной вместо молчаливого исправления.
"""
