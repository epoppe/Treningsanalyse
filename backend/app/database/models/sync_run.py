"""SyncRun — historikk og statistikk for synkroniseringskjøringer."""

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base


class SyncRun(Base):
    """Sporbar kjøring av en synk-jobb (audit/metrics, parallelt med SyncJob)."""

    __tablename__ = "sync_runs"
    __table_args__ = (
        Index("idx_sync_runs_status_job_type", "status", "job_type"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(String(36), nullable=True, index=True)  # kobling til SyncJob.job_id
    job_type = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True, default="queued")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    inserted = Column(Integer, nullable=False, default=0)
    updated = Column(Integer, nullable=False, default=0)
    skipped = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    # Restartbar synk: siste sikre posisjon (f.eks. last_activity_id / last_start_time)
    checkpoint = Column(JSON, nullable=True)
    code_version = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
