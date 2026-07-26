from sqlalchemy import Column, DateTime, Index, JSON, String, Text
from sqlalchemy.sql import func

from .base import Base


class SyncJob(Base):
    """Persistert status for bakgrunnssynkroniseringsjobber."""

    __tablename__ = "sync_jobs"
    __table_args__ = (
        Index("idx_sync_jobs_status_job_type", "status", "job_type"),
    )

    job_id = Column(String(36), primary_key=True, index=True)
    job_type = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True, default="queued")
    message = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    progress = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
