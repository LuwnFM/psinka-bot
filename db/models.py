"""SQLAlchemy models used by model stats and jail sentences."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class ModelSuccessLog(Base):
    __tablename__ = 'model_success_log'
    id = Column(Integer, primary_key=True)
    provider = Column(String(50), nullable=False)
    model_name = Column(String(100), nullable=False)
    success_count = Column(Integer, default=1)
    last_success_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    avg_latency_ms = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint('provider', 'model_name', name='_provider_model_uc'),)


