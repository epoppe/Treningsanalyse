"""SQLAlchemy engine and session factory.

SQLite-specific PRAGMA / pool settings are isolated here so business logic
never needs to know the dialect.
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, event, pool
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from ..config import settings

logger = logging.getLogger(__name__)

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL


def configure_sqlite(dbapi_conn, connection_record) -> None:
    """Apply desktop-friendly SQLite PRAGMAs on each new connection."""
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA optimize")
    finally:
        cursor.close()
    logger.debug("SQLite PRAGMA settings applied")


def create_db_engine(database_url: str | None = None) -> Engine:
    """Create an engine for the given URL (defaults to settings.DATABASE_URL)."""
    url = database_url or settings.DATABASE_URL
    if url.startswith("sqlite"):
        # NullPool: one connection per checkout. StaticPool shares a single connection
        # across FastAPI's sync threadpool and causes sqlite3.InterfaceError under
        # concurrent /api/analysis requests.
        eng = create_engine(
            url,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
            poolclass=pool.NullPool,
            echo=False,
        )
        event.listen(eng, "connect", configure_sqlite)
        return eng

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


engine = create_db_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
