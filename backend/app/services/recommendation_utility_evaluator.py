"""Evaluate recommendations on outcomes — imitation is not the primary metric."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .ppap_metrics_service import PpapMetricsService


class RecommendationUtilityEvaluator:
    """
    Separates imitation (did we match the actual session type?) from outcome utility.

    Counterfactual claims are labeled as such — never presented as observed truth.
    """

    SESSION_FAMILIES = {
        "easy_run": {"easy_aerobic", "recovery_run", "steady", "long_aerobic", "easy_run"},
        "recovery_run": {"recovery_run", "easy_aerobic", "recovery_run"},
        "long_run": {"long_aerobic", "easy_aerobic", "long_run"},
        "threshold": {"threshold", "tempo", "steady"},
        "vo2_intervals": {"vo2_intervals", "anaerobic"},
        "race_pace": {"race", "threshold", "tempo", "race_pace"},
        "rest": {"rest"},
    }

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)

    def evaluate(
        self,
        *,
        recommended_type: Optional[str],
        actual_type: Optional[str],
        as_of: date,
        decision_confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        imitation = self.imitation_score(recommended_type, actual_type)
        short_term = self._short_term_utility(as_of)
        medium_term = self._medium_term_utility(as_of)
        recovery_cost = self._recovery_cost(as_of, recommended_type)
        # Plausible better: not a match, but subsequent markers look favorable for the rec.
        plausible_better = (
            imitation is False
            and short_term is not None
            and short_term >= 0.55
            and (recovery_cost is None or recovery_cost <= 0.55)
        )
        conf = decision_confidence
        if conf is None:
            conf = 0.5
            if short_term is not None:
                conf = min(0.85, 0.35 + 0.5 * short_term)
        return {
            "imitation": imitation,
            "short_term_utility": short_term,
            "medium_term_utility": medium_term,
            "recovery_cost": recovery_cost,
            "confidence": round(float(conf), 3),
            "plausible_better_despite_mismatch": plausible_better,
            "note": "Utility uses observed post-recommendation markers; not a causal counterfactual claim.",
            "evaluation_kind": "observational_outcome",
        }

    def imitation_score(
        self,
        recommended: Optional[str],
        actual: Optional[str],
    ) -> Optional[bool]:
        if recommended is None or actual is None:
            return None
        family = self.SESSION_FAMILIES.get(recommended, {recommended})
        return actual in family or actual == recommended

    def _short_term_utility(self, as_of: date) -> Optional[float]:
        """0–1 from session quality + next-day HRV/RHR when available."""
        scores = []
        for offset in (0, 1):
            day = as_of + timedelta(days=offset)
            q = self._safe_quality(day)
            if q is not None:
                scores.append(q)
        hrv = self._ppap.get_hrv_delta_pct(as_of + timedelta(days=1))
        rhr = self._ppap.get_rhr_delta_bpm(as_of + timedelta(days=1))
        missing = []
        if hrv is None:
            missing.append("hrv")
        else:
            # Missing ≠ negative; only score when present.
            scores.append(max(0.0, min(1.0, 0.5 + (-hrv) / 40.0)))
        if rhr is None:
            missing.append("rhr")
        else:
            scores.append(max(0.0, min(1.0, 0.5 - rhr / 20.0)))
        if not scores:
            return None
        return round(sum(scores) / len(scores), 3)

    def _medium_term_utility(self, as_of: date) -> Optional[float]:
        """Rough 7–21d trend from TSB recovery and CTL stability — observational only."""
        tsb_now = self._ppap.get_tsb(as_of)
        tsb_later = self._ppap.get_tsb(as_of + timedelta(days=14))
        ctl_now = self._ppap.get_ctl(as_of)
        ctl_later = self._ppap.get_ctl(as_of + timedelta(days=21))
        parts = []
        if tsb_now is not None and tsb_later is not None:
            # Moving toward fresher TSB is positive if we were fatigued.
            delta = tsb_later - tsb_now
            parts.append(max(0.0, min(1.0, 0.5 + delta / 30.0)))
        if ctl_now is not None and ctl_later is not None and ctl_now > 0:
            growth = (ctl_later - ctl_now) / max(ctl_now, 1.0)
            parts.append(max(0.0, min(1.0, 0.5 + growth)))
        if not parts:
            return None
        return round(sum(parts) / len(parts), 3)

    def _recovery_cost(self, as_of: date, recommended: Optional[str]) -> Optional[float]:
        hard = recommended in {"threshold", "vo2_intervals", "race_pace"}
        tsb = self._ppap.get_tsb(as_of + timedelta(days=2))
        hrv = self._ppap.get_hrv_delta_pct(as_of + timedelta(days=1))
        cost = 0.35 if hard else 0.2
        if tsb is not None and tsb < -20:
            cost += 0.25
        if hrv is not None and hrv < -10:
            cost += 0.2
        # Missing HRV does not increase cost (missingness-aware).
        return round(min(1.0, cost), 3)

    def _safe_quality(self, day: date) -> Optional[float]:
        # SessionQualityService scores activities, not calendar days — omit if unavailable.
        return None
