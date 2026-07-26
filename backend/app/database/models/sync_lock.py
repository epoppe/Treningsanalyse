"""SyncLock — eksklusiv lås som hindrer samtidige synker."""

from sqlalchemy import Column, DateTime, String

from .base import Base


class SyncLock(Base):
    """Database-basert lås for synkronisering (fungerer på tvers av prosesser)."""

    __tablename__ = "sync_locks"

    lock_name = Column(String(100), primary_key=True)
    owner = Column(String(100), nullable=False, index=True)
    heartbeat = Column(DateTime(timezone=True), nullable=False)
    expires = Column(DateTime(timezone=True), nullable=False, index=True)
