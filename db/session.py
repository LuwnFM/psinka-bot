"""Explicit database initialization, never performed on module import."""

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base


def init_db(database_url: str | None):
    """Create engine and DB tables after all model modules are imported.

    Args:
        database_url: SQLAlchemy URL, None disables persistence.

    Returns:
        Pair of engine and session factory or (None, None) on failure.
    """
    if not database_url:
        logging.warning("⚠️ DATABASE_URL не найден. Работа с БД отключена (экономия ресурсов).")
        return None, None
    try:
        engine = create_engine(database_url, echo=False, future=True, pool_pre_ping=True, pool_size=5, max_overflow=10)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        logging.info("✅ База данных Neon подключена.")
        return engine, factory
    except Exception:
        logging.exception("❌ Ошибка подключения к БД")
        return None, None
