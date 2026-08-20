"""Shared MCP helpers — context, parsing, activity resolution."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterator, Optional

from sqlalchemy.orm import Session, selectinload

from ...config import settings
from ...database.models.activity import Activity
from ...database.session import SessionLocal
from ...storage import DataStorage
from ...utils.activity_filters import is_running_activity


@contextmanager
def training_context() -> Iterator[tuple[Session, DataStorage]]:
    db = SessionLocal()
    storage = DataStorage(settings.DATA_DIR)
    try:
        yield db, storage
    finally:
        db.close()


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def readable_date(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%A, %Y-%m-%d %H:%M")


def resolve_activity(
    db: Session,
    activity_id: Optional[str],
    *,
    running_only: bool = False,
) -> Optional[Activity]:
    query = db.query(Activity).options(selectinload(Activity.activity_type))
    if activity_id:
        activity = query.filter_by(activity_id=str(activity_id)).first()
        if activity is None:
            return None
        return activity if not running_only or is_running_activity(activity) else None

    activities = query.order_by(Activity.start_time.desc()).limit(200).all()
    if running_only:
        return next((activity for activity in activities if is_running_activity(activity)), None)
    return activities[0] if activities else None
