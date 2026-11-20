"""SQLAlchemy repository for routing statistics and model performance metrics."""

import csv
import io
import logging
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from db.models import ModelSuccessLog

logger = logging.getLogger(__name__)


class DBManager:
    """Persist AI-provider success metrics with a bounded 200-row history."""

    def __init__(self, session_factory: sessionmaker[Session] | None) -> None:
        """Store a reusable session factory without opening a connection."""
        self.SessionLocal = session_factory

    def log_success(self, provider: str, model: str, latency_ms: int) -> None:
        """Record one success and update its arithmetic mean latency."""
        if self.SessionLocal is None:
            return
        with self.SessionLocal() as session:
            try:
                record = session.query(ModelSuccessLog).filter_by(
                    provider=provider, model_name=model
                ).first()
                if record:
                    record.success_count += 1
                    record.avg_latency_ms = int(
                        (record.avg_latency_ms * (record.success_count - 1) + latency_ms)
                        / record.success_count
                    )
                    record.last_success_at = datetime.now(timezone.utc)
                else:
                    session.add(
                        ModelSuccessLog(
                            provider=provider,
                            model_name=model,
                            success_count=1,
                            last_success_at=datetime.now(timezone.utc),
                            avg_latency_ms=latency_ms,
                        )
                    )
                session.commit()
                self._cleanup_old_records(session)
            except SQLAlchemyError:
                session.rollback()
                logger.exception("Ошибка записи статистики модели в БД")

    def _cleanup_old_records(self, session: Session) -> None:
        """Keep the same oldest-first retention behavior as the original bot."""
        try:
            count = session.query(ModelSuccessLog).count()
            if count <= 200:
                return
            old_ids = (
                session.query(ModelSuccessLog.id)
                .order_by(ModelSuccessLog.last_success_at.asc())
                .limit(count - 200)
                .all()
            )
            if old_ids:
                identifiers = [item[0] for item in old_ids]
                session.query(ModelSuccessLog).filter(
                    ModelSuccessLog.id.in_(identifiers)
                ).delete(synchronize_session=False)
                session.commit()
        except SQLAlchemyError:
            session.rollback()
            logger.exception("Не удалось удалить старые записи статистики моделей")

    def get_top_models(self, limit: int = 10) -> list[tuple[str, str, int]]:
        """Return models sorted by success count and then average latency."""
        if self.SessionLocal is None:
            return []
        with self.SessionLocal() as session:
            try:
                results = (
                    session.query(
                        ModelSuccessLog.provider,
                        ModelSuccessLog.model_name,
                        ModelSuccessLog.avg_latency_ms,
                    )
                    .order_by(
                        ModelSuccessLog.success_count.desc(),
                        ModelSuccessLog.avg_latency_ms.asc(),
                    )
                    .limit(limit)
                    .all()
                )
                return [(row.provider, row.model_name, row.avg_latency_ms) for row in results]
            except SQLAlchemyError:
                logger.exception("Не удалось прочитать топ моделей")
                return []

    def export_to_csv(self) -> str | None:
        """Export original CSV columns, retaining the existing sort order."""
        if self.SessionLocal is None:
            return None
        with self.SessionLocal() as session:
            try:
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(
                    ["ID", "Provider", "Model", "Success Count", "Avg Latency (ms)", "Last Success"]
                )
                records = session.query(ModelSuccessLog).order_by(
                    ModelSuccessLog.success_count.desc()
                ).all()
                for record in records:
                    writer.writerow(
                        [
                            record.id,
                            record.provider,
                            record.model_name,
                            record.success_count,
                            record.avg_latency_ms,
                            record.last_success_at,
                        ]
                    )
                return output.getvalue()
            except SQLAlchemyError:
                logger.exception("Ошибка экспорта статистики в CSV")
                return None

    def import_pending_records(self, records: list[tuple[str, str, int]]) -> bool:
        """Commit the entire temporary model log in one transaction.

        The owner command must not delete its CSV unless every observation
        reaches the database. Duplicate model names are expected; success
        counts and integer average latencies follow the original algorithm.
        """
        if self.SessionLocal is None:
            return False
        with self.SessionLocal() as session:
            try:
                for provider, model, latency_ms in records:
                    record = session.query(ModelSuccessLog).filter_by(
                        provider=provider, model_name=model
                    ).first()
                    if record is None:
                        session.add(
                            ModelSuccessLog(
                                provider=provider,
                                model_name=model,
                                success_count=1,
                                last_success_at=datetime.now(timezone.utc),
                                avg_latency_ms=latency_ms,
                            )
                        )
                    else:
                        record.success_count += 1
                        record.avg_latency_ms = int(
                            (record.avg_latency_ms * (record.success_count - 1) + latency_ms)
                            / record.success_count
                        )
                        record.last_success_at = datetime.now(timezone.utc)

                    # The production factory sets autoflush=False; flush is needed
                    # so the next duplicate provider/model finds the new row.
                    session.flush()

                session.commit()
                self._cleanup_old_records(session)
                return True
            except (SQLAlchemyError, TypeError, ValueError):
                session.rollback()
                logger.exception("Ошибка переноса временных результатов моделей в БД")
                return False

    def clear_all(self) -> int | None:
        """Delete all success records and report the deleted count.

        Returning None distinguishes a database failure from an empty table.
        The caller may run this synchronous operation via asyncio.to_thread.
        """
        if self.SessionLocal is None:
            return None
        with self.SessionLocal() as session:
            try:
                count = int(session.query(ModelSuccessLog).count())
                session.query(ModelSuccessLog).delete(synchronize_session=False)
                session.commit()
                return count
            except SQLAlchemyError:
                session.rollback()
                logger.exception("Ошибка очистки статистики моделей")
                return None

    def is_connected(self) -> bool:
        """Indicate whether a session factory is configured."""
        return self.SessionLocal is not None

    def has_data(self) -> bool:
        """Check whether any model observations have been persisted."""
        if self.SessionLocal is None:
            return False
        with self.SessionLocal() as session:
            try:
                return bool(session.query(ModelSuccessLog).count() > 0)
            except SQLAlchemyError:
                logger.exception("Не удалось проверить наличие статистики моделей")
                return False

    def get_all_models(self) -> list[tuple[str, str]]:
        """Return stored providers and models in descending success count order."""
        if self.SessionLocal is None:
            return []
        with self.SessionLocal() as session:
            try:
                rows = (
                    session.query(ModelSuccessLog.provider, ModelSuccessLog.model_name)
                    .order_by(ModelSuccessLog.success_count.desc())
                    .all()
                )
                return [(row.provider, row.model_name) for row in rows]
            except SQLAlchemyError:
                logger.exception("Не удалось прочитать сохранённые модели")
                return []
