from sqlalchemy import Column, Integer, String, Date, DateTime, JSON
from sqlalchemy.sql import func

from .base import Base


class SyncState(Base):
    __tablename__ = "sync_state"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    last_synced_date = Column(Date, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


