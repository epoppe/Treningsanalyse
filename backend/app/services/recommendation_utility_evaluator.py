"""Evaluate recommendations on outcomes — imitation is not the primary metric."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .coaching_config import DEFAULT_RECOVERY_COST
from .outcome_maturity import (
    EVALUATED,
    MEDIUM_TERM_LAG_DAYS,
    SHORT_TERM_LAG_DAYS,
    medium_term_maturity,
    short_term_maturity,
    window_closed,
)
from .ppap_metrics_service import PpapMetricsService

# get_hrv_delta_pct is in percentage points. ±20 points maps onto the 0–1 bounds.
_HRV_UTILITY_SPAN_PCT = 40.0
_RHR_UTILITY_SPAN_BPM = 20.0

# Aliases into the documented default recovery envelope (days), not observed markers.
_EXPECTED_COST_ALIASES = {
    "recovery_run": "easy_run",
    "long_run": "easy_run",
    "race_pace": "threshold",
    "race": "race",
}


def hrv_component_score(hrv_delta_pct: Optional[float]) -> Optional[float]:
    """Map HRV percent-vs-baseline onto 0–1 utility.

    Positive delta (HRV above baseline) raises the score. Negative delta lowers it.
    None stays None — missing HRV is not negative physiology.
    """
    if hrv_delta_pct is None:
        return None
    return round(max(0.0, min(1.0, 0.5 + float(hrv_delta_pct) / _HRV_UTILITY_SPAN_PCT)), 3)


def expected_recovery_cost_value(recommended_type: Optional[str]) -> float:
    """What the default envelope expected the *recommended* session to cost.

    This does not look at the session that was actually performed.
    Scale is 0–1 from the midpoint of the documented recovery-day range / 7.
    """
    key = recommended_type or ""
    key = _EXPECTED_COST_ALIASES.get(key, key)
    bounds = DEFAULT_RECOVERY_COST.get(key, [1, 2])
    midpoint = (float(bounds[0]) + float(bounds[1])) / 2.0
    return round(min(1.0, midpoint / 7.0), 3)


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
        actual_load: Optional[float] = None,
        today: Optional[date] = None,
    ) -> Dict[str, Any]:
        today = today or date.today()
        imitation = self.imitation_score(recommended_type, actual_type)
        short_term, short_status = self._short_term_utility(as_of, today=today)
        medium_term, medium_status = self._medium_term_utility(as_of, today=today)
        expected = self._expected_recovery_cost(recommended_type)
        observed = self._observed_recovery_response(
            as_of,
            today=today,
            actual_type=actual_type,
            actual_load=actual_load,
        )
        observed_cost = observed.get("value")
        # Plausible better: not a match, but subsequent *observed* markers look favorable.
        plausible_better = (
            imitation is False
            and short_status == EVALUATED
            and short_term is not None
            and short_term >= 0.55
            and (observed_cost is None or observed_cost <= 0.55)
        )
        conf = decision_confidence
        if conf is None:
            conf = 0.5
            if short_term is not None and short_status == EVALUATED:
                conf = min(0.85, 0.35 + 0.5 * short_term)
        return {
            "imitation": imitation,
            "short_term_utility": short_term,
            "short_term_maturity": short_status,
            "medium_term_utility": medium_term,
            "medium_term_maturity": medium_status,
            "expected_recovery_cost": expected,
            "observed_recovery_response": observed,
            # Numeric alias of the observed cost only. Never the expected envelope.
            "recovery_cost": observed_cost,
            "confidence": round(float(conf), 3),
            "plausible_better_despite_mismatch": plausible_better,
            "note": (
                "Utility uses observed post-session markers; not a causal counterfactual claim. "
                "expected_recovery_cost is the default envelope for the recommended type. "
                "observed_recovery_response is not a causal effect of that recommendation."
            ),
            "evaluation_kind": "observational_outcome",
            "maturity": {
                "short_term": short_status,
                "medium_term": medium_status,
                "observed_recovery": observed.get("maturity_status"),
            },
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

    def _short_term_utility(self, as_of: date, *, today: date) -> tuple[Optional[float], str]:
        """0–1 from session quality + next-day HRV/RHR when the window has closed."""
        hrv = self._ppap.get_hrv_delta_pct(as_of + timedelta(days=1))
        rhr = self._ppap.get_rhr_delta_bpm(as_of + timedelta(days=1))
        scores = []
        for offset in (0, 1):
            q = self._safe_quality(as_of + timedelta(days=offset))
            if q is not None:
                scores.append(q)
        hrv_score = hrv_component_score(hrv)
        if hrv_score is not None:
            scores.append(hrv_score)
        if rhr is not None:
            # Positive RHR delta (higher than baseline) lowers utility.
            scores.append(max(0.0, min(1.0, 0.5 - float(rhr) / _RHR_UTILITY_SPAN_BPM)))
        value = round(sum(scores) / len(scores), 3) if scores else None
        # Do not emit a score until the 24–48h window has closed, even if a
        # partial marker already exists. Pending is not a low utility.
        if not window_closed(as_of, today, SHORT_TERM_LAG_DAYS):
            return None, short_term_maturity(as_of, today, has_value=False)
        status = short_term_maturity(as_of, today, has_value=value is not None)
        return (value if status == EVALUATED else None), status

    def _medium_term_utility(self, as_of: date, *, today: date) -> tuple[Optional[float], str]:
        """Rough 7–21d trend from TSB recovery and CTL stability — observational only."""
        tsb_now = self._ppap.get_tsb(as_of)
        tsb_later = self._ppap.get_tsb(as_of + timedelta(days=14))
        ctl_now = self._ppap.get_ctl(as_of)
        ctl_later = self._ppap.get_ctl(as_of + timedelta(days=21))
        parts = []
        if tsb_now is not None and tsb_later is not None:
            delta = tsb_later - tsb_now
            parts.append(max(0.0, min(1.0, 0.5 + delta / 30.0)))
        if ctl_now is not None and ctl_later is not None and ctl_now > 0:
            growth = (ctl_later - ctl_now) / max(ctl_now, 1.0)
            parts.append(max(0.0, min(1.0, 0.5 + growth)))
        value = round(sum(parts) / len(parts), 3) if parts else None
        if not window_closed(as_of, today, MEDIUM_TERM_LAG_DAYS):
            return None, medium_term_maturity(as_of, today, has_value=False)
        status = medium_term_maturity(as_of, today, has_value=value is not None)
        return (value if status == EVALUATED else None), status

    def _expected_recovery_cost(self, recommended: Optional[str]) -> Dict[str, Any]:
        return {
            "value": expected_recovery_cost_value(recommended),
            "workout_type": recommended,
            "source": "default_envelope",
            "label": "expected_recovery_cost",
            "note": "Expected cost of the recommended workout type. Not the observed response.",
        }

    def _observed_recovery_response(
        self,
        as_of: date,
        *,
        today: date,
        actual_type: Optional[str],
        actual_load: Optional[float],
    ) -> Dict[str, Any]:
        """Physiological markers after the actual session. Not a causal effect.

        The recommended type is intentionally unused. An easy_run recommendation
        followed by vo2 intervals must not be scored as if the easy run happened.
        Missing HRV/RHR/TSB does not invent a cost.
        """
        hrv = self._ppap.get_hrv_delta_pct(as_of + timedelta(days=1))
        rhr = self._ppap.get_rhr_delta_bpm(as_of + timedelta(days=1))
        tsb = self._ppap.get_tsb(as_of + timedelta(days=2))
        parts = []
        if hrv is not None:
            # Higher HRV than baseline lowers observed recovery stress.
            parts.append(max(0.0, min(1.0, 0.5 - float(hrv) / _HRV_UTILITY_SPAN_PCT)))
        if rhr is not None:
            parts.append(max(0.0, min(1.0, 0.5 + float(rhr) / _RHR_UTILITY_SPAN_BPM)))
        if tsb is not None:
            parts.append(max(0.0, min(1.0, 0.5 - float(tsb) / 40.0)))
        value = round(sum(parts) / len(parts), 3) if parts else None
        if not window_closed(as_of, today, SHORT_TERM_LAG_DAYS):
            status = short_term_maturity(as_of, today, has_value=False)
            value = None
        else:
            status = short_term_maturity(as_of, today, has_value=value is not None)
            if status != EVALUATED:
                value = None
        return {
            "value": value,
            "actual_type": actual_type,
            "actual_load": actual_load,
            "inputs_present": {
                "hrv_delta_pct": hrv is not None,
                "rhr_delta_bpm": rhr is not None,
                "tsb": tsb is not None,
                "actual_load": actual_load is not None,
            },
            "maturity_status": status,
            "label": "observed_recovery_response",
            "evaluation_kind": "observational_outcome",
            "note": (
                "Observational markers after the actual session. "
                "Not a causal effect of the recommendation, and not an adherence score."
            ),
        }

    def _safe_quality(self, day: date) -> Optional[float]:
        # SessionQualityService scores activities, not calendar days — omit if unavailable.
        return None
