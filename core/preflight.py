"""Offline deployment preflight: validate local configuration without connecting to APIs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from core.config import BotSettings
from core.paths import MERCENARY_DB_FILE

logger = logging.getLogger(__name__)
_PLACEHOLDERS = {"your_discord_bot_token_here", "replace_me", "changeme", "your_token_here"}


@dataclass(frozen=True)
class PreflightFinding:
    """An actionable deployment diagnostic with no credential values."""

    severity: str
    message: str


def check_deployment(
    settings: BotSettings,
    *,
    workbook: Path = MERCENARY_DB_FILE,
) -> list[PreflightFinding]:
    """Inspect release prerequisites without network, database or filesystem writes."""
    findings: list[PreflightFinding] = []
    token = (settings.discord_token or "").strip()
    if not token or token.lower() in _PLACEHOLDERS:
        findings.append(PreflightFinding("ERROR", "DISCORD_TOKEN отсутствует или содержит шаблонное значение."))
    elif any(char.isspace() for char in token):
        findings.append(PreflightFinding("ERROR", "DISCORD_TOKEN содержит пробелы или переносы строк."))

    if not workbook.is_file():
        findings.append(PreflightFinding("ERROR", f"Отсутствует Excel-база наёмников: {workbook.name}."))
    elif workbook.stat().st_size == 0:
        findings.append(PreflightFinding("ERROR", f"Excel-база наёмников пуста: {workbook.name}."))

    if settings.owner_id == 0:
        findings.append(PreflightFinding("WARNING", "OWNER_ID не указан: команды владельца будут недоступны."))
    if not settings.groq_token and not settings.openrouter_token:
        findings.append(
            PreflightFinding("WARNING", "Не указаны GROQ_TOKEN и OPENR_TOKEN: остаётся только g4f fallback.")
        )

    if settings.database_url:
        try:
            url = make_url(settings.database_url)
        except (ArgumentError, ValueError):
            findings.append(PreflightFinding("ERROR", "DATABASE_URL имеет неверный формат URL."))
        else:
            if url.get_backend_name() != "postgresql":
                findings.append(
                    PreflightFinding("WARNING", "DATABASE_URL указывает не на PostgreSQL; проверьте окружение.")
                )
    else:
        findings.append(PreflightFinding("WARNING", "DATABASE_URL отсутствует: функции БД будут ограничены."))

    return findings


def main() -> int:
    """Print safe diagnostics and return a failing exit code only for fatal configuration."""
    settings = BotSettings.from_environment()
    findings = check_deployment(settings)
    for finding in findings:
        if finding.severity == "ERROR":
            logger.error("%s", finding.message)
        else:
            logger.warning("%s", finding.message)
    errors = sum(finding.severity == "ERROR" for finding in findings)
    if errors:
        logger.error("Предстартовая проверка: %d критических проблем. Discord не запускаем.", errors)
        return 1
    logger.info("Предстартовая проверка пройдена. Внешние подключения не проверялись.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
