"""Single personalization evidence budget — stop inventing n>=X per service."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional


class PersonalizationLevel:
    DEFAULT = "DEFAULT"
    EMERGING_PERSONAL = "EMERGING_PERSONAL"
    PERSONAL_SUPPORTED = "PERSONAL_SUPPORTED"
    PERSONAL_STRONG = "PERSONAL_STRONG"


class PersonalizationEvidencePolicy:
    """
    Canonical policy for when personal evidence may override defaults.

    Prefer SampleSufficiencyPolicy for domain-specific floors + temporal spread.
    Decay reduces weight for old evidence without deleting history.
    """

    MIN_EMERGING = 8
    MIN_SUPPORTED = 20
    MIN_STRONG = 40
    MAX_AGE_DAYS_FULL = 180
    MAX_AGE_DAYS_HALF = 365

    def assess(
        self,
        *,
        sample_count: int,
        stable_folds: int = 0,
        evidence_strength: Optional[float] = None,
        ci_width: Optional[float] = None,
        last_supporting_observation: Optional[date] = None,
        as_of: Optional[date] = None,
        prospective: bool = False,
    ) -> Dict[str, Any]:
        as_of = as_of or date.today()
        decay = 1.0
        age_days = None
        if last_supporting_observation is not None:
            age_days = (as_of - last_supporting_observation).days
            if age_days > self.MAX_AGE_DAYS_HALF:
                decay = 0.35
            elif age_days > self.MAX_AGE_DAYS_FULL:
                decay = 0.6

        effective_n = int(sample_count * decay)
        strength = float(evidence_strength or 0.0) * decay
        if ci_width is not None and ci_width > 0.4:
            strength *= 0.7

        if effective_n < self.MIN_EMERGING or (not prospective and effective_n < self.MIN_EMERGING):
            level = PersonalizationLevel.DEFAULT
        elif effective_n < self.MIN_SUPPORTED or strength < 0.35:
            level = PersonalizationLevel.EMERGING_PERSONAL
        elif effective_n < self.MIN_STRONG or stable_folds < 2:
            level = PersonalizationLevel.PERSONAL_SUPPORTED
        else:
            level = PersonalizationLevel.PERSONAL_STRONG

        may_override = level in {
            PersonalizationLevel.PERSONAL_SUPPORTED,
            PersonalizationLevel.PERSONAL_STRONG,
        }
        return {
            "level": level,
            "may_override_defaults": may_override,
            "sample_count": sample_count,
            "effective_sample_count": effective_n,
            "decay_factor": round(decay, 3),
            "age_days": age_days,
            "evidence_strength": round(strength, 3),
            "note": "Historical evidence retained; decay only reduces current decision weight.",
        }
