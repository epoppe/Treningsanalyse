"""Sporbarhet for beregnede metrikker."""

from sqlalchemy import Column, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base


class MetricProvenance(Base):
    """Proveniens for én beregnet metrikk på én entitet (typisk aktivitet)."""

    __tablename__ = "metric_provenance"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "metric_key",
            name="uq_metric_provenance_entity_metric",
        ),
        Index("idx_metric_provenance_entity", "entity_type", "entity_id"),
        Index("idx_metric_provenance_metric_key", "metric_key"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    entity_type = Column(String(50), nullable=False, default="activity")
    entity_id = Column(String(255), nullable=False)
    metric_key = Column(String(100), nullable=False)
    algorithm_version = Column(String(64), nullable=False)
    calculated_at = Column(DateTime(timezone=True), nullable=False)
    source_hash = Column(String(64), nullable=True)
    source_updated_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String(32), nullable=False, default="ok")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
