"""Persistence operations for the jail mechanic, independent from Discord."""

from datetime import datetime

from db.models import JailSentence
from services.jail_time import normalize_jail_datetime


def save_jail_sentence_db(
    session_factory,
    jail_role_id: int,
    guild_id: int,
    user_id: int,
    moderator_id: int,
    reason: str,
    expires_at: datetime,
) -> None:
    """Создаёт или обновляет срок темницы в базе данных."""

    if session_factory is None:
        return

    session = session_factory()

    try:
        record = (
            session.query(JailSentence)
            .filter_by(
                guild_id=str(guild_id),
                user_id=str(user_id),
            )
            .first()
        )

        if record is None:
            record = JailSentence(
                guild_id=str(guild_id),
                user_id=str(user_id),
                role_id=str(jail_role_id),
                moderator_id=str(moderator_id),
                reason=reason,
                expires_at=expires_at,
            )

            session.add(record)

        else:
            record.role_id = str(jail_role_id)
            record.moderator_id = str(moderator_id)
            record.reason = reason
            record.expires_at = expires_at

        session.commit()

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def delete_jail_sentence_db(
    session_factory,
    guild_id: int,
    user_id: int,
) -> None:
    """Удаляет завершившийся срок из базы."""

    if session_factory is None:
        return

    session = session_factory()

    try:
        (
            session.query(JailSentence)
            .filter_by(
                guild_id=str(guild_id),
                user_id=str(user_id),
            )
            .delete(synchronize_session=False)
        )

        session.commit()

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def load_jail_sentences_db(session_factory) -> list[tuple[int, int, datetime]]:
    """Загружает действующие сроки после перезапуска бота."""

    if session_factory is None:
        return []

    session = session_factory()

    try:
        rows = session.query(JailSentence).all()

        return [
            (
                int(row.guild_id),
                int(row.user_id),
                normalize_jail_datetime(row.expires_at),
            )
            for row in rows
        ]

    finally:
        session.close()
