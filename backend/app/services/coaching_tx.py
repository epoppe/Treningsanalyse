"""Transaction helpers — orchestrator owns commit; domain services flush."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session


def finalize_write(db: Session, *, commit: bool) -> None:
    if commit:
        db.commit()
    else:
        db.flush()


@contextmanager
def coaching_transaction(db: Session) -> Iterator[Session]:
    """Outer transaction for multi-write coaching flows. Rollback on error."""
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
