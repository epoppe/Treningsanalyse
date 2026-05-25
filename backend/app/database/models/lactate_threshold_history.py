from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String

from .base import Base


class LactateThresholdHistory(Base):
    __tablename__ = "lactate_threshold_history"

    __table_args__ = (
        Index("idx_lactate_threshold_history_observed_at", "observed_at"),
        Index("idx_lactate_threshold_history_source_observed_at", "source", "observed_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    observed_at = Column(DateTime, nullable=False, index=True)
    source = Column(String(50), nullable=False)
    sync_context = Column(String(50), nullable=True)
    lactate_threshold_speed = Column(Float, nullable=True)  # m/s
    lactate_threshold_heart_rate = Column(Float, nullable=True)  # bpm
    raw_lactate_threshold_speed = Column(Float, nullable=True)  # ufiltrert Garmin-verdi
    is_fallback = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
