"""One data-quality snapshot for the coaching evidence API and MCP.

Freshness and source coverage come from DataLatencyMonitor and
DataQualityTrendService. Observation counts come from the canonical
prospective observations already resolved by the caller. This module does
not score outcomes again and does not invent a third coverage formula.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import RecommendationRecord
from .canonical_prospective_observation import CanonicalProspectiveObservationService
from .coaching_operational_monitors import DataLatencyMonitor, DataQualityTrendService
from .outcome_maturity import INCOMPLETE_DATA
from .recommendation_utility_evaluator import RecommendationUtilityEvaluator

SCHEMA = "data-quality-snapshot-1"
COVERAGE_SHIFT_THRESHOLD = 0.25
_FEEDBACK_GROUPS = {
    "easy_run": "easy",
    "recovery_run": "easy",
    "long_run": "long",
    "threshold": "threshold",
    "tempo": "threshold",
    "vo2_intervals": "intervals",
    "race_pace": "race",
    "race": "race",
}
_GROUP_ORDER = ("easy", "long", "threshold", "intervals", "race")


class DataQualitySnapshotService:
    def __init__(self, db: Session):
        self.db = db

    def build(self, *, end: date, window_days: int = 90) -> Dict[str, Any]:
        if window_days < 1 or window_days > 365:
            raise ValueError("window_days must be between 1 and 365")
        start = end - timedelta(days=window_days)
        observations = CanonicalProspectiveObservationService(self.db).resolve(
            start=start,
            end=end,
            today=end,
        )
        evaluator = RecommendationUtilityEvaluator(self.db)
        utilities = {
            row["recommendation_id"]: evaluator.evaluate_for_observation(row, today=end)
            for row in observations
        }
        return self.from_observations(
            observations=observations,
            utilities=utilities,
            start=start,
            end=end,
            window_days=window_days,
        )

    def from_observations(
        self,
        *,
        observations: List[Dict[str, Any]],
        utilities: Dict[int, Dict[str, Any]],
        start: date,
        end: date,
        window_days: int,
    ) -> Dict[str, Any]:
        latency = DataLatencyMonitor().assess(self.db, as_of=_as_of(end))
        trend_days = min(28, window_days)
        trend = DataQualityTrendService().assess(self.db, end=end, window_days=trend_days)
        recent_days = min(14, trend_days)
        recent = DataQualityTrendService().assess(self.db, end=end, window_days=recent_days)
        prior = DataQualityTrendService().assess(
            self.db,
            end=end - timedelta(days=recent_days),
            window_days=recent_days,
        )
        counts = _observation_counts(observations, utilities)
        excluded = _excluded_counts(self.db, observations, start=start, end=end)
        matching = _matching(observations)
        feedback = _feedback(observations)
        return {
            "schema": SCHEMA,
            "as_of": end.isoformat(),
            "window": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "window_days": window_days,
            },
            "freshness": {
                "last_sync_at": latency.get("last_sync_at"),
                "last_activity_at": latency.get("last_activity_at"),
                "last_sleep_date": latency.get("last_sleep_date"),
                "source_latency_hours": latency.get("source_latency_hours"),
                "sync_latency_hours": latency.get("sync_latency_hours"),
                "stale_local_despite_source": bool(latency.get("stale_local_despite_source")),
            },
            "source_coverage": {
                "hrv": trend.get("hrv_coverage"),
                "sleep": trend.get("sleep_coverage"),
                "rhr": trend.get("rhr_coverage"),
                "tss_epoc_activity_share": trend.get("tss_epoc_activity_share"),
                "activity_count": trend.get("activity_count"),
                "sample_days": trend.get("sample_count"),
            },
            "missing_sources": _missing_sources(trend),
            "coverage_shifts": _coverage_shifts(recent, prior),
            "observations": {**counts, "excluded": excluded["total"], "excluded_detail": excluded},
            "execution_matching": matching,
            "feedback_coverage": feedback["coverage"],
            "feedback_by_group": feedback["by_group"],
            "observation_note": (
                "pending and evaluated describe execution maturity on canonical observations. "
                "incomplete is a closed short-term window without markers and can overlap an "
                "evaluated execution. excluded rows are shadow, superseded, or same-day duplicates "
                "and are not part of the canonical count."
            ),
            "sources": [
                "DataLatencyMonitor",
                "DataQualityTrendService",
                "CanonicalProspectiveObservation",
            ],
        }


def _as_of(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, 0)


def _observation_counts(
    observations: List[Dict[str, Any]],
    utilities: Dict[int, Dict[str, Any]],
) -> Dict[str, int]:
    pending = evaluated = incomplete = 0
    for row in observations:
        status = row.get("observation_status")
        if status == "pending":
            pending += 1
        elif status == "evaluated":
            evaluated += 1
        utility = utilities.get(row["recommendation_id"]) or {}
        if utility.get("short_term_maturity") == INCOMPLETE_DATA or status == INCOMPLETE_DATA:
            incomplete += 1
    return {"pending": pending, "evaluated": evaluated, "incomplete": incomplete}


def _excluded_counts(
    db: Session,
    observations: List[Dict[str, Any]],
    *,
    start: date,
    end: date,
) -> Dict[str, int]:
    superseded = sum(max(0, int(row.get("supersede_chain_length") or 1) - 1) for row in observations)
    same_day = sum(len(row.get("same_day_excluded_ids") or []) for row in observations)
    shadow = (
        db.query(RecommendationRecord)
        .filter(
            RecommendationRecord.is_shadow.is_(True),
            RecommendationRecord.as_of_date >= start,
            RecommendationRecord.as_of_date <= end,
        )
        .count()
    )
    return {
        "shadow": int(shadow),
        "superseded": superseded,
        "same_day_unlinked": same_day,
        "total": int(shadow) + superseded + same_day,
    }


def _matching(observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    explicit = sum(1 for row in observations if row.get("match_source") == "explicit_execution")
    heuristic = sum(1 for row in observations if row.get("match_source") == "legacy_heuristic")
    matched = explicit + heuristic
    return {
        "explicit": explicit,
        "heuristic": heuristic,
        "explicit_share": round(explicit / matched, 3) if matched else None,
    }


def _feedback(observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    groups = {name: {"recommendations": 0, "with_feedback": 0, "coverage": None} for name in _GROUP_ORDER}
    with_feedback = 0
    for row in observations:
        if row.get("subjective_feedback"):
            with_feedback += 1
        group = _FEEDBACK_GROUPS.get(row.get("recommended_workout_type") or "")
        if group is None:
            continue
        groups[group]["recommendations"] += 1
        if row.get("subjective_feedback"):
            groups[group]["with_feedback"] += 1
    for bucket in groups.values():
        count = bucket["recommendations"]
        bucket["coverage"] = round(bucket["with_feedback"] / count, 3) if count else None
    total = len(observations)
    return {
        "coverage": round(with_feedback / total, 3) if total else None,
        "by_group": groups,
    }


def _missing_sources(trend: Dict[str, Any]) -> List[Dict[str, str]]:
    missing: List[Dict[str, str]] = []
    labels = (
        ("hrv_coverage", "hrv"),
        ("sleep_coverage", "sleep"),
        ("rhr_coverage", "rhr"),
    )
    for key, name in labels:
        if trend.get(key) == 0:
            missing.append({"source": name, "reason": "no rows in the coverage window"})
    if not trend.get("activity_count"):
        missing.append({"source": "activities", "reason": "no activities in the coverage window"})
    return missing


def _coverage_shifts(recent: Dict[str, Any], prior: Dict[str, Any]) -> List[Dict[str, Any]]:
    shifts = []
    for key, name in (("hrv_coverage", "hrv"), ("sleep_coverage", "sleep"), ("rhr_coverage", "rhr")):
        current = recent.get(key)
        previous = prior.get(key)
        if current is None or previous is None:
            continue
        delta = round(float(current) - float(previous), 3)
        if abs(delta) >= COVERAGE_SHIFT_THRESHOLD:
            shifts.append({"source": name, "recent": current, "prior": previous, "delta": delta})
    return shifts
