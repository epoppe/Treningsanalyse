"""Historical cockpit payloads — YoY, performance/recovery rollups, annotations."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import RecommendationRecord, TrainingPlanVersion
from ..database.models.summaries import MonthlySummary
from ..storage import DataStorage
from .ppap_metrics_service import PpapMetricsService


class HistoryCockpitService:
    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage
        self._ppap = PpapMetricsService(db, storage)

    def yoy_months(self, *, end_date: Optional[date] = None, months: int = 12) -> Dict[str, Any]:
        end_date = end_date or date.today()
        last_day = monthrange(end_date.year, end_date.month)[1]
        end_month = date(end_date.year, end_date.month, last_day)

        def first_day(y: int, m: int) -> date:
            return date(y, m, 1)

        def add_months(d: date, delta: int) -> date:
            y = d.year + (d.month - 1 + delta) // 12
            m = (d.month - 1 + delta) % 12 + 1
            return first_day(y, m)

        end_month_start = first_day(end_month.year, end_month.month)
        start_month_start = add_months(end_month_start, -(months - 1))
        prev_year_start = add_months(start_month_start, -12)

        summaries = (
            self.db.query(MonthlySummary)
            .filter(
                MonthlySummary.month_start_date >= prev_year_start,
                MonthlySummary.month_end_date <= end_month,
            )
            .order_by(MonthlySummary.month_start_date.asc())
            .all()
        )
        by_month = {
            f"{s.month_start_date.year}-{s.month_start_date.month:02d}": s
            for s in summaries
            if s.month_start_date
        }

        def payload(summary: Optional[MonthlySummary]) -> Optional[Dict[str, Any]]:
            if summary is None:
                return None
            return {
                "activities": summary.total_activities,
                "distance_m": summary.total_distance,
                "duration_s": summary.total_duration,
                "tss": summary.total_tss,
            }

        def pct(current: float, previous: float) -> Optional[float]:
            if previous in (None, 0):
                return 100.0 if (current or 0) > 0 else 0.0
            return round(((current or 0) - previous) / previous * 100.0, 1)

        rows: List[Dict[str, Any]] = []
        for i in range(months):
            cur_start = add_months(start_month_start, i)
            cur_key = f"{cur_start.year}-{cur_start.month:02d}"
            prev_key = f"{cur_start.year - 1}-{cur_start.month:02d}"
            cur = by_month.get(cur_key)
            prev = by_month.get(prev_key)
            cur_p = payload(cur)
            prev_p = payload(prev)
            deltas = None
            if cur_p and prev_p:
                deltas = {
                    "distance_pct": pct(cur_p["distance_m"] or 0, prev_p["distance_m"] or 0),
                    "duration_pct": pct(cur_p["duration_s"] or 0, prev_p["duration_s"] or 0),
                    "activities_pct": pct(cur_p["activities"] or 0, prev_p["activities"] or 0),
                }
            rows.append(
                {
                    "year": cur_start.year,
                    "month": cur_start.month,
                    "month_label": cur_key,
                    "current": cur_p,
                    "previous_year": prev_p,
                    "deltas": deltas,
                }
            )
        return {
            "end_date": end_month.isoformat(),
            "months": months,
            "rows": rows,
            "disclaimer": "Year-over-year uses MonthlySummary — observational volume comparison.",
        }

    def performance_recovery_history(
        self,
        *,
        end_date: Optional[date] = None,
        months: int = 12,
    ) -> Dict[str, Any]:
        end_date = end_date or date.today()

        def add_months(d: date, delta: int) -> date:
            y = d.year + (d.month - 1 + delta) // 12
            m = (d.month - 1 + delta) % 12 + 1
            return date(y, m, 1)

        end_month_start = date(end_date.year, end_date.month, 1)
        rows: List[Dict[str, Any]] = []
        for i in range(months - 1, -1, -1):
            month_start = add_months(end_month_start, -i)
            last_day = monthrange(month_start.year, month_start.month)[1]
            month_end = date(month_start.year, month_start.month, last_day)
            summary = (
                self.db.query(MonthlySummary)
                .filter(
                    MonthlySummary.year == month_start.year,
                    MonthlySummary.month == month_start.month,
                )
                .first()
            )
            ctl = self._ppap.get_ctl(month_end)
            hrv = self._ppap.get_hrv_delta_pct(month_end)
            rows.append(
                {
                    "month": f"{month_start.year}-{month_start.month:02d}",
                    "month_start": month_start.isoformat(),
                    "month_end": month_end.isoformat(),
                    "volume_hours": round((summary.total_duration or 0) / 3600.0, 1)
                    if summary and summary.total_duration
                    else None,
                    "activity_count": summary.total_activities if summary else None,
                    "ctl": round(float(ctl), 1) if ctl is not None else None,
                    "hrv_delta_pct": round(float(hrv), 1) if hrv is not None else None,
                }
            )
        return {
            "end_date": end_date.isoformat(),
            "months": rows,
            "disclaimer": "Monthly snapshots — performance/recovery are point-in-time, not causal.",
        }

    def annotations(self, *, end_date: Optional[date] = None, limit: int = 24) -> Dict[str, Any]:
        end_date = end_date or date.today()
        start = end_date - timedelta(days=365)
        events: List[Dict[str, Any]] = []

        plan_versions = (
            self.db.query(TrainingPlanVersion)
            .filter(TrainingPlanVersion.created_at.isnot(None))
            .order_by(TrainingPlanVersion.created_at.desc())
            .limit(20)
            .all()
        )
        for version in plan_versions:
            created = version.created_at.date() if version.created_at else None
            if created and created < start:
                continue
            reasons = version.reason_json or []
            if not reasons and not version.changes_json:
                continue
            events.append(
                {
                    "date": version.created_at.isoformat() if version.created_at else None,
                    "type": "plan_adjustment",
                    "title": "Planjustering",
                    "detail": "; ".join(str(r) for r in reasons[:3]) or "Plan oppdatert",
                }
            )

        recommendations = (
            self.db.query(RecommendationRecord)
            .filter(
                RecommendationRecord.is_shadow.is_(False),
                RecommendationRecord.as_of_date >= start,
            )
            .order_by(RecommendationRecord.generated_at.desc())
            .limit(30)
            .all()
        )
        for rec in recommendations:
            if rec.superseded_by_id is None:
                continue
            events.append(
                {
                    "date": rec.generated_at.isoformat() if rec.generated_at else rec.as_of_date.isoformat(),
                    "type": "recommendation_change",
                    "title": "Ny anbefaling",
                    "detail": rec.recommended_workout_type or "Anbefaling endret",
                }
            )

        events.sort(key=lambda e: e.get("date") or "", reverse=True)
        return {
            "end_date": end_date.isoformat(),
            "items": events[:limit],
            "disclaimer": "Annotations are observational milestones — not judgments.",
        }
