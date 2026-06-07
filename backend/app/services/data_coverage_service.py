"""
Kartlegging av datadekning for aktiviteter, helsedata og avledede metrikker.

Brukes til backfill-vurdering uten å starte synkronisering mot Garmin.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database.models.activity import Activity, ActivityType, GarminPerformanceMetric
from ..utils.activity_filters import is_running_activity, running_type_keys_for_query
from ..database.models.body_battery import BodyBattery
from ..database.models.health_data_missing import HealthDataMissing
from ..database.models.sleep import HRV, RestingHeartRate, Sleep
from ..database.models.stress import Stress
from ..database.models.sync_state import SyncState
from ..storage import DataStorage
from .analysis_service import enrich_fit_speed_from_distance


class GapCause(str, Enum):
    """Hvorfor data mangler eller er tynn."""

    API_LIMITED = "api_limited"
    DEVICE_LIMITED = "device_limited"
    SYNC_GAP = "sync_gap"
    BACKFILL_CANDIDATE = "backfill_candidate"
    UNKNOWN = "unknown"


class BackfillRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DerivedBackfillSkipReason(str, Enum):
    """Hvorfor avledede løpemetrikker ikke kan beregnes."""

    NOT_RUNNING_SPORT = "not_running_sport"
    THIN_FIT_SAMPLES = "thin_fit_samples"
    THIN_SUMMARY_FIELDS = "thin_summary_fields"
    MISSING_FIT_COLUMNS = "missing_fit_columns"
    NO_FIT_DATA = "no_fit_data"
    ELIGIBLE = "eligible"


@dataclass(frozen=True)
class DatasetCoverage:
    key: str
    label: str
    row_count: int
    first_date: Optional[date]
    last_date: Optional[date]
    expected_days: Optional[int] = None
    filled_days: Optional[int] = None
    missing_marked: int = 0
    sync_state_date: Optional[date] = None
    notes: str = ""


@dataclass
class DerivedBackfillDiagnostic:
    activity_id: str
    type_key: Optional[str]
    skip_reason: DerivedBackfillSkipReason
    detail: str = ""
    fit_rows: int = 0
    speed_samples: int = 0
    heart_rate_coverage_pct: Optional[float] = None


@dataclass
class BackfillRecommendation:
    priority: int
    key: str
    title: str
    cause: GapCause
    risk: BackfillRisk
    value_for_mcp: str
    action: str
    estimated_scope: str
    notes: str = ""


# Kjente historiske begrensninger (Garmin/enhet/API), brukt til klassifisering.
KNOWN_API_FLOORS: Dict[str, date] = {
    "hrv": date(2023, 1, 1),
    "body_battery": date(2020, 1, 1),
    "stress": date(2020, 1, 1),
    "sleep": date(2018, 1, 1),
    "resting_heart_rate": date(2018, 1, 1),
}

ACTIVITY_FIELD_GROUPS: Dict[str, List[str]] = {
    "training_load": ["epoc", "training_stress_score", "total_training_effect"],
    "running_dynamics": [
        "ground_contact_time",
        "stride_length",
        "vertical_oscillation",
        "vertical_ratio",
    ],
    "recovery_per_activity": ["body_battery_start", "activity_body_battery_delta"],
    "power": ["average_power", "normalized_power"],
    "derived_local": ["negative_split_percent", "decoupling_percent", "running_economy"],
    "weather": ["weather_condition", "temperature"],
}

@dataclass
class DataCoverageReport:
    generated_at: datetime
    activity_count: int
    activity_first: Optional[date]
    activity_last: Optional[date]
    datasets: List[DatasetCoverage] = field(default_factory=list)
    activity_fields: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    fit: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[BackfillRecommendation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "activities": {
                "count": self.activity_count,
                "first_date": self.activity_first.isoformat() if self.activity_first else None,
                "last_date": self.activity_last.isoformat() if self.activity_last else None,
            },
            "datasets": [
                {
                    "key": d.key,
                    "label": d.label,
                    "row_count": d.row_count,
                    "first_date": d.first_date.isoformat() if d.first_date else None,
                    "last_date": d.last_date.isoformat() if d.last_date else None,
                    "expected_days": d.expected_days,
                    "filled_days": d.filled_days,
                    "missing_marked": d.missing_marked,
                    "sync_state_date": d.sync_state_date.isoformat() if d.sync_state_date else None,
                    "notes": d.notes,
                }
                for d in self.datasets
            ],
            "activity_fields": self.activity_fields,
            "fit": self.fit,
            "recommendations": [
                {
                    "priority": r.priority,
                    "key": r.key,
                    "title": r.title,
                    "cause": r.cause.value,
                    "risk": r.risk.value,
                    "value_for_mcp": r.value_for_mcp,
                    "action": r.action,
                    "estimated_scope": r.estimated_scope,
                    "notes": r.notes,
                }
                for r in self.recommendations
            ],
        }


class DataCoverageService:
    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage

    def build_report(self, as_of: Optional[date] = None) -> DataCoverageReport:
        as_of = as_of or date.today()
        activity_bounds = self._activity_bounds()
        sync_states = self._sync_state_map()

        report = DataCoverageReport(
            generated_at=datetime.now(),
            activity_count=activity_bounds[2],
            activity_first=activity_bounds[0],
            activity_last=activity_bounds[1],
        )
        report.datasets = self._health_datasets(as_of, sync_states)
        report.activity_fields = self._activity_field_coverage(activity_bounds[2])
        report.fit = self._fit_coverage()
        report.recommendations = self._build_recommendations(report, as_of)
        return report

    def _activity_bounds(self) -> Tuple[Optional[date], Optional[date], int]:
        row = self.db.query(
            func.min(Activity.start_time),
            func.max(Activity.start_time),
            func.count(Activity.activity_id),
        ).one()
        first = row[0].date() if row[0] else None
        last = row[1].date() if row[1] else None
        return first, last, int(row[2] or 0)

    def _sync_state_map(self) -> Dict[str, Optional[date]]:
        rows = self.db.query(SyncState.key, SyncState.last_synced_date).all()
        return {key: synced for key, synced in rows}

    def _count_missing_marked(self, data_type: str) -> int:
        return (
            self.db.query(func.count(HealthDataMissing.id))
            .filter(HealthDataMissing.data_type == data_type)
            .scalar()
            or 0
        )

    def _date_range_stats(
        self,
        date_values: Sequence[date],
        as_of: date,
        api_floor: Optional[date],
    ) -> Tuple[Optional[date], Optional[date], Optional[int], Optional[int]]:
        if not date_values:
            return None, None, None, None
        first = min(date_values)
        last = max(date_values)
        range_start = max(first, api_floor) if api_floor else first
        range_end = min(last, as_of)
        if range_start > range_end:
            return first, last, 0, len(set(date_values))
        expected = (range_end - range_start).days + 1
        filled = len({d for d in date_values if range_start <= d <= range_end})
        return first, last, expected, filled

    def _health_datasets(self, as_of: date, sync_states: Dict[str, Optional[date]]) -> List[DatasetCoverage]:
        datasets: List[DatasetCoverage] = []

        hrv_dates = [row[0] for row in self.db.query(HRV.measurement_date).all()]
        first, last, expected, filled = self._date_range_stats(hrv_dates, as_of, KNOWN_API_FLOORS["hrv"])
        datasets.append(
            DatasetCoverage(
                key="hrv",
                label="HRV",
                row_count=len(hrv_dates),
                first_date=first,
                last_date=last,
                expected_days=expected,
                filled_days=filled,
                missing_marked=self._count_missing_marked("hrv"),
                sync_state_date=sync_states.get("hrv"),
                notes="Garmin HRV via API fra ca. 2023.",
            )
        )

        sleep_dates = [row[0] for row in self.db.query(Sleep.sleep_date).all()]
        first, last, expected, filled = self._date_range_stats(sleep_dates, as_of, None)
        datasets.append(
            DatasetCoverage(
                key="sleep",
                label="Søvn",
                row_count=len(sleep_dates),
                first_date=first,
                last_date=last,
                expected_days=expected,
                filled_days=filled,
                missing_marked=self._count_missing_marked("sleep"),
                sync_state_date=sync_states.get("sleep"),
                notes="Historikk avhenger av kompatibel klokke og faktisk søvnregistrering.",
            )
        )

        bb_dates = [row[0] for row in self.db.query(BodyBattery.date).all()]
        first, last, expected, filled = self._date_range_stats(bb_dates, as_of, None)
        datasets.append(
            DatasetCoverage(
                key="body_battery",
                label="Body Battery",
                row_count=len(bb_dates),
                first_date=first,
                last_date=last,
                expected_days=expected,
                filled_days=filled,
                sync_state_date=sync_states.get("body_battery"),
                notes="Daglig Body Battery krever støttet enhet.",
            )
        )

        stress_dates = [row[0] for row in self.db.query(Stress.stress_date).all()]
        first, last, expected, filled = self._date_range_stats(stress_dates, as_of, KNOWN_API_FLOORS["stress"])
        datasets.append(
            DatasetCoverage(
                key="stress",
                label="Stress",
                row_count=len(stress_dates),
                first_date=first,
                last_date=last,
                expected_days=expected,
                filled_days=filled,
                missing_marked=self._count_missing_marked("stress"),
                sync_state_date=sync_states.get("stress"),
                notes="Stress-synk prøver fra 2020, men historikk varierer per enhet.",
            )
        )

        rhr_dates = [row[0] for row in self.db.query(RestingHeartRate.measurement_date).all()]
        first, last, expected, filled = self._date_range_stats(rhr_dates, as_of, None)
        datasets.append(
            DatasetCoverage(
                key="resting_heart_rate",
                label="Hvilepuls",
                row_count=len(rhr_dates),
                first_date=first,
                last_date=last,
                expected_days=expected,
                filled_days=filled,
                missing_marked=self._count_missing_marked("resting_heart_rate"),
                sync_state_date=sync_states.get("resting_heart_rate"),
                notes="Automatisk hvilepuls er ofte tynn historisk.",
            )
        )

        gpm = self.db.query(
            func.count(GarminPerformanceMetric.date),
            func.min(GarminPerformanceMetric.date),
            func.max(GarminPerformanceMetric.date),
        ).one()
        gpm_first = gpm[1].date() if gpm[1] else None
        gpm_last = gpm[2].date() if gpm[2] else None
        datasets.append(
            DatasetCoverage(
                key="garmin_performance_metrics",
                label="Garmin performance (daglig)",
                row_count=int(gpm[0] or 0),
                first_date=gpm_first,
                last_date=gpm_last,
                sync_state_date=sync_states.get("garmin_performance_metrics"),
                notes="Daglige Garmin metrics (VO2, load balance, training status).",
            )
        )

        return datasets

    def _activity_field_coverage(self, total: int) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        if total == 0:
            return result

        for group, columns in ACTIVITY_FIELD_GROUPS.items():
            group_stats: Dict[str, Any] = {"fields": {}, "any_filled": 0}
            for column in columns:
                row = self.db.query(
                    func.count(getattr(Activity, column)),
                    func.min(Activity.start_time),
                ).filter(getattr(Activity, column).isnot(None)).one()
                count = int(row[0] or 0)
                first = row[1].date() if row[1] else None
                group_stats["fields"][column] = {
                    "count": count,
                    "pct": round(100.0 * count / total, 1),
                    "first_date": first.isoformat() if first else None,
                }
            group_stats["any_filled"] = max(
                (group_stats["fields"][c]["count"] for c in columns),
                default=0,
            )
            result[group] = group_stats
        return result

    def _fit_coverage(self) -> Dict[str, Any]:
        total = self.db.query(func.count(Activity.activity_id)).scalar() or 0
        fit_ids = self._fit_activity_ids()
        with_fit = 0
        if fit_ids:
            with_fit = (
                self.db.query(func.count(Activity.activity_id))
                .filter(Activity.activity_id.in_(list(fit_ids)))
                .scalar()
                or 0
            )

        with_db_records = (
            self.db.query(func.count(Activity.activity_id))
            .filter(Activity.detailed_metrics.isnot(None))
            .filter(Activity.detailed_metrics.like("%records%"))
            .scalar()
            or 0
        )

        missing_derived = 0
        missing_derived_running = 0
        if fit_ids:
            missing_derived = (
                self.db.query(func.count(Activity.activity_id))
                .filter(Activity.activity_id.in_(list(fit_ids)))
                .filter(Activity.negative_split_percent.is_(None))
                .filter(Activity.decoupling_percent.is_(None))
                .filter(Activity.running_economy.is_(None))
                .scalar()
                or 0
            )
            missing_derived_running = self._count_fit_missing_derived_running(fit_ids)

        missing_epoc_with_fit = 0
        if fit_ids:
            missing_epoc_with_fit = (
                self.db.query(func.count(Activity.activity_id))
                .filter(Activity.activity_id.in_(list(fit_ids)))
                .filter(Activity.epoc.is_(None))
                .scalar()
                or 0
            )

        return {
            "parquet_activity_count": len(fit_ids),
            "activities_with_fit": with_fit,
            "activities_total": total,
            "fit_pct": round(100.0 * with_fit / total, 1) if total else 0.0,
            "db_detailed_metrics_with_records": with_db_records,
            "fit_missing_all_derived_metrics": missing_derived,
            "fit_missing_derived_running": missing_derived_running,
            "fit_missing_epoc": missing_epoc_with_fit,
        }

    def _running_derived_query(self, fit_ids: set[str]):
        return (
            self.db.query(Activity.activity_id)
            .join(Activity.activity_type)
            .filter(Activity.activity_id.in_(list(fit_ids)))
            .filter(ActivityType.type_key.in_(running_type_keys_for_query(include_treadmill=True)))
            .filter(Activity.negative_split_percent.is_(None))
            .filter(Activity.decoupling_percent.is_(None))
            .filter(Activity.running_economy.is_(None))
        )

    def _count_fit_missing_derived_running(self, fit_ids: set[str]) -> int:
        if not fit_ids:
            return 0
        return int(self._running_derived_query(fit_ids).count())

    def _fit_sample_stats(self, activity_id: str) -> Tuple[int, int, Optional[float]]:
        if self.storage is None:
            return 0, 0, None
        try:
            details_df = self.storage.get_activity_details(int(activity_id))
        except Exception:
            return 0, 0, None
        if details_df is None or details_df.empty:
            return 0, 0, None

        details_df = enrich_fit_speed_from_distance(details_df)
        fit_rows = len(details_df)
        speed_samples = 0
        hr_coverage: Optional[float] = None
        if "speed" in details_df.columns:
            speed = pd.to_numeric(details_df["speed"], errors="coerce")
            speed_samples = int((speed > 0).sum())
        if "heart_rate" in details_df.columns:
            hr = pd.to_numeric(details_df["heart_rate"], errors="coerce")
            hr_coverage = round(100.0 * hr.notna().mean(), 1)
        return fit_rows, speed_samples, hr_coverage

    def diagnose_derived_backfill_candidate(self, activity: Activity) -> DerivedBackfillDiagnostic:
        activity_id = str(activity.activity_id)
        type_key = activity.activity_type.type_key if activity.activity_type else None
        fit_rows, speed_samples, hr_coverage = self._fit_sample_stats(activity_id)

        if not is_running_activity(activity, include_treadmill=True):
            return DerivedBackfillDiagnostic(
                activity_id=activity_id,
                type_key=type_key,
                skip_reason=DerivedBackfillSkipReason.NOT_RUNNING_SPORT,
                detail=type_key or "unknown_type",
                fit_rows=fit_rows,
                speed_samples=speed_samples,
                heart_rate_coverage_pct=hr_coverage,
            )

        summary_ok = (
            activity.average_speed
            and activity.average_heart_rate
            and activity.average_speed > 0
            and activity.average_heart_rate > 0
        )
        if fit_rows == 0:
            return DerivedBackfillDiagnostic(
                activity_id=activity_id,
                type_key=type_key,
                skip_reason=DerivedBackfillSkipReason.NO_FIT_DATA,
                detail="ingen_parquet_rader",
                fit_rows=fit_rows,
                speed_samples=speed_samples,
                heart_rate_coverage_pct=hr_coverage,
            )

        if speed_samples < 20:
            detail = f"speed_samples={speed_samples}"
            if not summary_ok:
                detail += ";mangler_avg_speed_eller_hr"
            return DerivedBackfillDiagnostic(
                activity_id=activity_id,
                type_key=type_key,
                skip_reason=DerivedBackfillSkipReason.THIN_FIT_SAMPLES,
                detail=detail,
                fit_rows=fit_rows,
                speed_samples=speed_samples,
                heart_rate_coverage_pct=hr_coverage,
            )

        if hr_coverage is not None and hr_coverage < 25:
            return DerivedBackfillDiagnostic(
                activity_id=activity_id,
                type_key=type_key,
                skip_reason=DerivedBackfillSkipReason.THIN_FIT_SAMPLES,
                detail=f"hr_coverage={hr_coverage}%",
                fit_rows=fit_rows,
                speed_samples=speed_samples,
                heart_rate_coverage_pct=hr_coverage,
            )

        return DerivedBackfillDiagnostic(
            activity_id=activity_id,
            type_key=type_key,
            skip_reason=DerivedBackfillSkipReason.ELIGIBLE,
            fit_rows=fit_rows,
            speed_samples=speed_samples,
            heart_rate_coverage_pct=hr_coverage,
        )

    def diagnose_derived_backfill_gaps(
        self,
        *,
        include_non_running: bool = False,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Klassifiserer FIT-kandidater uten avledede metrikker."""
        fit_ids = self._fit_activity_ids()
        if not fit_ids:
            return {"total": 0, "by_reason": {}, "items": []}

        query = (
            self.db.query(Activity)
            .filter(Activity.activity_id.in_(list(fit_ids)))
            .filter(Activity.negative_split_percent.is_(None))
            .filter(Activity.decoupling_percent.is_(None))
            .filter(Activity.running_economy.is_(None))
            .order_by(Activity.start_time.desc())
        )
        activities = query.all()
        diagnostics = [self.diagnose_derived_backfill_candidate(a) for a in activities]
        if not include_non_running:
            diagnostics = [
                d
                for d in diagnostics
                if d.skip_reason != DerivedBackfillSkipReason.NOT_RUNNING_SPORT
            ]
        if limit is not None:
            diagnostics = diagnostics[:limit]

        by_reason: Dict[str, int] = {}
        for item in diagnostics:
            by_reason[item.skip_reason.value] = by_reason.get(item.skip_reason.value, 0) + 1

        return {
            "total": len(diagnostics),
            "by_reason": by_reason,
            "eligible": by_reason.get(DerivedBackfillSkipReason.ELIGIBLE.value, 0),
            "items": [
                {
                    "activity_id": d.activity_id,
                    "type_key": d.type_key,
                    "skip_reason": d.skip_reason.value,
                    "detail": d.detail,
                    "fit_rows": d.fit_rows,
                    "speed_samples": d.speed_samples,
                    "heart_rate_coverage_pct": d.heart_rate_coverage_pct,
                }
                for d in diagnostics
            ],
        }

    def _fit_activity_ids(self) -> set[str]:
        ids: set[str] = set()
        if self.storage is None:
            return ids
        try:
            self.storage.reload_activity_details()
            df = self.storage.activity_details_df
            if df is not None and not df.empty and "activity_id" in df.columns:
                ids = {str(v) for v in df["activity_id"].unique()}
        except Exception:
            return ids
        return ids

    def _derived_backfill_gap_query(
        self,
        fit_ids: set[str],
        *,
        include_non_running: bool,
        include_partial: bool,
    ):
        query = (
            self.db.query(Activity)
            .filter(Activity.activity_id.in_(list(fit_ids)))
            .order_by(Activity.start_time.desc())
        )
        if include_partial:
            query = query.filter(
                or_(
                    Activity.negative_split_percent.is_(None),
                    Activity.decoupling_percent.is_(None),
                    Activity.running_economy.is_(None),
                )
            )
        else:
            query = query.filter(
                Activity.negative_split_percent.is_(None),
                Activity.decoupling_percent.is_(None),
                Activity.running_economy.is_(None),
            )
        if not include_non_running:
            query = (
                query.join(Activity.activity_type)
                .filter(ActivityType.type_key.in_(running_type_keys_for_query(include_treadmill=True)))
            )
        return query

    def fit_missing_derived_activity_ids(
        self,
        limit: Optional[int] = None,
        *,
        include_non_running: bool = False,
        include_partial: bool = False,
    ) -> List[str]:
        """Aktiviteter med FIT-parquet som mangler avledede metrikker."""
        fit_ids = self._fit_activity_ids()
        if not fit_ids:
            return []
        query = self._derived_backfill_gap_query(
            fit_ids,
            include_non_running=include_non_running,
            include_partial=include_partial,
        )
        if limit is not None:
            query = query.limit(limit)
        return [str(activity.activity_id) for activity in query.all()]

    def eligible_derived_backfill_activity_ids(
        self,
        limit: Optional[int] = None,
        *,
        include_non_running: bool = False,
        include_partial: bool = True,
    ) -> List[str]:
        """Kun kandidater diagnose merker som eligible (hopper over tynn FIT m.m.)."""
        fit_ids = self._fit_activity_ids()
        if not fit_ids:
            return []
        activities = self._derived_backfill_gap_query(
            fit_ids,
            include_non_running=include_non_running,
            include_partial=include_partial,
        ).all()
        eligible: List[str] = []
        for activity in activities:
            diagnostic = self.diagnose_derived_backfill_candidate(activity)
            if diagnostic.skip_reason != DerivedBackfillSkipReason.ELIGIBLE:
                continue
            eligible.append(str(activity.activity_id))
            if limit is not None and len(eligible) >= limit:
                break
        return eligible

    def _scalar_count(self, *filters) -> int:
        query = self.db.query(func.count(Activity.activity_id))
        for clause in filters:
            query = query.filter(clause)
        return int(query.scalar() or 0)

    def _build_recommendations(self, report: DataCoverageReport, as_of: date) -> List[BackfillRecommendation]:
        recs: List[BackfillRecommendation] = []
        total = report.activity_count
        fit = report.fit

        missing_epoc = self._scalar_count(Activity.epoc.is_(None))
        missing_summary = self._scalar_count(
            Activity.activity_body_battery_delta.is_(None),
            Activity.ground_contact_time.is_(None),
        )
        missing_te = self._scalar_count(
            (Activity.total_training_effect.is_(None)) | (Activity.total_training_effect <= 0)
        )

        if fit.get("fit_missing_all_derived_metrics", 0) > 0:
            running_missing = fit.get("fit_missing_derived_running", 0)
            recs.append(
                BackfillRecommendation(
                    priority=1,
                    key="recompute_derived_metrics",
                    title="Reberegn lokale aktivitetsmetrikker fra FIT",
                    cause=GapCause.BACKFILL_CANDIDATE,
                    risk=BackfillRisk.LOW,
                    value_for_mcp="Høy – negative split, decoupling og løpsøkonomi brukes i analyse.",
                    action="python scripts/backfill_derived_metrics.py --diagnose; deretter --limit 200.",
                    estimated_scope=(
                        f"{running_missing} løp/tredemølle med FIT uten avledede metrikker "
                        f"({fit['fit_missing_all_derived_metrics']} totalt inkl. andre idretter)"
                    ),
                    notes="Kjør --diagnose først; mange kandidater kan være feilsport eller tynn FIT.",
                )
            )

        if missing_epoc > 0 or missing_summary > 0:
            recs.append(
                BackfillRecommendation(
                    priority=2,
                    key="activity_summary_metrics",
                    title="Backfill activity summary (EPOC, TE, løpsdynamikk, BB-delta)",
                    cause=GapCause.SYNC_GAP,
                    risk=BackfillRisk.MEDIUM,
                    value_for_mcp="Svært høy – treningsslast, readiness og recovery per økt.",
                    action="sync_training_effect_for_missing() eller sync_training_effect_data(ignore_sync_state=True) per periode.",
                    estimated_scope=f"EPOC mangler på {missing_epoc}/{total}; summary-felter tynt på eldre økter",
                    notes="Eldre økter kan mangle felter i Garmin API selv etter backfill.",
                )
            )

        if fit.get("activities_with_fit", 0) < total:
            gap = total - int(fit.get("activities_with_fit", 0))
            recs.append(
                BackfillRecommendation(
                    priority=3,
                    key="fit_download",
                    title="FIT-nedlasting for aktiviteter uten detaljdata",
                    cause=GapCause.SYNC_GAP,
                    risk=BackfillRisk.MEDIUM,
                    value_for_mcp="Høy – grunnlag for ruteanalyse, pulsprofiler og lokale beregninger.",
                    action="download_fit_data_for_activities() / download_fit_data_for_period() i kontrollerte batcher.",
                    estimated_scope=f"{gap} aktiviteter uten FIT-parquet ({fit.get('fit_pct', 0)}% dekning)",
                    notes="Mange hull er fra 2009–2017; API kan mangle FIT for eldste økter (api_limited).",
                )
            )

        hrv = next((d for d in report.datasets if d.key == "hrv"), None)
        if hrv and hrv.expected_days and hrv.filled_days is not None:
            gap_days = hrv.expected_days - hrv.filled_days
            if gap_days > 0 or (hrv.missing_marked or 0) > 0:
                recs.append(
                    BackfillRecommendation(
                        priority=4,
                        key="hrv_gaps",
                        title="Fyll HRV-hull siden 2023",
                        cause=GapCause.SYNC_GAP if gap_days < 50 else GapCause.API_LIMITED,
                        risk=BackfillRisk.MEDIUM,
                        value_for_mcp="Høy – recovery/HRV i readiness og coaching.",
                        action="sync_hrv_data(force_refresh_recent=False) eller health API med fill_gaps=true.",
                        estimated_scope=f"{gap_days} mulige dager i range + {hrv.missing_marked} markert manglende",
                        notes="Før 2023-01-01 er HRV normalt ikke tilgjengelig via Garmin.",
                    )
                )

        bb = next((d for d in report.datasets if d.key == "body_battery"), None)
        if bb and bb.first_date:
            recs.append(
                BackfillRecommendation(
                    priority=5,
                    key="body_battery_daily",
                    title="Backfill daglig Body Battery i lagret periode",
                    cause=GapCause.SYNC_GAP,
                    risk=BackfillRisk.MEDIUM,
                    value_for_mcp="Høy – recovery_context og health.body_battery_* i MCP.",
                    action="BodyBatteryService.sync_body_battery_data_to_database(start, end) per måned.",
                    estimated_scope=f"{bb.row_count} dager lagret ({bb.first_date}–{bb.last_date})",
                    notes="Data før første lagrede dato er sannsynligvis api/device-begrenset.",
                )
            )

        sleep = next((d for d in report.datasets if d.key == "sleep"), None)
        if sleep and sleep.first_date and sleep.expected_days and sleep.filled_days is not None:
            gap_days = sleep.expected_days - sleep.filled_days
            if gap_days > 0:
                recs.append(
                    BackfillRecommendation(
                        priority=6,
                        key="sleep_recent",
                        title="Kompletter søvn i nåværende lagringsvindu",
                        cause=GapCause.SYNC_GAP,
                        risk=BackfillRisk.LOW,
                        value_for_mcp="Middels – søvnscore og varighet i recovery.",
                        action=f"sync_sleep_data() for {sleep.first_date}–{as_of}.",
                        estimated_scope=f"{gap_days} dager i {sleep.first_date}–{sleep.last_date}",
                        notes="Søvn før første faktiske registrering er trolig ikke hos Garmin.",
                    )
                )

        stress = next((d for d in report.datasets if d.key == "stress"), None)
        if stress and stress.first_date:
            recs.append(
                BackfillRecommendation(
                    priority=7,
                    key="stress_recent",
                    title="Kompletter stress i lagret periode",
                    cause=GapCause.SYNC_GAP,
                    risk=BackfillRisk.LOW,
                    value_for_mcp="Middels – stressnivå i recovery.",
                    action="sync_stress_data() fra stress.first_date; test eldre datoer forsiktig.",
                    estimated_scope=f"{stress.row_count} dager ({stress.first_date}–{stress.last_date})",
                    notes="Stress før enhetens støtteperiode er sannsynligvis api_limited.",
                )
            )

        gpm = next((d for d in report.datasets if d.key == "garmin_performance_metrics"), None)
        if gpm and report.activity_last and gpm.last_date and gpm.last_date < report.activity_last:
            recs.append(
                BackfillRecommendation(
                    priority=8,
                    key="garmin_performance_metrics",
                    title="Oppdater daglige Garmin performance metrics",
                    cause=GapCause.SYNC_GAP,
                    risk=BackfillRisk.LOW,
                    value_for_mcp="Middels – VO2/load balance/treningsstatus.",
                    action="sync_garmin_performance_metrics() for siste uke.",
                    estimated_scope=f"Siste lagret {gpm.last_date}, aktiviteter til {report.activity_last}",
                )
            )

        weather_count = report.activity_fields.get("weather", {}).get("fields", {}).get("weather_condition", {}).get("count", 0)
        if total and weather_count / total < 0.2:
            recs.append(
                BackfillRecommendation(
                    priority=9,
                    key="activity_weather",
                    title="Værberikelse for aktiviteter med GPS/FIT",
                    cause=GapCause.BACKFILL_CANDIDATE,
                    risk=BackfillRisk.LOW,
                    value_for_mcp="Lav–middels – kontekst for utendørs økter.",
                    action="backfill_garmin_weather.py / sync_activity_weather per periode.",
                    estimated_scope=f"{weather_count}/{total} aktiviteter har vær ({round(100*weather_count/total,1)}%)",
                )
            )

        if missing_te > 0:
            recs.append(
                BackfillRecommendation(
                    priority=10,
                    key="training_effect",
                    title="Training Effect for økter med 0/manglende TE",
                    cause=GapCause.SYNC_GAP,
                    risk=BackfillRisk.MEDIUM,
                    value_for_mcp="Middels – treningseffekt og etiketter.",
                    action="sync_training_effect_for_missing().",
                    estimated_scope=f"{missing_te} aktiviteter",
                )
            )

        recs.sort(key=lambda r: r.priority)
        return recs
