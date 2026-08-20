"""Adaptiv LT1-estimering med prioritert evidenskjede og eksplisitt fallback."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..database.models.lactate_threshold_history import LactateThresholdHistory
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .coaching_analysis_service import CoachingAnalysisService
from .metric_evidence import confidence_from_sample_count

LT1_FROM_LT2_HR_RATIO = 0.85
LT1_FROM_LT2_SPEED_RATIO = 0.82
STABLE_EASY_HR_MAX_RATIO = 0.92
STABLE_EASY_MIN_DURATION_S = 30 * 60
STABLE_EASY_MAX_DRIFT_PCT = 5.0
STABLE_EASY_LOOKBACK_DAYS = 120


class AdaptiveThresholdService:
    """Estimerer LT1 med prioritet: målt > historisk stabil > drift/EF > LT2-fallback."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        coaching: Optional[CoachingAnalysisService] = None,
    ):
        self.db = db
        self.storage = storage
        self._coaching = coaching or CoachingAnalysisService(db, storage)

    def estimate_lt1(
        self,
        *,
        end_date: Optional[date] = None,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        end = end_date or date.today()
        lt2 = self._latest_lt2(end)
        evidence: List[str] = []
        fallback_used = False
        method = "unknown"
        confidence = 0.0
        lt1_hr: Optional[float] = None
        lt1_speed: Optional[float] = None

        verified = self._verified_lt1(end)
        if verified:
            lt1_hr = verified.get("heart_rate_bpm")
            lt1_speed = verified.get("speed_mps")
            method = verified.get("method", "verified_threshold")
            confidence = 0.95
            evidence.extend(verified.get("evidence", []))

        if lt1_hr is None:
            stable = self._stable_easy_runs_lt1(end, include_treadmill=include_treadmill)
            if stable:
                lt1_hr = stable.get("lt1_hr")
                lt1_speed = stable.get("lt1_speed_mps")
                method = "stable_easy_runs"
                confidence = stable.get("confidence", 0.7)
                evidence.extend(stable.get("evidence", []))

        if lt1_hr is None and lt2:
            drift = self._drift_informed_lt1(end, lt2, include_treadmill=include_treadmill)
            if drift:
                lt1_hr = drift.get("lt1_hr")
                method = "drift_decoupling"
                confidence = drift.get("confidence", 0.55)
                evidence.extend(drift.get("evidence", []))

        if lt1_hr is None and lt2:
            ef = self._pace_hr_ef_lt1(end, lt2, include_treadmill=include_treadmill)
            if ef:
                lt1_hr = ef.get("lt1_hr")
                lt1_speed = ef.get("lt1_speed_mps")
                method = "pace_hr_ef_response"
                confidence = ef.get("confidence", 0.5)
                evidence.extend(ef.get("evidence", []))

        if lt1_hr is None and lt2.get("heart_rate_bpm"):
            lt1_hr = float(lt2["heart_rate_bpm"]) * LT1_FROM_LT2_HR_RATIO
            fallback_used = True
            method = "lt2_multiplier_fallback"
            confidence = 0.35
            evidence.append(f"LT1 estimated as {LT1_FROM_LT2_HR_RATIO:.0%} of LT2 HR")

        if lt1_speed is None and lt2.get("speed_mps"):
            lt1_speed = float(lt2["speed_mps"]) * LT1_FROM_LT2_SPEED_RATIO
            if fallback_used:
                evidence.append(f"LT1 speed estimated as {LT1_FROM_LT2_SPEED_RATIO:.0%} of LT2 speed")

        lt1_pace = 1000.0 / lt1_speed if lt1_speed and lt1_speed > 0 else None

        return {
            "lt1_hr": round(lt1_hr, 0) if lt1_hr is not None else None,
            "lt1_speed_mps": round(lt1_speed, 3) if lt1_speed is not None else None,
            "lt1_pace_sec_km": round(lt1_pace, 1) if lt1_pace is not None else None,
            "confidence": round(confidence, 2),
            "method": method,
            "evidence": evidence,
            "fallback_used": fallback_used,
            "source_type": "estimated" if fallback_used else ("derived" if method != "verified_threshold" else "measured"),
            "limitations": (
                ["LT1 is heuristic — not a direct lactate measurement"]
                if fallback_used or method != "verified_threshold"
                else []
            ),
        }

    def latest_lt2(self, end_date: Optional[date] = None) -> Dict[str, Any]:
        """LT2 fra historikk med stale-flagg. Ikke en ny terskelmodell."""
        end = end_date or date.today()
        lt2 = self._latest_lt2(end)
        observed = lt2.get("observed_at")
        freshness_days = None
        stale = True
        if observed:
            try:
                from datetime import datetime

                ts = datetime.fromisoformat(str(observed).replace("Z", "+00:00"))
                freshness_days = (end - ts.date()).days
                stale = freshness_days > 90
            except (TypeError, ValueError):
                stale = True
        speed = lt2.get("speed_mps")
        pace = 1000.0 / float(speed) if speed and float(speed) > 0 else None
        hr = lt2.get("heart_rate_bpm")
        confidence = 0.0
        if hr:
            confidence = 0.35 if stale else 0.75
        return {
            "lt2_hr": round(float(hr), 0) if hr is not None else None,
            "lt2_speed_mps": round(float(speed), 3) if speed is not None else None,
            "lt2_pace_sec_km": round(pace, 1) if pace is not None else None,
            "observed_at": observed,
            "freshness_days": freshness_days,
            "stale": stale,
            "confidence": confidence,
            "source": "lactate_threshold_history",
        }

    def _latest_lt2(self, end: date) -> Dict[str, Any]:
        history = (
            self.db.query(LactateThresholdHistory)
            .filter(func.date(LactateThresholdHistory.observed_at) <= end)
            .order_by(LactateThresholdHistory.observed_at.desc())
            .first()
        )
        if history:
            return {
                "heart_rate_bpm": history.lactate_threshold_heart_rate,
                "speed_mps": history.lactate_threshold_speed,
                "observed_at": history.observed_at.isoformat() if history.observed_at else None,
            }
        return {}

    def _verified_lt1(self, end: date) -> Optional[Dict[str, Any]]:
        """Direkte/verifisert threshold — kun hvis eksplisitt lagret som LT1-kilde."""
        row = (
            self.db.query(LactateThresholdHistory)
            .filter(
                func.date(LactateThresholdHistory.observed_at) <= end,
                LactateThresholdHistory.source.in_(("lab", "verified", "manual_lt1")),
            )
            .order_by(LactateThresholdHistory.observed_at.desc())
            .first()
        )
        if row is None or not row.lactate_threshold_heart_rate:
            return None
        return {
            "heart_rate_bpm": float(row.lactate_threshold_heart_rate),
            "speed_mps": float(row.lactate_threshold_speed) if row.lactate_threshold_speed else None,
            "method": "verified_threshold",
            "evidence": [f"verified source={row.source}", f"observed_at={row.observed_at.date().isoformat()}"],
        }

    def _stable_easy_runs_lt1(
        self,
        end: date,
        *,
        include_treadmill: bool,
    ) -> Optional[Dict[str, Any]]:
        start = end - timedelta(days=STABLE_EASY_LOOKBACK_DAYS)
        lt2_hr = self._latest_lt2(end).get("heart_rate_bpm")
        if not lt2_hr:
            return None

        activities = (
            self.db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                    Activity.duration.isnot(None),
                    Activity.duration >= STABLE_EASY_MIN_DURATION_S,
                    Activity.average_heart_rate.isnot(None),
                )
            )
            .order_by(Activity.start_time.desc())
            .all()
        )
        lt1_ceiling = float(lt2_hr) * 0.88
        stable_hrs: List[float] = []
        stable_speeds: List[float] = []
        for activity in activities:
            if not is_running_activity(activity, include_treadmill=include_treadmill):
                continue
            hr = float(activity.average_heart_rate)
            if hr > lt1_ceiling:
                continue
            if activity.hr_drift_pct is not None and float(activity.hr_drift_pct) > STABLE_EASY_MAX_DRIFT_PCT:
                continue
            if activity.decoupling_percent is not None and float(activity.decoupling_percent) > STABLE_EASY_MAX_DRIFT_PCT:
                continue
            stable_hrs.append(hr)
            if activity.average_speed and activity.average_speed > 0:
                stable_speeds.append(float(activity.average_speed))

        if len(stable_hrs) < 3:
            return None

        lt1_hr = median(stable_hrs) * 1.02
        lt1_speed = median(stable_speeds) if stable_speeds else None
        confidence = confidence_from_sample_count(len(stable_hrs), min_samples=3, target_samples=10)
        return {
            "lt1_hr": lt1_hr,
            "lt1_speed_mps": lt1_speed,
            "confidence": confidence,
            "evidence": [
                f"{len(stable_hrs)} stable easy runs with low drift",
                f"median_easy_hr={median(stable_hrs):.0f}bpm",
            ],
        }

    def _drift_informed_lt1(
        self,
        end: date,
        lt2: Dict[str, Any],
        *,
        include_treadmill: bool,
    ) -> Optional[Dict[str, Any]]:
        start = end - timedelta(days=90)
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
        drift_samples = [
            float(a.hr_drift_pct)
            for a in activities
            if is_running_activity(a, include_treadmill=include_treadmill) and a.hr_drift_pct is not None
        ][-20:]
        median_drift = median(drift_samples) if drift_samples else None
        lt2_hr = lt2.get("heart_rate_bpm")
        if lt2_hr is None or median_drift is None:
            return None
        adjustment = min(0.05, max(-0.02, float(median_drift) / 100.0))
        lt1_hr = float(lt2_hr) * (LT1_FROM_LT2_HR_RATIO - adjustment)
        return {
            "lt1_hr": lt1_hr,
            "confidence": 0.55,
            "evidence": [f"drift-adjusted LT1 using median_hr_drift={median_drift}%"],
        }

    def _pace_hr_ef_lt1(
        self,
        end: date,
        lt2: Dict[str, Any],
        *,
        include_treadmill: bool,
    ) -> Optional[Dict[str, Any]]:
        start = end - timedelta(days=90)
        lt2_hr = lt2.get("heart_rate_bpm")
        if not lt2_hr:
            return None
        lt1_hr_estimate = float(lt2_hr) * LT1_FROM_LT2_HR_RATIO
        candidates: List[float] = []
        activities = (
            self.db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .order_by(Activity.start_time.desc())
            .limit(30)
            .all()
        )
        for activity in activities:
            if not is_running_activity(activity, include_treadmill=include_treadmill):
                continue
            if not activity.average_speed or not activity.average_heart_rate:
                continue
            if float(activity.average_heart_rate) > lt1_hr_estimate:
                continue
            candidates.append(float(activity.average_speed) / float(activity.average_heart_rate))

        if len(candidates) < 3:
            return None
        ratio = sum(candidates) / len(candidates)
        lt1_hr = lt1_hr_estimate
        lt1_speed = lt1_hr * ratio
        return {
            "lt1_hr": lt1_hr,
            "lt1_speed_mps": lt1_speed,
            "confidence": confidence_from_sample_count(len(candidates)),
            "evidence": [f"pace-HR economy from {len(candidates)} easy runs"],
        }
