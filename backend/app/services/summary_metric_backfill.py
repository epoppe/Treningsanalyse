"""Backfill av sammendragsfelter (best_* og årlige trender) fra lokale aktiviteter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional, Tuple

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..database.models.summaries import DailySummary, MonthlySummary, WeeklySummary, YearlySummary
from .summary_service import SummaryService


@dataclass
class SummaryBackfillSummary:
    daily_count: int = 0
    weekly_count: int = 0
    monthly_count: int = 0
    yearly_count: int = 0
    field_counts: Dict[str, int] = field(default_factory=dict)


def _count_filled(model: type, column: str, db: Session) -> Dict[str, int]:
    col = getattr(model, column)
    total = db.query(model).count()
    filled = db.query(model).filter(col.isnot(None)).count()
    return {"total": total, "filled": filled}


def audit_summary_best_fields(db: Session) -> Dict[str, Dict[str, int]]:
    """Tell fylte best_*-kolonner i sammendragstabeller."""
    audits: Dict[str, Dict[str, int]] = {}
    for prefix, model in (
        ("daily_summary", DailySummary),
        ("weekly_summary", WeeklySummary),
        ("monthly_summary", MonthlySummary),
        ("yearly_summary", YearlySummary),
    ):
        for column in ("best_pace", "best_distance", "best_duration", "best_speed"):
            audits[f"{prefix}.{column}"] = _count_filled(model, column, db)
    for column in ("activities_trend", "distance_trend", "duration_trend"):
        audits[f"yearly_summary.{column}"] = _count_filled(YearlySummary, column, db)
    return audits


def run_summary_metric_backfill(
    db: Session,
    *,
    daily: bool = True,
    weekly: bool = True,
    monthly: bool = True,
    yearly: bool = True,
    dry_run: bool = False,
) -> SummaryBackfillSummary:
    """
    Regenerer sammendrag fra aktiviteter slik at best_* og yearly-trender fylles.
    """
    service = SummaryService()
    service.db = db
    summary = SummaryBackfillSummary()

    before = audit_summary_best_fields(db)

    if daily:
        dates = db.query(func.date(Activity.start_time)).distinct().all()
        for (date_value,) in dates:
            if not date_value:
                continue
            if isinstance(date_value, str):
                target_date = date.fromisoformat(date_value)
            else:
                target_date = date_value
            if service.calculate_daily_summary(target_date, commit=False):
                summary.daily_count += 1

    if weekly:
        bounds = db.query(
            func.min(func.date(Activity.start_time)),
            func.max(func.date(Activity.start_time)),
        ).one()
        if bounds[0] and bounds[1]:
            start_bound = bounds[0] if isinstance(bounds[0], date) else date.fromisoformat(str(bounds[0]))
            end_bound = bounds[1] if isinstance(bounds[1], date) else date.fromisoformat(str(bounds[1]))
            year_weeks: list[Tuple[int, int]] = service._period_weeks(start_bound, end_bound)
            for year, week in year_weeks:
                try:
                    if service.calculate_weekly_summary(year, week, commit=False):
                        summary.weekly_count += 1
                except ValueError:
                    continue

    if monthly:
        year_months = (
            db.query(
                extract("year", Activity.start_time).label("year"),
                extract("month", Activity.start_time).label("month"),
            )
            .distinct()
            .all()
        )
        for year, month in year_months:
            if year and month:
                if service.calculate_monthly_summary(int(year), int(month), commit=False):
                    summary.monthly_count += 1

    if yearly:
        years = sorted(
            int(year)
            for (year,) in db.query(extract("year", Activity.start_time).label("year")).distinct().all()
            if year
        )
        for year in years:
            if service.calculate_yearly_summary(year, commit=False):
                summary.yearly_count += 1

    if dry_run:
        db.rollback()
    else:
        db.commit()

    after = audit_summary_best_fields(db)
    for key, stats in after.items():
        delta = stats["filled"] - before.get(key, {}).get("filled", 0)
        if delta > 0:
            summary.field_counts[key] = delta

    return summary
