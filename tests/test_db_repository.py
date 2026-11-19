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
