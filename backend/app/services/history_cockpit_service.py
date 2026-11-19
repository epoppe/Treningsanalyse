"""Historical cockpit payloads — YoY, performance/recovery rollups, annotations."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import RecommendationRecord, TrainingPlanVersion
from ..database.models.sleep import HRV, RestingHeartRate
from ..database.models.summaries import MonthlySummary
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .ppap_metrics_service import PpapMetricsService
from .temporal_metric_contract import percentile_rank


def _regime_split_dates(detector: Any, series: List[Tuple[date, float]], depth: int = 0) -> List[date]:
    if len(series) < 8 or depth >= 2:
        return []
    hit = detector._detect_change_point(series)
    if not hit.get("change_detected") or not hit.get("change_date"):
        return []
    split = date.fromisoformat(str(hit["change_date"]))
    left = [item for item in series if item[0] < split]
    right = [item for item in series if item[0] >= split]
    if len(left) < 4 or len(right) < 4:
        return [split]
    return (
        _regime_split_dates(detector, left, depth + 1)
        + [split]
        + _regime_split_dates(detector, right, depth + 1)
    )


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

        def relative(current: Optional[float], previous: Optional[float]) -> Dict[str, Any]:
            if previous in (None, 0):
                if (current or 0) > 0 and previous == 0:
                    return {"relative_delta": None, "comparison_basis": "from_zero"}
                return {"relative_delta": None, "comparison_basis": "missing_baseline"}
            return {
                "relative_delta": round(((current or 0) - previous) / previous * 100.0, 1),
                "comparison_basis": "ratio",
            }

        rows: List[Dict[str, Any]] = []
        for i in range(months):
            cur_start = add_months(start_month_start, i)
            cur_key = f"{cur_start.year}-{cur_start.month:02d}"
            prev_key = f"{cur_start.year - 1}-{cur_start.month:02d}"
            cur = by_month.get(cur_key)
            prev = by_month.get(prev_key)
            cur_p = payload(cur)
            prev_p = payload(prev)
            partial = (
                cur_start.year == end_date.year
                and cur_start.month == end_date.month
                and end_date.day < monthrange(end_date.year, end_date.month)[1]
            )
            if partial:
                cur_p = self._activity_totals(cur_start, end_date)
                prev_end = date(cur_start.year - 1, cur_start.month, end_date.day)
                prev_p = self._activity_totals(date(prev_end.year, prev_end.month, 1), prev_end)
            deltas = None
            comparison_basis = "full_month"
            if cur_p and prev_p:
                distance = relative(cur_p["distance_m"] or 0, prev_p["distance_m"] or 0)
                duration = relative(cur_p["duration_s"] or 0, prev_p["duration_s"] or 0)
                activities = relative(cur_p["activities"] or 0, prev_p["activities"] or 0)
                comparison_basis = "month_to_date" if partial else distance["comparison_basis"]
                if partial:
                    comparison_basis = "month_to_date"
                elif "from_zero" in {
                    distance["comparison_basis"],
                    duration["comparison_basis"],
                    activities["comparison_basis"],
                }:
                    comparison_basis = "from_zero"
                deltas = {
                    "distance_pct": distance["relative_delta"],
                    "duration_pct": duration["relative_delta"],
                    "activities_pct": activities["relative_delta"],
                    "distance": distance,
                    "duration": duration,
                    "activities": activities,
                }
            rows.append(
                {
                    "year": cur_start.year,
                    "month": cur_start.month,
                    "month_label": cur_key,
                    "partial": partial,
                    "comparison_basis": comparison_basis if cur_p and prev_p else (
                        "month_to_date" if partial else "full_month"
                    ),
                    "current": cur_p,
                    "previous_year": prev_p,
                    "deltas": deltas,
                }
            )
        return {
            "end_date": end_month.isoformat(),
            "months": months,
            "rows": rows,
            "disclaimer": (
                "Closed months compare full months. The open month compares the same "
                "day-of-month last year (month-to-date). A zero baseline is from_zero, not +100%."
            ),
        }

    def _activity_totals(self, start: date, end: date) -> Dict[str, Any]:
        activities = (
            self.db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .all()
        )
        distance = 0.0
        duration = 0.0
        count = 0
        tss = 0.0
        for activity in activities:
            if activity.start_time is None or activity.start_time.date() > end:
                continue
            count += 1
            distance += float(activity.distance or 0)
            duration += float(activity.duration or 0)
            tss += float(activity.training_stress_score or 0)
        return {
            "activities": count,
            "distance_m": round(distance, 1),
            "duration_s": round(duration, 1),
            "tss": round(tss, 1),
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
        first_month = add_months(end_month_start, -(months - 1))
        self._ppap.prime_load_series(first_month, end_date)
        rows: List[Dict[str, Any]] = []
        for i in range(months - 1, -1, -1):
            month_start = add_months(end_month_start, -i)
            last_day = monthrange(month_start.year, month_start.month)[1]
            calendar_end = date(month_start.year, month_start.month, last_day)
            effective_end = min(calendar_end, end_date)
            if effective_end < month_start:
                continue
            totals = self._activity_totals(month_start, effective_end)
            ctl_end = self._ppap.get_ctl(effective_end)
            ctl_samples = []
            cursor = month_start
            while cursor <= effective_end:
                value = self._ppap.get_ctl(cursor)
                if value is not None:
                    ctl_samples.append(float(value))
                cursor += timedelta(days=1)
            hrv_values = self._hrv_values(month_start, effective_end)
            rhr_values = self._rhr_values(month_start, effective_end)
            hrv_end = self._ppap.get_hrv_delta_pct(effective_end)
            span_days = (effective_end - month_start).days + 1
            rows.append(
                {
                    "month": f"{month_start.year}-{month_start.month:02d}",
                    "month_start": month_start.isoformat(),
                    "month_end": effective_end.isoformat(),
                    "calendar_month_end": calendar_end.isoformat(),
                    "partial": effective_end < calendar_end,
                    "effective_end": effective_end.isoformat(),
                    "volume_hours": round(totals["duration_s"] / 3600.0, 1) if totals["duration_s"] else None,
                    "activity_count": totals["activities"],
                    "tss": totals["tss"],
                    "ctl": round(float(ctl_end), 1) if ctl_end is not None else None,
                    "ctl_end": round(float(ctl_end), 1) if ctl_end is not None else None,
                    "ctl_mean": round(sum(ctl_samples) / len(ctl_samples), 1) if ctl_samples else None,
                    "ctl_end_semantics": "point_in_time",
                    "hrv_delta_pct": round(float(hrv_end), 1) if hrv_end is not None else None,
                    "hrv_median": round(sorted(hrv_values)[len(hrv_values) // 2], 1) if hrv_values else None,
                    "hrv_coverage": round(len(hrv_values) / span_days, 2) if span_days else None,
                    "rhr_median": round(sorted(rhr_values)[len(rhr_values) // 2], 1) if rhr_values else None,
                    "easy_minutes": self._easy_minutes(month_start, effective_end),
                    "quality_sessions": self._quality_sessions(month_start, effective_end),
                }
            )
        self._attach_seasonal_context(rows)
        return {
            "end_date": end_date.isoformat(),
            "months": rows,
            "disclaimer": (
                "ctl_end is the load state on effective_end (never a future month-end). "
                "ctl_mean is the mean of daily states inside the month. "
                "HRV/RHR medians are observations in the month. Not causal."
            ),
        }

    def _hrv_values(self, start: date, end: date) -> List[float]:
        rows = (
            self.db.query(HRV.rmssd)
            .filter(
                and_(
                    HRV.measurement_date >= start,
                    HRV.measurement_date <= end,
                    HRV.rmssd.isnot(None),
                )
            )
            .all()
        )
        return [float(row.rmssd) for row in rows if row.rmssd is not None]

    def _rhr_values(self, start: date, end: date) -> List[float]:
        rows = (
            self.db.query(RestingHeartRate.resting_heart_rate)
            .filter(
                and_(
                    RestingHeartRate.measurement_date >= start,
                    RestingHeartRate.measurement_date <= end,
                    RestingHeartRate.resting_heart_rate.isnot(None),
                )
            )
            .all()
        )
        return [float(row.resting_heart_rate) for row in rows if row.resting_heart_rate is not None]

    def _easy_minutes(self, start: date, end: date) -> Optional[float]:
        from .session_classifier_service import SessionClassifierService

        classifier = SessionClassifierService(self.db, self.storage)
        total = 0.0
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .all()
        )
        for activity in activities:
            if not is_running_activity(activity) or not activity.duration:
                continue
            kind = classifier.classify_activity(activity, end_date=end).get("session_type")
            if kind in {"recovery_run", "easy_aerobic"}:
                total += float(activity.duration) / 60.0
        return round(total, 1) if total > 0 else None

    def _quality_sessions(self, start: date, end: date) -> int:
        from .session_classifier_service import SessionClassifierService

        classifier = SessionClassifierService(self.db, self.storage)
        count = 0
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .all()
        )
        for activity in activities:
            if not is_running_activity(activity):
                continue
            kind = classifier.classify_activity(activity, end_date=end).get("session_type")
            if kind in {"threshold", "vo2_intervals", "tempo", "anaerobic", "race"}:
                count += 1
        return count

    def _attach_seasonal_context(self, rows: List[Dict[str, Any]]) -> None:
        """Descriptive same-month percentile. Omitted when coverage is thin."""
        if not rows:
            return
        latest = rows[-1]
        month_number = int(str(latest["month"]).split("-")[1])
        history = [
            float(row["hrv_median"])
            for row in rows[:-1]
            if row.get("hrv_median") is not None and int(str(row["month"]).split("-")[1]) == month_number
        ]
        current = latest.get("hrv_median")
        rank = percentile_rank(float(current), history) if current is not None else None
        if rank is None:
            latest["seasonal_context"] = None
            return
        latest["seasonal_context"] = {
            "metric": "hrv_median",
            "percentile_vs_same_month": rank,
            "same_month_samples": len(history),
            "note": "Descriptive personal same-month baseline. Not a prediction.",
        }

    def monthly_history(self, *, start: date, end: date, period: str) -> Dict[str, Any]:
        """Adaptive history. `period=all` is not silently truncated to 36 months."""
        months = (
            self.db.query(MonthlySummary)
            .filter(
                MonthlySummary.month_start_date >= start,
                MonthlySummary.month_end_date <= end + timedelta(days=31),
            )
            .order_by(MonthlySummary.month_start_date.asc())
            .all()
        )
        payloads: List[Dict[str, Any]] = []
        for summary in months:
            if summary.month_start_date is None:
                continue
            if summary.month_start_date > end:
                continue
            payloads.append(
                {
                    "month_start": summary.month_start_date.isoformat(),
                    "month_end": summary.month_end_date.isoformat() if summary.month_end_date else None,
                    "year": summary.year,
                    "month": summary.month,
                    "total_duration_seconds": summary.total_duration,
                    "total_distance_meters": summary.total_distance,
                    "activity_count": summary.total_activities,
                    "total_tss": summary.total_tss,
                }
            )
        span_months = max(1, (end.year - start.year) * 12 + (end.month - start.month) + 1)
        if span_months <= 36:
            granularity = "monthly"
            buckets = payloads
        elif span_months <= 120:
            granularity = "quarterly"
            buckets = _aggregate_quarters(payloads)
        else:
            granularity = "annual"
            buckets = _aggregate_years(payloads)
        years: Dict[str, List[Dict[str, Any]]] = {}
        for item in payloads:
            years.setdefault(str(item["year"]), []).append(item)
        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "period": period,
            "granularity": granularity,
            "capped": False,
            "available_month_count": len(payloads),
            "month_count": len(payloads),
            "regimes": self._load_regimes(payloads),
            "buckets": buckets,
            "years": [
                {"year": year, "months": items}
                for year, items in sorted(years.items(), key=lambda item: item[0], reverse=True)
            ],
            "note": (
                "Full available MonthlySummary history. "
                "0–36 months stay monthly; 3–10 years are also rolled to quarters; "
                "10+ years add an annual overview. Months are not dropped."
            ),
        }

    def _load_regimes(self, monthly_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Median-shift blocks on monthly TSS.

        A durable block lasted at least three months. The shift is a load-level
        change, not a performance improvement.
        """
        from .trend_analysis_service import TrendAnalysisService

        series: List[Tuple[date, float]] = []
        for row in monthly_rows:
            start_raw = row.get("month_start")
            if not start_raw:
                continue
            series.append((date.fromisoformat(str(start_raw)[:10]), float(row.get("total_tss") or 0.0)))
        series.sort(key=lambda item: item[0])
        if not series:
            return []
        detector = TrendAnalysisService(self.db, self.storage)
        splits = sorted(set(_regime_split_dates(detector, series)))
        indices = [0]
        for split in splits:
            index = next((i for i, (day, _value) in enumerate(series) if day >= split), None)
            if index is not None and 0 < index < len(series):
                indices.append(index)
        indices.append(len(series))
        indices = sorted(set(indices))
        regimes: List[Dict[str, Any]] = []
        previous_level: Optional[float] = None
        for left, right in zip(indices, indices[1:]):
            segment = series[left:right]
            if not segment:
                continue
            level = float(median(value for _day, value in segment))
            shift = None if previous_level is None else round(level - previous_level, 1)
            if shift is None:
                kind = "baseline"
            elif shift > 0:
                kind = "level_shift_up"
            else:
                kind = "level_shift_down"
            regimes.append(
                {
                    "start": segment[0][0].isoformat(),
                    "end": segment[-1][0].isoformat(),
                    "metric": "total_tss",
                    "level": round(level, 1),
                    "months": len(segment),
                    "shift_from_previous": shift,
                    "kind": kind,
                    "durable": len(segment) >= 3,
                    "interpretation": "load_regime",
                }
            )
            previous_level = level
        return regimes

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


