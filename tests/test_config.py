"""Environment settings behavior without Discord or live API credentials."""

from core.config import BotSettings, env_bool, safe_int_env


def test_invalid_number_uses_previous_default(monkeypatch) -> None:
    monkeypatch.setenv("MAX_CONCURRENT", "abc")
    monkeypatch.setenv("USE_PROXY", "да")
    assert safe_int_env("MAX_CONCURRENT", 5) == 5
    assert env_bool("USE_PROXY") is True


def test_concurrency_and_refresh_minimum(monkeypatch) -> None:
    monkeypatch.setenv("MAX_CONCURRENT", "0")
    monkeypatch.setenv("PROXY_REFRESH_HOURS", "-3")
    settings = BotSettings.from_environment()
    assert settings.max_concurrent == 1
    assert settings.proxy_refresh_hours == 1


def test_optional_tokens_do_not_block_settings_parsing(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_TOKEN", raising=False)
    monkeypatch.delenv("OPENR_TOKEN", raising=False)
    settings = BotSettings.from_environment()
    assert settings.groq_token is None
    assert settings.openrouter_token is None
