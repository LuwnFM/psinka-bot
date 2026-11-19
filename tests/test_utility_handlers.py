"""Mocked Discord interaction regression tests for extracted utility handlers."""

import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from handlers.utility_commands import respond_to_bark, respond_to_cube
from services.dice import DiceParser


@pytest.mark.asyncio
async def test_bark_keeps_health_embed_contract() -> None:
    response = SimpleNamespace(send_message=AsyncMock())
    interaction = SimpleNamespace(response=response)
    bot = SimpleNamespace(latency=0.075)
    await respond_to_bark(interaction, bot)
    response.send_message.assert_awaited_once()
    embed = response.send_message.await_args.kwargs["embed"]
    assert "ПсИИнка" in embed.title
    assert "75 мс" in embed.description


@pytest.mark.asyncio
async def test_dice_help_retains_original_examples() -> None:
    interaction = SimpleNamespace(
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await respond_to_cube(interaction, None, DiceParser())
    interaction.response.send_message.assert_awaited_once()
    interaction.response.defer.assert_not_awaited()
    assert "Справка по кубикам" in interaction.response.send_message.await_args.kwargs["embed"].title


@pytest.mark.asyncio
async def test_two_dice_formulas_create_separate_followups() -> None:
    random.seed(42)
    interaction = SimpleNamespace(
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await respond_to_cube(interaction, "1d6; 1d8", DiceParser())
    interaction.response.defer.assert_awaited_once()
    assert interaction.followup.send.await_count == 2
    sent = [entry.kwargs["embed"] for entry in interaction.followup.send.await_args_list]
    assert "формула 1/2" in sent[0].title
    assert "формула 2/2" in sent[1].title


@pytest.mark.asyncio
async def test_invalid_dice_formula_is_ephemeral_error() -> None:
    interaction = SimpleNamespace(
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await respond_to_cube(interaction, "abc___invalid", DiceParser())
    interaction.followup.send.assert_awaited_once()
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
