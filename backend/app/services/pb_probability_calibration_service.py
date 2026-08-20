"""Historisk kalibrering av PB-sannsynlighet fra readiness vs faktiske PB-er."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..database.models.summaries import PersonalRecord
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .coaching_decision_metrics_service import CoachingDecisionMetricsService
from .ppap_metrics_service import PpapMetricsService
from .session_classifier_service import RACE_NAME_PATTERN, SessionClassifierService

EVENT_DISTANCE_M: Dict[str, Tuple[float, float]] = {
    "5k": (4800.0, 5200.0),
    "10k": (9800.0, 10300.0),
    "hm": (20500.0, 22000.0),
    "marathon": (41500.0, 43000.0),
}

READINESS_BINS: Tuple[Tuple[float, float], ...] = (
    (0.0, 45.0),
    (45.0, 60.0),
    (60.0, 75.0),
    (75.0, 85.0),
    (85.0, 101.0),
)

MIN_CALIBRATION_SAMPLES = 8
MIN_BIN_SAMPLES = 2


@dataclass
class _RaceObservation:
    event: str
    race_date: date
    readiness_score: float
    was_pb: bool
    activity_id: str


class PbProbabilityCalibrationService:
    """Kalibrerer readiness-score til empirisk PB-rate per distanse."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._decision = CoachingDecisionMetricsService(self.db, self._ppap)
        self._classifier = SessionClassifierService(db, storage)

    def get_calibrated_probability(
        self,
        day: date,
        distance: str,
        *,
        lookback_days: int = 730,
    ) -> Dict[str, Any]:
        readiness = self._decision.get_pb_readiness_score(day, distance)
        if readiness is None:
            return {
                "distance": distance,
                "date": day.isoformat(),
                "probability_pct": None,
                "method": "insufficient_readiness_data",
                "confidence": 0.0,
                "sample_count": 0,
            }

        calibration = self.build_calibration(distance, lookback_days=lookback_days, end_date=day)
        bins = calibration.get("bins", [])
        prob = self._lookup_bin_probability(float(readiness), bins)
        heuristic = float(readiness)

        if prob is None:
            return {
                "distance": distance,
                "date": day.isoformat(),
                "probability_pct": round(heuristic * 0.6, 1),
                "readiness_score": readiness,
                "method": "heuristic_scaled_fallback",
                "confidence": 0.25,
                "sample_count": calibration.get("sample_count", 0),
                "limitations": [
                    "insufficient_historical_races_for_calibration",
                    "scaled_from_readiness_heuristic_not_true_probability",
                ],
                "calibration": calibration,
            }

        return {
            "distance": distance,
            "date": day.isoformat(),
            "probability_pct": prob,
            "readiness_score": readiness,
            "method": "historical_calibration",
            "confidence": calibration.get("confidence", 0.5),
            "sample_count": calibration.get("sample_count", 0),
            "bin_used": self._bin_label(float(readiness)),
            "calibration": calibration,
            "limitations": calibration.get("limitations", []),
        }

    def build_calibration(
        self,
        distance: str,
        *,
        lookback_days: int = 730,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        end = end_date or date.today()
        start = end - timedelta(days=lookback_days)
        observations = self._collect_observations(distance, start, end)

        if len(observations) < MIN_CALIBRATION_SAMPLES:
            return {
                "distance": distance,
                "sample_count": len(observations),
                "confidence": 0.0,
                "bins": [],
                "limitations": [f"need_at_least_{MIN_CALIBRATION_SAMPLES}_race_observations"],
            }

        bins: List[Dict[str, Any]] = []
        for low, high in READINESS_BINS:
            in_bin = [o for o in observations if low <= o.readiness_score < high]
            pb_count = sum(1 for o in in_bin if o.was_pb)
            rate = (pb_count / len(in_bin) * 100.0) if in_bin else None
            bins.append(
                {
                    "readiness_min": low,
                    "readiness_max": high,
                    "sample_count": len(in_bin),
                    "pb_count": pb_count,
                    "pb_rate_pct": round(rate, 1) if rate is not None else None,
                }
            )

        valid_bins = sum(1 for b in bins if b["sample_count"] >= MIN_BIN_SAMPLES)
        confidence = min(0.9, valid_bins / len(READINESS_BINS) * (len(observations) / 20.0))

        return {
            "distance": distance,
            "lookback_days": lookback_days,
            "sample_count": len(observations),
            "confidence": round(confidence, 2),
            "bins": bins,
            "overall_pb_rate_pct": round(
                sum(1 for o in observations if o.was_pb) / len(observations) * 100.0,
                1,
            ),
            "limitations": [] if len(observations) >= MIN_CALIBRATION_SAMPLES else ["sparse_data"],
        }

    def _collect_observations(
        self,
        distance: str,
        start: date,
        end: date,
    ) -> List[_RaceObservation]:
        bounds = EVENT_DISTANCE_M.get(distance)
        if not bounds:
            return []

        min_d, max_d = bounds
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                    Activity.distance.isnot(None),
                    Activity.distance >= min_d,
                    Activity.distance <= max_d,
                    Activity.duration.isnot(None),
                    Activity.duration > 0,
                )
            )
            .order_by(Activity.start_time)
            .all()
        )

        observations: List[_RaceObservation] = []
        best_time: Optional[float] = None

        for activity in activities:
            if not is_running_activity(activity) or not activity.start_time:
                continue
            if not self._is_race_activity(activity):
                continue

            race_day = activity.start_time.date()
            as_of = race_day - timedelta(days=1)
            readiness = self._decision.get_pb_readiness_score(as_of, distance)
            if readiness is None:
                continue

            duration = float(activity.duration)
            was_pb = best_time is None or duration < best_time
            if was_pb:
                best_time = duration

            observations.append(
                _RaceObservation(
                    event=distance,
                    race_date=race_day,
                    readiness_score=float(readiness),
                    was_pb=was_pb,
                    activity_id=str(activity.activity_id),
                )
            )

        pr_observations = self._observations_from_personal_records(distance, start, end)
        seen_ids = {o.activity_id for o in observations}
        for obs in pr_observations:
            if obs.activity_id not in seen_ids:
                observations.append(obs)

        observations.sort(key=lambda o: o.race_date)
        return observations

    def _observations_from_personal_records(
        self,
        distance: str,
        start: date,
        end: date,
    ) -> List[_RaceObservation]:
        record_type_map = {
            "5k": "5k",
            "10k": "10k",
            "hm": "half_marathon",
            "marathon": "marathon",
        }
        record_type = record_type_map.get(distance)
        if not record_type:
            return []

        rows = (
            self.db.query(PersonalRecord)
            .filter(
                and_(
                    PersonalRecord.record_type == record_type,
                    PersonalRecord.achieved_date >= start,
                    PersonalRecord.achieved_date <= end,
                )
            )
            .order_by(PersonalRecord.achieved_date)
            .all()
        )

        observations: List[_RaceObservation] = []
        for row in rows:
            if not row.achieved_date:
                continue
            as_of = row.achieved_date - timedelta(days=1)
            readiness = self._decision.get_pb_readiness_score(as_of, distance)
            if readiness is None:
                continue
            observations.append(
                _RaceObservation(
                    event=distance,
                    race_date=row.achieved_date,
                    readiness_score=float(readiness),
                    was_pb=True,
                    activity_id=str(row.activity_id or f"pr-{row.id}"),
                )
            )
        return observations

    def _is_race_activity(self, activity: Activity) -> bool:
        if activity.activity_name and RACE_NAME_PATTERN.search(activity.activity_name):
            return True
        classification = self._classifier.classify_activity(activity)
        return classification.get("session_type") == "race"

    def _lookup_bin_probability(
        self,
        readiness: float,
        bins: List[Dict[str, Any]],
    ) -> Optional[float]:
        for bin_entry in bins:
            low = float(bin_entry["readiness_min"])
            high = float(bin_entry["readiness_max"])
            if low <= readiness < high:
                if bin_entry.get("sample_count", 0) < MIN_BIN_SAMPLES:
                    return None
                return bin_entry.get("pb_rate_pct")
        return None

    @staticmethod
    def _bin_label(readiness: float) -> str:
        for low, high in READINESS_BINS:
            if low <= readiness < high:
                return f"{int(low)}-{int(high)}"
        return "unknown"