def _sum_field(items: List[Dict[str, Any]], field: str) -> float:
    return float(sum(float(item.get(field) or 0) for item in items))


def _aggregate_quarters(months: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in months:
        month = int(item.get("month") or 1)
        quarter = (month - 1) // 3 + 1
        key = f"{item.get('year')}-Q{quarter}"
        groups.setdefault(key, []).append(item)
    buckets = []
    for key, items in groups.items():
        buckets.append(
            {
                "bucket": key,
                "granularity": "quarterly",
                "month_count": len(items),
                "total_duration_seconds": _sum_field(items, "total_duration_seconds"),
                "total_distance_meters": _sum_field(items, "total_distance_meters"),
                "activity_count": int(_sum_field(items, "activity_count")),
                "total_tss": _sum_field(items, "total_tss"),
            }
        )
    return buckets


def _aggregate_years(months: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in months:
        groups.setdefault(str(item.get("year")), []).append(item)
    return [
        {
            "bucket": year,
            "granularity": "annual",
            "month_count": len(items),
            "total_duration_seconds": _sum_field(items, "total_duration_seconds"),
            "total_distance_meters": _sum_field(items, "total_distance_meters"),
            "activity_count": int(_sum_field(items, "activity_count")),
            "total_tss": _sum_field(items, "total_tss"),
        }
        for year, items in groups.items()
    ]
