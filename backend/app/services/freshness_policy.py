"""Canonical freshness policies for coaching metrics."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional


POLICY = {
    "lt2": {"fresh_days": 21, "aging_days": 60, "stale_days": 90, "usable_stale": ["fallback"]},
    "vo2max": {"fresh_days": 30, "aging_days": 60, "stale_days": 120, "usable_stale": ["fallback"]},
    "critical_speed": {"fresh_days": 21, "aging_days": 45, "stale_days": 90, "usable_stale": ["fallback"]},
    "weather": {"fresh_days": 1, "aging_days": 2, "stale_days": 3, "usable_stale": []},
    "hrv_baseline": {"fresh_days": 7, "aging_days": 14, "stale_days": 30, "usable_stale": ["context"]},
    "calibration_snapshot": {"fresh_days": 14, "aging_days": 30, "stale_days": 60, "usable_stale": ["fallback"]},
}


class FreshnessPolicy:
    @staticmethod
    def assess(
        metric: str,
        *,
        as_of: date,
        observed_on: Optional[date] = None,
        age_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        rules = POLICY.get(metric, {"fresh_days": 14, "aging_days": 30, "stale_days": 60, "usable_stale": ["fallback"]})
        if age_days is None:
            if observed_on is None:
                return {
                    "metric": metric,
                    "age_days": None,
                    "freshness": "missing",
                    "usable_for": [],
                    "missing_evidence": True,
                }
            age_days = (as_of - observed_on).days
        if age_days <= rules["fresh_days"]:
            freshness = "fresh"
            usable = ["primary", "fallback", "context"]
        elif age_days <= rules["aging_days"]:
            freshness = "aging"
            usable = ["primary_with_caution", "fallback", "context"]
        elif age_days <= rules["stale_days"]:
            freshness = "stale"
            usable = list(rules.get("usable_stale") or ["fallback"])
        else:
            freshness = "stale"
            usable = list(rules.get("usable_stale") or [])
        return {
            "metric": metric,
            "age_days": age_days,
            "freshness": freshness,
            "usable_for": usable,
            "high_confidence_primary": freshness == "fresh",
            "missing_evidence": False,
        }

    @staticmethod
    def bundle(as_of: date, ages: Dict[str, Optional[int]]) -> Dict[str, Any]:
        return {metric: FreshnessPolicy.assess(metric, as_of=as_of, age_days=age) for metric, age in ages.items()}
