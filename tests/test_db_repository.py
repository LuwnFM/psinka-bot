"""Smoke tests of the independent SQLAlchemy model-success repository."""

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, ModelSuccessLog
from repositories.model_success import DBManager


def test_model_metrics_lifecycle(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'metrics.sqlite3'}")
    Base.metadata.create_all(engine)
    manager = DBManager(sessionmaker(bind=engine))
    try:
        assert manager.is_connected()
        assert not manager.has_data()
        manager.log_success("Groq", "model-a", 40)
        manager.log_success("Groq", "model-a", 60)
        manager.log_success("OpenRouter", "model-b", 20)
        assert manager.has_data()
        assert manager.get_top_models(2)[0] == ("Groq", "model-a", 50)
        assert manager.get_all_models() == [("Groq", "model-a"), ("OpenRouter", "model-b")]
        report = manager.export_to_csv()
        assert report is not None
        assert "model-a" in report and "model-b" in report
        with sessionmaker(bind=engine)() as session:
            rows = session.query(ModelSuccessLog).all()
            assert len(rows) == 2
            assert all(isinstance(r.last_success_at, datetime) for r in rows)
    finally:
        engine.dispose()


def test_no_database_config_does_not_write() -> None:
    manager = DBManager(None)
    assert not manager.is_connected()
    assert not manager.has_data()
    assert manager.export_to_csv() is None
    assert manager.get_top_models() == []


def test_clear_all_stats_returns_exact_count(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'cleanup.sqlite3'}")
    Base.metadata.create_all(engine)
    manager = DBManager(sessionmaker(bind=engine))
    try:
        manager.log_success("Groq", "model-a", 60)
        manager.log_success("Groq", "model-a", 40)
        manager.log_success("OpenRouter", "model-b", 30)
        assert manager.clear_all() == 2
        assert manager.clear_all() == 0
        assert manager.get_all_models() == []
    finally:
        engine.dispose()


def test_clear_without_database_does_not_claim_success() -> None:
    assert DBManager(None).clear_all() is None


def test_batch_import_preserves_duplicate_metrics_and_average(tmp_path) -> None:
    """The original per-observation mean calculation must be unchanged."""
    engine = create_engine(f"sqlite:///{tmp_path / 'import.sqlite3'}")
    Base.metadata.create_all(engine)
    manager = DBManager(sessionmaker(bind=engine, autoflush=False))
    try:
        manager.log_success("Groq", "model-a", 100)
        assert manager.import_pending_records([
            ("Groq", "model-a", 30),
            ("Groq", "model-a", 50),
            ("OpenRouter", "model-b", 20),
            ("OpenRouter", "model-b", 40),
        ])
        with sessionmaker(bind=engine)() as session:
            groq = session.query(ModelSuccessLog).filter_by(
                provider="Groq", model_name="model-a"
            ).one()
            router = session.query(ModelSuccessLog).filter_by(
                provider="OpenRouter", model_name="model-b"
            ).one()
            assert (groq.success_count, groq.avg_latency_ms) == (3, 60)
            assert (router.success_count, router.avg_latency_ms) == (2, 30)
    finally:
        engine.dispose()


def test_batch_import_rolls_back_every_observation_on_failure(tmp_path) -> None:
    """An invalid trailing observation must not partially commit earlier rows."""
    engine = create_engine(f"sqlite:///{tmp_path / 'rollback.sqlite3'}")
    Base.metadata.create_all(engine)
    manager = DBManager(sessionmaker(bind=engine, autoflush=False))
    try:
        manager.log_success("Groq", "previous", 90)
        assert not manager.import_pending_records([
            ("Groq", "previous", 10),
            ("OpenRouter", "new", 20),
            ("Groq", None, 99),
        ])
        with sessionmaker(bind=engine)() as session:
            original = session.query(ModelSuccessLog).all()
            assert len(original) == 1
            assert original[0].model_name == "previous"
            assert (original[0].success_count, original[0].avg_latency_ms) == (1, 90)
    finally:
        engine.dispose()


def test_batch_import_requires_database() -> None:
    assert not DBManager(None).import_pending_records([("Groq", "example", 10)])
