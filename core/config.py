"""Runtime configuration parsed once from the bot's environment."""

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

from core.paths import ENV_FILE

logger = logging.getLogger(__name__)


def safe_int_env(name: str, default: int = 0) -> int:
    """Read an integer setting, preserving the original invalid-value fallback."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning("Invalid integer for %s; using %s", name, default)
        return default


def env_bool(name: str, default: bool = False) -> bool:
    """Interpret the original English and Russian truth values."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "да", "on"}


@dataclass(frozen=True)
class BotSettings:
    """Validated runtime settings; optional integrations may remain unset."""

    database_url: str | None
    discord_token: str | None
    groq_token: str | None
    openrouter_token: str | None
    is_railway: bool
    owner_id: int
    required_role_id: int
    debug: bool
    max_concurrent: int
    proxy_refresh_hours: int
    use_proxy: bool

    @classmethod
    def from_environment(cls) -> "BotSettings":
        """Load .env and preserve existing defaults and feature flags."""
        load_dotenv(ENV_FILE)
        return cls(
            database_url=os.getenv("DATABASE_URL") or None,
            discord_token=os.getenv("DISCORD_TOKEN") or None,
            groq_token=os.getenv("GROQ_TOKEN") or None,
            openrouter_token=os.getenv("OPENR_TOKEN") or None,
            is_railway=env_bool("RAILWAY") or env_bool("IS_RAILWAY"),
            owner_id=safe_int_env("OWNER_ID"),
            required_role_id=safe_int_env("REQUIRED_ROLE_ID"),
            debug=env_bool("DEBUG"),
            max_concurrent=max(1, safe_int_env("MAX_CONCURRENT", 5)),
            proxy_refresh_hours=max(1, safe_int_env("PROXY_REFRESH_HOURS", 6)),
            use_proxy=env_bool("USE_PROXY"),
        )
