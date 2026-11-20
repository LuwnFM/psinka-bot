"""Deployment preflight tests: no live credentials, DB connection or Discord calls."""

from dataclasses import replace

from core.config import BotSettings
from core.preflight import check_deployment


def _settings() -> BotSettings:
    return BotSettings(
        database_url="postgresql://user:private-password@db.example.invalid/psinka",
        discord_token="offline-test-discord-token",  # noqa: S106 - test-only value
        groq_token="offline-test-groq-key",  # noqa: S106 - test-only value
        openrouter_token=None,
        is_railway=False,
        owner_id=123,
        required_role_id=0,
        debug=False,
        max_concurrent=2,
        proxy_refresh_hours=6,
        use_proxy=False,
    )


def test_valid_offline_configuration_passes_without_network(tmp_path) -> None:
    workbook = tmp_path / "mercenaries.xlsx"
    workbook.write_bytes(b"offline fixture")
    assert check_deployment(_settings(), workbook=workbook) == []


def test_placeholder_discord_token_is_rejected_without_leaking(tmp_path) -> None:
    workbook = tmp_path / "mercenaries.xlsx"
    workbook.write_bytes(b"fixture")
    for value in (None, "", "your_discord_bot_token_here", "  bad token  "):
        findings = check_deployment(replace(_settings(), discord_token=value), workbook=workbook)
        assert any(f.severity == "ERROR" and "DISCORD_TOKEN" in f.message for f in findings)
        assert all("private-password" not in f.message for f in findings)


def test_missing_or_empty_workbook_is_fatal(tmp_path) -> None:
    workbook = tmp_path / "mercenaries.xlsx"
    assert any(f.severity == "ERROR" for f in check_deployment(_settings(), workbook=workbook))
    workbook.write_bytes(b"")
    assert any("пуста" in f.message for f in check_deployment(_settings(), workbook=workbook))


def test_optional_integrations_are_warnings(tmp_path) -> None:
    workbook = tmp_path / "mercenaries.xlsx"
    workbook.write_bytes(b"fixture")
    settings = replace(_settings(), owner_id=0, database_url=None, groq_token=None, openrouter_token=None)
    findings = check_deployment(settings, workbook=workbook)
    assert len(findings) == 3
    assert all(f.severity == "WARNING" for f in findings)


def test_malformed_database_url_is_fatal_without_exposing_password(tmp_path) -> None:
    workbook = tmp_path / "mercenaries.xlsx"
    workbook.write_bytes(b"fixture")
    marker = "test-marker-not-for-logs"
    findings = check_deployment(
        replace(_settings(), database_url=f"this is not a URL {marker}"),
        workbook=workbook,
    )
    assert any(f.severity == "ERROR" and "DATABASE_URL" in f.message for f in findings)
    assert all(marker not in f.message for f in findings)


def test_non_postgres_database_raises_warning_not_failure(tmp_path) -> None:
    workbook = tmp_path / "mercenaries.xlsx"
    workbook.write_bytes(b"fixture")
    findings = check_deployment(
        replace(_settings(), database_url="sqlite:///:memory:"), workbook=workbook
    )
    assert len(findings) == 1
    assert findings[0].severity == "WARNING"
