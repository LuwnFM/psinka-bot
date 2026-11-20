"""Discord presentation adapters; no parser, model or persistence logic here."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

import disnake

from repositories.model_success import DBManager
from services.dice import DiceParser, DiceResult
from services.dice_format import _dice_paginate, _dice_result_block

logger = logging.getLogger(__name__)


async def _send_ephemeral_error(
    interaction: disnake.CommandInteraction, message: str
) -> None:
    """Send errors via the correct Disnake response path.

    A slash interaction has exactly one initial response. After a defer or
    initial send, subsequent messages must use the follow-up webhook.
    """
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except disnake.HTTPException:
        logger.exception("Не удалось сообщить об ошибке в Discord")


async def respond_to_cube(
    interaction: disnake.CommandInteraction,
    formula: str | None,
    dice_engine: DiceParser,
) -> None:
    """Render roll help/results using the unchanged original Discord embeds."""
    if not formula:
        help_embed = disnake.Embed(
            title="🎲 ПсИИнка: Справка по кубикам",
            description=dice_engine.get_help_text(),
            color=0xFF8844,
            timestamp=datetime.now()
        )
        help_embed.set_footer(text="ПсИИнка бот | Dice Roller 🐾")
        await interaction.response.send_message(embed=help_embed)
        return

    await interaction.response.defer()

    try:
        results = dice_engine.parse(formula)
        if not results:
            raise ValueError("Не удалось разобрать формулу.")

        grouped: dict[int, list[DiceResult]] = {}
        for result in results:
            grouped.setdefault(result.formula_index, []).append(result)

        for formula_index in sorted(grouped):
            formula_results = grouped[formula_index]
            first = formula_results[0]
            header_lines = [f"*подбрасывает лапой* Формула: `{first.formula_raw}` 🐾"]
            if first.formula_expanded and first.formula_expanded.strip() != first.formula_raw.split('!', 1)[0].strip():
                header_lines.append(f"Разобрано как: `{first.formula_expanded}`")
            header = "\n".join(header_lines)
            blocks = [_dice_result_block(result) for result in formula_results]
            pages = _dice_paginate(header, blocks)

            for page_index, page in enumerate(pages):
                title = f"🎲 Кубик — формула {formula_index + 1}/{first.formula_count}"
                if len(pages) > 1:
                    title += f" · стр. {page_index + 1}/{len(pages)}"
                embed = disnake.Embed(
                    title=title,
                    description=page,
                    color=0x00AAFF,
                    timestamp=datetime.now(),
                )
                embed.set_footer(text="ПсИИнка бот | Dice Roller 🐾")
                embed.check_limits()
                # Каждая формула через `;` уходит отдельным сообщением и не суммируется с соседними.
                await interaction.followup.send(embed=embed)

    except ValueError as e:
        shown_formula = formula if len(formula) <= 1200 else formula[:1197] + "..."
        error_embed = disnake.Embed(
            title="❌ ПсИИнка не понял формулу",
            description=(
                f"*склонил голову набок* Не могу разобрать: `{shown_formula}` 🐕\n\n"
                f"**Причина:** {e}"
            ),
            color=0xFF4444,
            timestamp=datetime.now(),
        )
        error_embed.add_field(
            name="💡 Помощь",
            value="Используй `/кубик` без параметров — я покажу синтаксис и примеры.",
            inline=False,
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)
    except Exception as e:
        logger.error(f"Error in /cube: {e}", exc_info=True)
        error_embed = disnake.Embed(
            title="❌ Ошибка броска",
            description="*ПсИИнка растерянно посмотрел на кубики.* Произошла внутренняя ошибка; она записана в лог.",
            color=0xFF4444,
            timestamp=datetime.now(),
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)


async def respond_to_bark(interaction: disnake.CommandInteraction, bot: disnake.Client) -> None:
    """Report bot latency without blocking Discord event handling."""
    try:
        ping_ms = round(bot.latency * 1000)
        status = "🟢" if ping_ms < 100 else "🟡" if ping_ms < 300 else "🔴"

        embed = disnake.Embed(
            title="🐕 Гав! ПсИИнка на связи!",
            description=f"{status} **Пинг:** `{ping_ms} мс` *тяв!*",
            color=0x00FF88 if ping_ms < 100 else 0xFFAA00 if ping_ms < 300 else 0xFF4444,
            timestamp=datetime.now()
        )
        embed.add_field(name="📊 Статус", value="Бот работает нормально *виляет хвостом*", inline=False)
        embed.set_footer(text="ПсИИнка бот | Health Check 🐾")

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        logger.error("Error in /bark: %s", e, exc_info=True)
        await _send_ephemeral_error(interaction, f"❌ Гав! Ошибка: {str(e)[:100]}")


async def respond_to_status(
    interaction: disnake.CommandInteraction,
    check_access: Callable[[disnake.CommandInteraction], Awaitable[bool]],
    db_manager: DBManager,
) -> None:
    """Render the original AI model health summary without blocking the event loop."""
    try:
        if not await check_access(interaction):
            return
        await interaction.response.defer()

        top = await asyncio.to_thread(db_manager.get_top_models, 10)

        embed = disnake.Embed(
            title="📊 ПсИИнка отчитывается",
            description="*виляет хвостом* Вот моя статистика, хозяин! 🐕",
            color=0x00FF88,
            timestamp=datetime.now()
        )

        if top:
            stats_text = ""
            for i, (p, m, lat) in enumerate(top, 1):
                medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i - 1] if i <= 5 else f"{i}."
                stats_text += f"{medal} `{p}` / `{m}` — `{lat}мс`\n"

            embed.add_field(name="🏆 Топ-10 моделей", value=stats_text, inline=False)
        else:
            embed.add_field(name="📭 Данные", value="Нет записей. *Гавкни* `/скажи` для начала сбора статистики!",
                            inline=False)

        db_state = "✅ Подключена *гав!*" if db_manager.is_connected() else "⚠️ Отключена *скулит*"
        data_state = "✅ Есть записи" if await asyncio.to_thread(db_manager.has_data) else "📭 Записей пока нет"
        embed.add_field(name="🔧 Режим", value=f"Экономия ресурсов (No Warmup)\nБД: {db_state}\nДанные: {data_state}", inline=False)
        embed.set_footer(text="ПсИИнка бот | Statistics 🐾")

        await interaction.edit_original_response(embed=embed)

    except Exception as e:
        logger.error("Error in /status: %s", e, exc_info=True)
        await _send_ephemeral_error(interaction, f"❌ Гав! Ошибка: {str(e)[:100]}")
