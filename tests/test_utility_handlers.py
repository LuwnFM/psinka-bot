"""Mocked Discord interaction regression tests for extracted utility handlers."""

import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from handlers.utility_commands import respond_to_bark, respond_to_cube, respond_to_status
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


@pytest.mark.asyncio
async def test_status_reports_ranked_models_and_database_connection() -> None:
    interaction = SimpleNamespace(
        response=SimpleNamespace(defer=AsyncMock()),
        edit_original_response=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    permissions = AsyncMock(return_value=True)
    storage = Mock()
    storage.get_top_models.return_value = [("Groq", "model-a", 25)]
    storage.has_data.return_value = True
    storage.is_connected.return_value = True
    await respond_to_status(interaction, permissions, storage)
    permissions.assert_awaited_once_with(interaction)
    interaction.response.defer.assert_awaited_once()
    embed = interaction.edit_original_response.await_args.kwargs["embed"]
    assert "model-a" in embed.fields[0].value
    assert "Подключена" in embed.fields[1].value


@pytest.mark.asyncio
async def test_status_denied_access_sends_no_details() -> None:
    interaction = SimpleNamespace(
        response=SimpleNamespace(defer=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    permissions = AsyncMock(return_value=False)
    storage = Mock()
    await respond_to_status(interaction, permissions, storage)
    interaction.response.defer.assert_not_awaited()
    storage.get_top_models.assert_not_called()


@pytest.mark.asyncio
async def test_status_failure_before_defer_uses_initial_response() -> None:
    """Do not send an unauthenticated followup when an access check raises."""
    interaction = SimpleNamespace(
        response=SimpleNamespace(
            defer=AsyncMock(),
            is_done=Mock(return_value=False),
            send_message=AsyncMock(),
        ),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    permissions = AsyncMock(side_effect=RuntimeError("permission service offline"))
    storage = Mock()
    await respond_to_status(interaction, permissions, storage)
    interaction.response.defer.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once()
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
    interaction.followup.send.assert_not_awaited()
    storage.get_top_models.assert_not_called()


@pytest.mark.asyncio
async def test_status_failure_after_defer_uses_ephemeral_followup() -> None:
    """A deferred interaction cannot receive a second initial response."""
    interaction = SimpleNamespace(
        response=SimpleNamespace(
            defer=AsyncMock(),
            is_done=Mock(return_value=True),
            send_message=AsyncMock(),
        ),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    storage = Mock()
    storage.get_top_models.side_effect = RuntimeError("database offline")
    await respond_to_status(interaction, AsyncMock(return_value=True), storage)
    interaction.response.defer.assert_awaited_once()
    interaction.followup.send.assert_awaited_once()
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
    interaction.response.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_bark_error_before_initial_reply_is_ephemeral() -> None:
    """A bad latency value still yields an actionable private error message."""
    interaction = SimpleNamespace(
        response=SimpleNamespace(
            send_message=AsyncMock(),
            is_done=Mock(return_value=False),
        ),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await respond_to_bark(interaction, SimpleNamespace(latency=None))
    interaction.response.send_message.assert_awaited_once()
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
    interaction.followup.send.assert_not_awaited()
