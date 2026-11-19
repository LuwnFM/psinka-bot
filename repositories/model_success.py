"""Repository for AI model success metrics backed by SQLAlchemy sessions."""

import csv
import io
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from db.models import ModelSuccessLog

class DBManager:
    def __init__(self, session_factory):
        self.SessionLocal = session_factory

    def log_success(self, provider: str, model: str, latency_ms: int):
        if not self.SessionLocal:
            return
        session = self.SessionLocal()
        try:
            record = session.query(ModelSuccessLog).filter_by(provider=provider, model_name=model).first()
            if record:
                record.success_count += 1
                record.avg_latency_ms = int(
                    (record.avg_latency_ms * (record.success_count - 1) + latency_ms) / record.success_count)
                record.last_success_at = datetime.now(timezone.utc)
            else:
                record = ModelSuccessLog(provider=provider, model_name=model, success_count=1,
                                         last_success_at=datetime.now(timezone.utc), avg_latency_ms=latency_ms)
                session.add(record)
            session.commit()
            self._cleanup_old_records(session)
        except Exception as e:
            session.rollback()
            logging.error(f"Ошибка записи в БД: {e}")
        finally:
            session.close()

    def _cleanup_old_records(self, session):
        try:
            count = session.query(ModelSuccessLog).count()
            if count > 200:
                old_ids = session.query(ModelSuccessLog.id).order_by(ModelSuccessLog.last_success_at.asc()).limit(
                    count - 200).all()
                if old_ids:
                    session.query(ModelSuccessLog).filter(ModelSuccessLog.id.in_([x[0] for x in old_ids])).delete(
                        synchronize_session=False)
                    session.commit()
        except:
            pass

    def get_top_models(self, limit: int = 10) -> List[Tuple[str, str, int]]:
        if not self.SessionLocal: return []
        session = self.SessionLocal()
        try:
            results = session.query(ModelSuccessLog.provider, ModelSuccessLog.model_name,
                                    ModelSuccessLog.avg_latency_ms) \
                .order_by(ModelSuccessLog.success_count.desc(), ModelSuccessLog.avg_latency_ms.asc()) \
                .limit(limit).all()
            return [(r.provider, r.model_name, r.avg_latency_ms) for r in results]
        except:
            return []
        finally:
            session.close()

    def export_to_csv(self) -> Optional[str]:
        if not self.SessionLocal: return None
        session = self.SessionLocal()
        try:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'Provider', 'Model', 'Success Count', 'Avg Latency (ms)', 'Last Success'])
            records = session.query(ModelSuccessLog).order_by(ModelSuccessLog.success_count.desc()).all()
            for r in records:
                writer.writerow([r.id, r.provider, r.model_name, r.success_count, r.avg_latency_ms, r.last_success_at])
            return output.getvalue()
        except Exception as e:
            logging.error(f"Ошибка экспорта CSV: {e}")
            return None
        finally:
            session.close()

    def is_connected(self) -> bool:
        return self.SessionLocal is not None

    def has_data(self) -> bool:
        if not self.SessionLocal: return False
        session = self.SessionLocal()
        try:
            return session.query(ModelSuccessLog).count() > 0
        except:
            return False
        finally:
            session.close()

    def get_all_models(self) -> List[Tuple[str, str]]:
        if not self.SessionLocal: return []
        session = self.SessionLocal()
        try:
            results = session.query(ModelSuccessLog.provider, ModelSuccessLog.model_name) \
                .order_by(ModelSuccessLog.success_count.desc()).all()
            return [(r.provider, r.model_name) for r in results]
        except:
            return []
        finally:
            session.close()


