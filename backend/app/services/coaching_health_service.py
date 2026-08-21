"""Aggregate coaching system health — observed values only, no placeholders."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database.migrations import get_schema_version
from ..database.models.activity import Activity, GarminPerformanceMetric
from ..database.models.coaching_v5 import (
    CalibrationSnapshot,
    RecommendationExecution,
    RecommendationRecord,
    ShadowRecommendation,
    ValidationRun,
)
from ..database.models.sleep import HRV, RestingHeartRate, Sleep
from ..database.models.sync_state import SyncState
from .adaptive_threshold_service import AdaptiveThresholdService
from .builtin_model_registry import BuiltinModelRegistry
from .coaching_model_registry import CoachingModelRegistry
from .freshness_policy import FreshnessPolicy
from .health_status_policy import HealthStatusPolicy
from .personalization_stability_service import PersonalizationStabilityService
from .ppap_metrics_service import PpapMetricsService
from .status_semantics import SourceType


class CoachingHealthService:
    def __init__(self, db: Session, ppap: Optional[PpapMetricsService] = None):
        self.db = db
        self._ppap = ppap or PpapMetricsService(db, None)
        self._thresholds = AdaptiveThresholdService(db, None)

    def report(self, day: Optional[date] = None) -> Dict[str, Any]:
        day = day or date.today()
        findings: List[Dict[str, Any]] = []
        checks: Dict[str, Any] = {}

        sync = self.db.query(SyncState).order_by(SyncState.updated_at.desc(), SyncState.id.desc()).first()
        last_sync = sync.last_synced_at if sync else None
        checks["last_successful_garmin_sync"] = {
            "value": last_sync.isoformat() if last_sync else None,
            "source_type": SourceType.OBSERVED.value if last_sync else SourceType.MISSING.value,
        }
        if last_sync is None:
            findings.append(self._finding("no_sync_state"))

        # Real Alembic comparison — never auto-migrate
        try:
            schema = get_schema_version(self.db.get_bind())
        except Exception as exc:
            schema = {
                "schema_version": None,
                "schema_head": None,
                "schema_at_head": False,
                "error": str(exc),
            }
        checks["db_migration"] = {
            "current_revision": schema.get("schema_version"),
            "expected_head": schema.get("schema_head"),
            "up_to_date": bool(schema.get("schema_at_head")),
            "source_type": SourceType.CONFIG.value,
            "error": schema.get("error"),
        }
        if not schema.get("schema_at_head"):
            findings.append(self._finding("migration_behind"))

        active = CoachingModelRegistry(self.db).get_active("ranker")
        checks["active_coaching_model"] = {
            "value": active,
            "source_type": SourceType.OBSERVED.value
            if active.get("id")
            else SourceType.CONFIG.value,
        }

        latest_run = (
            self.db.query(ValidationRun)
            .filter(ValidationRun.status == "completed")
            .order_by(ValidationRun.created_at.desc())
            .first()
        )
        checks["latest_validation_run_id"] = {
            "value": latest_run.id if latest_run else None,
            "source_type": SourceType.OBSERVED.value if latest_run else SourceType.MISSING.value,
        }
        if latest_run is None and not BuiltinModelRegistry.is_known(
            active.get("model_key") or "ranker", active.get("version") or "default"
        ):
            findings.append(self._finding("active_model_lacks_validation_run"))
        elif latest_run is None:
            findings.append(self._finding("no_validation_run"))

        prospective_n = self.db.query(func.count(RecommendationRecord.id)).scalar() or 0
        exec_n = self.db.query(func.count(RecommendationExecution.id)).scalar() or 0
        shadow_n = self.db.query(func.count(ShadowRecommendation.id)).scalar() or 0
        checks["prospective_sample_count"] = {"value": prospective_n, "source_type": SourceType.OBSERVED.value}
        checks["execution_sample_count"] = {"value": exec_n, "source_type": SourceType.OBSERVED.value}
        checks["shadow_sample_count"] = {"value": shadow_n, "source_type": SourceType.OBSERVED.value}
        if prospective_n < 5:
            findings.append(self._finding("low_prospective_n"))
        if shadow_n == 0:
            findings.append(self._finding("no_shadow_evidence"))

        orphan_exec = (
            self.db.query(func.count(RecommendationExecution.id))
            .filter(RecommendationExecution.recommendation_id.is_(None))
            .scalar()
            or 0
        )
        checks["orphan_executions"] = {"value": orphan_exec, "source_type": SourceType.OBSERVED.value}
        if orphan_exec:
            findings.append(self._finding("orphan_executions"))

        stability = PersonalizationStabilityService(self.db).assess(as_of_date=day)
        checks["calibration_stability"] = {
            "value": stability.get("status"),
            "source_type": SourceType.DERIVED_FROM_OBSERVED.value,
        }

        freshness = self._resolve_freshness(day)
        checks["data_freshness"] = freshness
        for metric, payload in freshness.items():
            if payload.get("status") == "missing" and metric in {"lt2", "hrv_baseline"}:
                findings.append(self._finding(f"missing_{metric}"))
            elif payload.get("status") == "stale" and metric in {"lt2", "critical_speed"}:
                findings.append(self._finding(f"stale_{metric}"))

        status = HealthStatusPolicy.aggregate(f["code"] for f in findings)
        return {
            "status": status,
            "checks": checks,
            "findings": findings,
            "issues": [f["code"] for f in findings],  # compatibility
            "as_of": day.isoformat(),
            "note": "All health fields are OBSERVED, DERIVED_FROM_OBSERVED, CONFIG, or MISSING — no placeholders.",
        }

    def _resolve_freshness(self, day: date) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        # LT2
        lt2 = self._thresholds.latest_lt2(day)
        observed = None
        if lt2.get("observed_at"):
            try:
                observed = datetime.fromisoformat(str(lt2["observed_at"]).replace("Z", "+00:00")).date()
            except ValueError:
                observed = None
        out["lt2"] = self._freshness_entry("lt2", day, observed, SourceType.OBSERVED if observed else SourceType.MISSING)

        # HRV baseline = latest HRV measurement date
        hrv_row = (
            self.db.query(HRV.measurement_date)
            .filter(HRV.measurement_date.isnot(None), HRV.measurement_date <= day)
            .order_by(HRV.measurement_date.desc())
            .first()
        )
        hrv_day = hrv_row[0] if hrv_row else None
        out["hrv_baseline"] = self._freshness_entry(
            "hrv_baseline", day, hrv_day, SourceType.OBSERVED if hrv_day else SourceType.MISSING
        )

        # Critical speed snapshot calculated_at when available
        cs_day = None
        if self._ppap.storage is not None:
            try:
                from .performance_metrics_service import PerformanceMetricsService

                payload = PerformanceMetricsService(self.db, self._ppap.storage).get_snapshot_payload("critical_speed")
                if payload and payload.get("calculated_at"):
                    cs_day = datetime.fromisoformat(str(payload["calculated_at"]).replace("Z", "+00:00")).date()
            except Exception:
                cs_day = None
        out["critical_speed"] = self._freshness_entry(
            "critical_speed", day, cs_day, SourceType.OBSERVED if cs_day else SourceType.MISSING
        )

        # VO2max from GarminPerformanceMetric
        vo2 = (
            self.db.query(GarminPerformanceMetric.date)
            .filter(
                GarminPerformanceMetric.date.isnot(None),
                GarminPerformanceMetric.vo2_max_precise.isnot(None),
            )
            .order_by(GarminPerformanceMetric.date.desc())
            .first()
        )
        vo2_day = vo2[0].date() if vo2 and hasattr(vo2[0], "date") else (vo2[0] if vo2 else None)
        if isinstance(vo2_day, datetime):
            vo2_day = vo2_day.date()
        out["vo2max"] = self._freshness_entry(
            "vo2max", day, vo2_day, SourceType.OBSERVED if vo2_day else SourceType.MISSING
        )

        last_act = (
            self.db.query(Activity.start_time)
            .filter(Activity.start_time.isnot(None))
            .order_by(Activity.start_time.desc())
            .first()
        )
        act_day = last_act[0].date() if last_act and last_act[0] else None
        out["last_activity"] = self._freshness_entry(
            "last_activity", day, act_day, SourceType.OBSERVED if act_day else SourceType.MISSING
        )

        sleep_row = (
            self.db.query(Sleep.sleep_date)
            .filter(Sleep.sleep_date.isnot(None), Sleep.sleep_date <= day)
            .order_by(Sleep.sleep_date.desc())
            .first()
        )
        sleep_day = sleep_row[0] if sleep_row else None
        out["last_sleep"] = self._freshness_entry(
            "last_sleep", day, sleep_day, SourceType.OBSERVED if sleep_day else SourceType.MISSING
        )

        rhr_row = (
            self.db.query(RestingHeartRate.measurement_date)
            .filter(RestingHeartRate.measurement_date.isnot(None), RestingHeartRate.measurement_date <= day)
            .order_by(RestingHeartRate.measurement_date.desc())
            .first()
        )
        rhr_day = rhr_row[0] if rhr_row else None
        out["last_rhr"] = self._freshness_entry(
            "last_rhr", day, rhr_day, SourceType.OBSERVED if rhr_day else SourceType.MISSING
        )

        cal = (
            self.db.query(CalibrationSnapshot)
            .order_by(CalibrationSnapshot.calculated_at.desc())
            .first()
        )
        cal_day = None
        if cal:
            cal_day = cal.as_of_date or (cal.calculated_at.date() if cal.calculated_at else None)
        out["calibration_snapshot"] = self._freshness_entry(
            "calibration_snapshot",
            day,
            cal_day,
            SourceType.OBSERVED if cal_day else SourceType.MISSING,
        )
        return out

    @staticmethod
    def _freshness_entry(
        metric: str,
        as_of: date,
        observed_on: Optional[date],
        source_type: SourceType,
    ) -> Dict[str, Any]:
        assessed = FreshnessPolicy.assess(metric, as_of=as_of, observed_on=observed_on)
        status = assessed.get("freshness") or "missing"
        return {
            "metric": metric,
            "observed_at": observed_on.isoformat() if observed_on else None,
            "age_days": assessed.get("age_days"),
            "status": status,  # fresh|aging|stale|missing
            "freshness": status,
            "usable_for": assessed.get("usable_for") or [],
            "source_type": source_type.value,
            "high_confidence_primary": assessed.get("high_confidence_primary", False),
        }

    @staticmethod
    def _finding(code: str) -> Dict[str, Any]:
        return {"code": code, "severity": HealthStatusPolicy.severity_for(code).value}
