"""Prospective-first evidence hierarchy — personal data does not auto-replace defaults."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, Sequence

from .sample_sufficiency_policy import SampleSufficiencyPolicy, SufficiencyLevel


class EvidenceHierarchy:
    """
    Priority:
      1. prospective personal evidence (if sufficient)
      2. historical personal evidence (if sufficient)
      3. physiological / default rules
    """

    def __init__(self, policy: Optional[SampleSufficiencyPolicy] = None):
        self._policy = policy or SampleSufficiencyPolicy()

    def resolve(
        self,
        *,
        domain: str,
        prospective_n: int = 0,
        historical_n: int = 0,
        prospective_dates: Optional[Sequence[date]] = None,
        historical_dates: Optional[Sequence[date]] = None,
        as_of: Optional[date] = None,
        data_quality: Optional[float] = None,
    ) -> Dict[str, Any]:
        as_of = as_of or date.today()
        pros = self._policy.assess(
            domain=domain,
            sample_count=prospective_n,
            observation_dates=prospective_dates,
            as_of=as_of,
            data_quality=data_quality,
        )
        hist = self._policy.assess(
            domain=domain,
            sample_count=historical_n,
            observation_dates=historical_dates,
            as_of=as_of,
            data_quality=data_quality,
        )

        if pros["may_override_defaults"]:
            source = "prospective"
            level = pros["level"]
            sample_count = prospective_n
            effective = pros["effective_sample_count"]
        elif hist["may_override_defaults"]:
            source = "historical"
            level = hist["level"]
            sample_count = historical_n
            effective = hist["effective_sample_count"]
        else:
            source = "default"
            # Surface best personal level even when still default
            if pros["level"] != SufficiencyLevel.INSUFFICIENT.value:
                level = pros["level"]
                sample_count = prospective_n
                effective = pros["effective_sample_count"]
            elif hist["level"] != SufficiencyLevel.INSUFFICIENT.value:
                level = hist["level"]
                sample_count = historical_n
                effective = hist["effective_sample_count"]
            else:
                level = SufficiencyLevel.INSUFFICIENT.value
                sample_count = max(prospective_n, historical_n)
                effective = max(pros["effective_sample_count"], hist["effective_sample_count"])

        return {
            "source": source,
            "evidence_level": level,
            "sample_count": sample_count,
            "effective_sample_count": effective,
            "prospective": pros,
            "historical": hist,
            "personalized": source in {"prospective", "historical"},
            "note": "Defaults remain until SampleSufficiencyPolicy allows override.",
        }
