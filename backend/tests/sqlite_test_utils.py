"""Shared SQLite helpers for deterministic, cross-platform unit tests."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool, StaticPool


def file_sqlite_url(db_path: Path) -> str:
    """Build a file-backed SQLite URL with forward slashes (Windows-safe)."""
    return f"sqlite:///{db_path.resolve().as_posix()}"


def make_memory_engine(url: str = "sqlite:///:memory:") -> Engine:
    """In-memory SQLite with a shared connection (StaticPool)."""
    return create_engine(
        url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def make_file_engine(url: str) -> Engine:
    """File-backed SQLite without pooled handles that outlive dispose() on Windows."""
    return create_engine(
        url,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )


def dispose_engine(engine: Engine | None) -> None:
    if engine is not None:
        engine.dispose()
