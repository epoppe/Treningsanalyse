"""Kontekstavhengig kvalitetsvurdering av gjennomførte løpeøkter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.activity import Activity, ActivityLap
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .coaching_decision_metrics_service import CoachingDecisionMetricsService
from .metric_evidence import confidence_from_sample_count
from .ppap_metrics_service import PpapMetricsService
from .session_classifier_service import SessionClassifierService

EASY_TYPES = frozenset({"recovery_run", "easy_aerobic", "long_aerobic", "steady"})
THRESHOLD_TYPES = frozenset({"tempo", "threshold"})
VO2_TYPES = frozenset({"vo2_intervals", "anaerobic"})


class SessionQualityService:
    """Scores session quality relative to session type — not absolute across types."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._classifier = SessionClassifierService(db, storage)
        self._decision = CoachingDecisionMetricsService(db, self._ppap)

    def evaluate(
        self,
        activity: Activity,
        *,
        session_type: Optional[str] = None,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        if not is_running_activity(activity, include_treadmill=include_treadmill):
            return self._empty("unknown", "non_running_activity")

        if session_type is None:
            classification = self._classifier.classify_activity(
                activity,
                include_treadmill=include_treadmill,
            )
            session_type = classification.get("session_type", "unknown")
            type_confidence = float(classification.get("confidence") or 0.3)
        else:
            type_confidence = 0.8

        if session_type in EASY_TYPES or session_type == "mixed":
            return self._score_easy_long(activity, session_type, type_confidence)
        if session_type in THRESHOLD_TYPES:
            return self._score_threshold(activity, session_type, type_confidence)
        if session_type in VO2_TYPES:
            return self._score_vo2(activity, session_type, type_confidence)
        if session_type == "race":
            return self._score_threshold(activity, session_type, type_confidence)
        return self._empty(session_type, "unsupported_session_type_for_quality")

    def _score_easy_long(
        self,
        activity: Activity,
        session_type: str,
        type_confidence: float,
    ) -> Dict[str, Any]:
        components: Dict[str, float] = {}
        flags: List[str] = []
        score = 70.0

        if activity.hr_drift_pct is not None:
            drift = float(activity.hr_drift_pct)
            components["hr_drift"] = max(0.0, 100.0 - drift * 8.0)
            score = score * 0.7 + components["hr_drift"] * 0.3
            if drift > 8:
                flags.append("elevated_hr_drift")

        if activity.decoupling_percent is not None:
            dec = float(activity.decoupling_percent)
            components["decoupling"] = max(0.0, 100.0 - dec * 6.0)
            score = score * 0.75 + components["decoupling"] * 0.25
            if dec > 6:
                flags.append("aerobic_decoupling")

        if activity.avg_efficiency_factor is not None:
            components["efficiency_factor"] = min(100.0, float(activity.avg_efficiency_factor) * 2500)
            score = score * 0.85 + components["efficiency_factor"] * 0.15

        if activity.pace_drop_pct is not None:
            drop = float(activity.pace_drop_pct)
            components["pace_stability"] = max(0.0, 100.0 - drop * 5.0)
            score = score * 0.8 + components["pace_stability"] * 0.2
            if drop > 8:
                flags.append("pace_instability")

        if activity.cadence_drop_pct is not None:
            components["cadence_stability"] = max(0.0, 100.0 - float(activity.cadence_drop_pct) * 4.0)
            score = score * 0.9 + components["cadence_stability"] * 0.1

        long_quality = self._decision.compute_long_run_quality(activity)
        if long_quality is not None:
            components["long_run_quality"] = float(long_quality)
            score = score * 0.5 + float(long_quality) * 0.5

        if activity.fatigue_resistance_score is not None:
            components["durability"] = float(activity.fatigue_resistance_score)

        confidence = confidence_from_sample_count(len(components), min_samples=2, target_samples=5)
        confidence *= type_confidence
        if type_confidence < 0.5:
            flags.append("session_classification_uncertain")
        interpretation = self._interpret(score, flags, session_type)

        return {
            "session_type": session_type,
            "quality_score": round(max(0.0, min(100.0, score)), 1),
            "confidence": round(confidence, 2),
            "components": {k: round(v, 1) for k, v in components.items()},
            "flags": flags,
            "interpretation": interpretation,
            "comparability_note": "Scores are relative within easy/long session types only.",
        }

    def _score_threshold(
        self,
        activity: Activity,
        session_type: str,
        type_confidence: float,
    ) -> Dict[str, Any]:
        components: Dict[str, float] = {}
        flags: List[str] = []
        score = 65.0

        if activity.hr_drift_pct is not None:
            drift = float(activity.hr_drift_pct)
            components["hr_response"] = max(0.0, 100.0 - max(0.0, drift - 3.0) * 5.0)
            score = score * 0.7 + components["hr_response"] * 0.3
            if drift > 10:
                flags.append("excessive_threshold_drift")

        if activity.pace_drop_pct is not None:
            components["pace_stability"] = max(0.0, 100.0 - float(activity.pace_drop_pct) * 4.0)
            score = score * 0.7 + components["pace_stability"] * 0.3

        if activity.average_power or activity.normalized_power:
            power = float(activity.normalized_power or activity.average_power or 0)
            components["power_present"] = 80.0 if power > 0 else 40.0

        te = activity.total_training_effect
        if te is not None:
            components["training_effect"] = min(100.0, float(te) / 5.0 * 100.0)
            score = score * 0.8 + components["training_effect"] * 0.2

        interval_completion = self._interval_completion(activity)
        if interval_completion is not None:
            components["interval_completion"] = interval_completion
            score = score * 0.7 + interval_completion * 0.3

        confidence = confidence_from_sample_count(len(components), min_samples=2, target_samples=4)
        confidence *= type_confidence
        if type_confidence < 0.5:
            flags.append("session_classification_uncertain")
        return {
            "session_type": session_type,
            "quality_score": round(max(0.0, min(100.0, score)), 1),
            "confidence": round(confidence, 2),
            "components": {k: round(v, 1) for k, v in components.items()},
            "flags": flags,
            "interpretation": self._interpret(score, flags, session_type),
            "comparability_note": "Scores are relative within threshold/tempo/race types only.",
        }

    def _score_vo2(
        self,
        activity: Activity,
        session_type: str,
        type_confidence: float,
    ) -> Dict[str, Any]:
        components: Dict[str, float] = {}
        flags: List[str] = []
        score = 60.0

        laps = self._work_laps(activity)
        if len(laps) >= 3:
            speeds = [float(lap.average_speed) for lap in laps if lap.average_speed]
            hrs = [float(lap.average_heart_rate) for lap in laps if lap.average_heart_rate]
            if speeds:
                mean_s = sum(speeds) / len(speeds)
                cv = (self._pstdev(speeds) / mean_s * 100) if mean_s > 0 else 100
                components["speed_consistency"] = max(0.0, 100.0 - cv * 3.0)
                score = score * 0.6 + components["speed_consistency"] * 0.4
                if len(speeds) >= 3 and speeds[-1] < speeds[0] * 0.95:
                    flags.append("interval_degradation")
                    components["degradation"] = max(0.0, 100.0 - (1 - speeds[-1] / speeds[0]) * 200)
            if hrs:
                components["hr_response"] = min(100.0, (sum(hrs) / len(hrs) / 180.0) * 100)
            components["repeated_intervals"] = min(100.0, len(laps) / 6.0 * 100)
            score = score * 0.8 + components["repeated_intervals"] * 0.2
        else:
            flags.append("few_work_intervals")
            if activity.total_anaerobic_training_effect:
                components["anaerobic_te"] = min(
                    100.0,
                    float(activity.total_anaerobic_training_effect) / 4.0 * 100,
                )
                score = components["anaerobic_te"]

        confidence = confidence_from_sample_count(len(components), min_samples=1, target_samples=3)
        confidence *= type_confidence
        if type_confidence < 0.5:
            flags.append("session_classification_uncertain")
        return {
            "session_type": session_type,
            "quality_score": round(max(0.0, min(100.0, score)), 1),
            "confidence": round(confidence, 2),
            "components": {k: round(v, 1) for k, v in components.items()},
            "flags": flags,
            "interpretation": self._interpret(score, flags, session_type),
            "comparability_note": "Scores are relative within VO2/anaerobic types only.",
        }

    def _work_laps(self, activity: Activity) -> List[ActivityLap]:
        laps = list(activity.laps or [])
        if not laps and activity.activity_id:
            laps = (
                self.db.query(ActivityLap)
                .filter(ActivityLap.activity_id == activity.activity_id)
                .order_by(ActivityLap.lap_number)
                .all()
            )
        return [
            lap
            for lap in laps
            if lap.duration and float(lap.duration) >= 60 and lap.average_heart_rate
        ]

    def _interval_completion(self, activity: Activity) -> Optional[float]:
        laps = self._work_laps(activity)
        if len(laps) < 2:
            return None
        durations = [float(lap.duration) for lap in laps if lap.duration]
        if not durations:
            return None
        target = durations[0]
        completed = sum(1 for d in durations if d >= target * 0.9)
        return completed / len(durations) * 100.0

    @staticmethod
    def _pstdev(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean_v = sum(values) / len(values)
        return (sum((v - mean_v) ** 2 for v in values) / len(values)) ** 0.5

    @staticmethod
    def _interpret(score: float, flags: List[str], session_type: str) -> str:
        if score >= 80:
            base = f"Strong {session_type} execution"
        elif score >= 60:
            base = f"Acceptable {session_type} execution"
        else:
            base = f"Compromised {session_type} execution"
        if flags:
            return f"{base}; flags: {', '.join(flags)}"
        return base

    @staticmethod
    def _empty(session_type: str, reason: str) -> Dict[str, Any]:
        return {
            "session_type": session_type,
            "quality_score": None,
            "confidence": 0.0,
            "components": {},
            "flags": [reason],
            "interpretation": reason,
            "comparability_note": "Scores are not comparable across session types.",
        }
