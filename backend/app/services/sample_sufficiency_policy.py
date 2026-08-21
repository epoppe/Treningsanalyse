"""Canonical sample sufficiency — one policy for personalization evidence floors."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence


class SufficiencyLevel(str, Enum):
    INSUFFICIENT = "INSUFFICIENT"
    EMERGING = "EMERGING"
    SUPPORTED = "SUPPORTED"
    STRONG = "STRONG"


# Domain → minimum sample counts (raw). Temporal spread adjusts effective n.
DOMAIN_FLOORS: Dict[str, Dict[str, int]] = {
    "recovery_cost": {"emerging": 8, "supported": 20, "strong": 40},
    "workout_effectiveness": {"emerging": 10, "supported": 25, "strong": 50},
    "dose_response": {"emerging": 12, "supported": 30, "strong": 60},
    "taper_personalization": {"emerging": 6, "supported": 15, "strong": 30},
    "concept_drift": {"emerging": 4, "supported": 8, "strong": 16},
    "shadow_comparison": {"emerging": 15, "supported": 30, "strong": 60},
    "confidence_calibration": {"emerging": 20, "supported": 40, "strong": 80},
    "load_progression": {"emerging": 10, "supported": 25, "strong": 50},
    "execution_patterns": {"emerging": 8, "supported": 20, "strong": 40},
    "default": {"emerging": 8, "supported": 20, "strong": 40},
}


class SampleSufficiencyPolicy:
    """
    10 observations in one week ≠ 10 observations across 4 months.

    effective_sample_count accounts for recency decay and temporal spread.
    """

    MIN_SPREAD_DAYS_FOR_FULL_CREDIT = 56  # ~8 weeks
    CONCENTRATION_PENALTY = 0.45  # applied when all samples fall in a short window

    def assess(
        self,
        *,
        domain: str,
        sample_count: int,
        observation_dates: Optional[Sequence[date]] = None,
        as_of: Optional[date] = None,
        data_quality: Optional[float] = None,
    ) -> Dict[str, Any]:
        as_of = as_of or date.today()
        floors = DOMAIN_FLOORS.get(domain) or DOMAIN_FLOORS["default"]
        n = max(0, int(sample_count))
        spread_days, concentration_ratio = self._temporal_stats(observation_dates, as_of)

        effective = float(n)
        if observation_dates:
            # Recency: observations older than 365d count half
            recent = 0.0
            for d in observation_dates:
                age = (as_of - d).days
                if age < 0:
                    continue
                recent += 1.0 if age <= 180 else (0.6 if age <= 365 else 0.35)
            effective = recent
            if spread_days is not None and spread_days < self.MIN_SPREAD_DAYS_FOR_FULL_CREDIT and n >= 3:
                effective *= self.CONCENTRATION_PENALTY + (1.0 - self.CONCENTRATION_PENALTY) * (
                    spread_days / self.MIN_SPREAD_DAYS_FOR_FULL_CREDIT
                )

        if data_quality is not None and data_quality < 0.5:
            effective *= 0.75

        effective_n = int(round(effective))
        if effective_n < floors["emerging"]:
            level = SufficiencyLevel.INSUFFICIENT
        elif effective_n < floors["supported"]:
            level = SufficiencyLevel.EMERGING
        elif effective_n < floors["strong"]:
            level = SufficiencyLevel.SUPPORTED
        else:
            level = SufficiencyLevel.STRONG

        return {
            "domain": domain,
            "level": level.value,
            "sample_count": n,
            "effective_sample_count": effective_n,
            "spread_days": spread_days,
            "concentration_ratio": concentration_ratio,
            "floors": floors,
            "may_override_defaults": level in {SufficiencyLevel.SUPPORTED, SufficiencyLevel.STRONG},
            "note": "Temporally concentrated samples are down-weighted — absence of spread ≠ strong evidence.",
        }

    @staticmethod
    def _temporal_stats(
        observation_dates: Optional[Sequence[date]], as_of: date
    ) -> tuple[Optional[int], Optional[float]]:
        if not observation_dates:
            return None, None
        days = sorted({d for d in observation_dates if d is not None and d <= as_of})
        if len(days) < 2:
            return 0 if days else None, 1.0 if days else None
        spread = (days[-1] - days[0]).days
        # Fraction of samples in the densest 7-day window
        best = 1
        for i, start in enumerate(days):
            j = i
            while j < len(days) and (days[j] - start).days <= 7:
                j += 1
            best = max(best, j - i)
        concentration = best / len(days)
        return spread, round(concentration, 3)
