"""Finn historisk sammenlignbare økter og percentile vs personlig baseline."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity, ActivityRouteFingerprint
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .session_classifier_service import SessionClassifierService
from .session_quality_service import SessionQualityService

DISTANCE_TOLERANCE_PCT = 0.15
DURATION_TOLERANCE_PCT = 0.20
TEMP_TOLERANCE_C = 8.0
ELEVATION_TOLERANCE_M = 80.0
HR_TOLERANCE_BPM = 12.0
MIN_COMPARABLE = 3


class ComparableSessionService:
    """Matcher økter på rute, distanse, varighet, type, vær og intensitet."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
    ):
        self.db = db
        self.storage = storage
        self._classifier = SessionClassifierService(db, storage)
        self._quality = SessionQualityService(db, storage)

    def find_comparable_sessions(
        self,
        activity_id: str,
        *,
        limit: int = 10,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        activity = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter_by(activity_id=str(activity_id))
            .first()
        )
        if activity is None or not is_running_activity(activity, include_treadmill=include_treadmill):
            return {"status": "not_found", "activity_id": activity_id, "matches": []}

        classification = self._classifier.classify_activity(
            activity,
            include_treadmill=include_treadmill,
        )
        session_type = classification.get("session_type", "unknown")
        fingerprint = (
            self.db.query(ActivityRouteFingerprint)
            .filter_by(activity_id=str(activity.activity_id))
            .first()
        )

        candidates = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(Activity.activity_id != str(activity.activity_id))
            .order_by(Activity.start_time.desc())
            .limit(500)
            .all()
        )

        scored: List[Tuple[float, Activity, Dict[str, Any]]] = []
        for candidate in candidates:
            if not is_running_activity(candidate, include_treadmill=include_treadmill):
                continue
            match = self._score_similarity(activity, candidate, session_type, fingerprint)
            if match["similarity"] >= 0.45:
                scored.append((match["similarity"], candidate, match))

        scored.sort(key=lambda item: item[0], reverse=True)
        matches = []
        for similarity, candidate, details in scored[:limit]:
            quality = self._quality.evaluate(candidate, include_treadmill=include_treadmill)
            matches.append(
                {
                    "activity_id": candidate.activity_id,
                    "activity_name": candidate.activity_name,
                    "date": candidate.start_time.date().isoformat() if candidate.start_time else None,
                    "similarity": round(similarity, 3),
                    "match_reasons": details.get("reasons", []),
                    "distance_m": candidate.distance,
                    "duration_s": candidate.duration,
                    "average_heart_rate": candidate.average_heart_rate,
                    "temperature": candidate.temperature,
                    "quality_score": quality.get("quality_score"),
                    "session_type": quality.get("session_type"),
                }
            )

        return {
            "status": "ok",
            "activity_id": str(activity.activity_id),
            "session_type": session_type,
            "matches": matches,
            "count": len(matches),
        }

    def compare_to_personal_baseline(
        self,
        activity_id: str,
        *,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        comparable = self.find_comparable_sessions(
            activity_id,
            limit=25,
            include_treadmill=include_treadmill,
        )
        if comparable.get("status") != "ok":
            return comparable

        activity = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter_by(activity_id=str(activity_id))
            .first()
        )
        current_quality = self._quality.evaluate(activity, include_treadmill=include_treadmill)
        current_score = current_quality.get("quality_score")

        peer_scores = [
            m["quality_score"]
            for m in comparable.get("matches", [])
            if m.get("quality_score") is not None
        ]

        percentile = None
        rank = None
        if current_score is not None and peer_scores:
            better = sum(1 for s in peer_scores if s < current_score)
            percentile = round(better / len(peer_scores) * 100.0, 1)
            rank = len(peer_scores) - better + 1

        return {
            "status": "ok",
            "activity_id": str(activity_id),
            "current_quality": current_quality,
            "comparable_count": len(peer_scores),
            "percentile_vs_comparable": percentile,
            "rank": rank,
            "baseline_median_quality": (
                round(sorted(peer_scores)[len(peer_scores) // 2], 1) if peer_scores else None
            ),
            "matches": comparable.get("matches", [])[:10],
            "limitations": (
                []
                if len(peer_scores) >= MIN_COMPARABLE
                else ["few_comparable_sessions — percentile uncertain"]
            ),
        }

    def _score_similarity(
        self,
        reference: Activity,
        candidate: Activity,
        session_type: str,
        fingerprint: Optional[ActivityRouteFingerprint],
    ) -> Dict[str, Any]:
        score = 0.0
        weight = 0.0
        reasons: List[str] = []

        cand_class = self._classifier.classify_activity(candidate)
        if cand_class.get("session_type") == session_type:
            score += 0.25
            reasons.append("same_session_type")
        weight += 0.25

        if fingerprint and fingerprint.route_group_key:
            cand_fp = (
                self.db.query(ActivityRouteFingerprint)
                .filter_by(activity_id=str(candidate.activity_id))
                .first()
            )
            if cand_fp and cand_fp.route_group_key == fingerprint.route_group_key:
                score += 0.30
                reasons.append("same_route")
            weight += 0.30

        if reference.distance and candidate.distance and reference.distance > 0:
            ratio = abs(float(candidate.distance) - float(reference.distance)) / float(reference.distance)
            if ratio <= DISTANCE_TOLERANCE_PCT:
                score += 0.15 * (1 - ratio / DISTANCE_TOLERANCE_PCT)
                reasons.append("similar_distance")
            weight += 0.15

        if reference.duration and candidate.duration and reference.duration > 0:
            ratio = abs(float(candidate.duration) - float(reference.duration)) / float(reference.duration)
            if ratio <= DURATION_TOLERANCE_PCT:
                score += 0.10 * (1 - ratio / DURATION_TOLERANCE_PCT)
                reasons.append("similar_duration")
            weight += 0.10

        if reference.temperature is not None and candidate.temperature is not None:
            delta = abs(float(candidate.temperature) - float(reference.temperature))
            if delta <= TEMP_TOLERANCE_C:
                score += 0.08 * (1 - delta / TEMP_TOLERANCE_C)
                reasons.append("similar_temperature")
            weight += 0.08

        if reference.total_ascent is not None and candidate.total_ascent is not None:
            delta = abs(float(candidate.total_ascent) - float(reference.total_ascent))
            if delta <= ELEVATION_TOLERANCE_M:
                score += 0.07 * (1 - delta / ELEVATION_TOLERANCE_M)
                reasons.append("similar_elevation")
            weight += 0.07

        if reference.average_heart_rate and candidate.average_heart_rate:
            delta = abs(float(candidate.average_heart_rate) - float(reference.average_heart_rate))
            if delta <= HR_TOLERANCE_BPM:
                score += 0.05 * (1 - delta / HR_TOLERANCE_BPM)
                reasons.append("similar_hr_intensity")
            weight += 0.05

        similarity = score / weight if weight > 0 else 0.0
        return {"similarity": similarity, "reasons": reasons}
