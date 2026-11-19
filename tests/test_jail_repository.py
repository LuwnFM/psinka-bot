"""Jail persistence integration tests on real SQLite sessions."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, JailSentence
from repositories.jail import (
    delete_jail_sentence_db,
    load_jail_sentences_db,
    save_jail_sentence_db,
)
from services.jail_time import normalize_jail_datetime


def test_jail_sentence_create_update_recover_and_delete(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'jail.sqlite3'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    deadline = datetime(2026, 12, 1, 10, tzinfo=timezone.utc)
    try:
        save_jail_sentence_db(session_factory, 100, 1, 2, 3, "Первый срок", deadline)
        assert load_jail_sentences_db(session_factory) == [(1, 2, deadline)]

        updated = deadline + timedelta(minutes=20)
        save_jail_sentence_db(session_factory, 200, 1, 2, 4, "Продление", updated)
        with session_factory() as session:
            entries = session.query(JailSentence).all()
            assert len(entries) == 1
            assert entries[0].role_id == "200"
            assert entries[0].moderator_id == "4"
            assert entries[0].reason == "Продление"
        assert load_jail_sentences_db(session_factory) == [(1, 2, updated)]

        delete_jail_sentence_db(session_factory, 1, 2)
        assert load_jail_sentences_db(session_factory) == []
    finally:
        engine.dispose()


def test_jail_without_database_is_noop() -> None:
    deadline = datetime(2026, 12, 1, tzinfo=timezone.utc)
    save_jail_sentence_db(None, 100, 1, 2, 3, "test", deadline)
    delete_jail_sentence_db(None, 1, 2)
    assert load_jail_sentences_db(None) == []


def test_naive_deadline_is_interpreted_as_utc() -> None:
    assert normalize_jail_datetime(datetime(2026, 12, 1, 11)) == datetime(
        2026, 12, 1, 11, tzinfo=timezone.utc
    )
