"""Propagate missing/stale/low-quality inputs into evidence — never invent normality."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


# Stale/missing reduces confidence; it does not automatically force rest.
_STALE_PENALTY = 0.15
_MISSING_CORE_PENALTY = 0.25
_AGING_PENALTY = 0.05

_CORE_METRICS = ("lt2", "hrv_baseline", "critical_speed")


def apply_data_quality_to_evidence(
    evidence_strength: float,
    decision_confidence: float,
    freshness: Optional[Dict[str, Any]] = None,
    *,
    data_quality_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Reduce evidence/confidence when canonical inputs are missing/stale/aging.

    Returns updated strengths plus whether the *decision* should change (always False here —
    callers must keep recommendation type unless a separate safety rule fires).
    """
    freshness = freshness or {}
    strength = float(evidence_strength or 0.0)
    confidence = float(decision_confidence or 0.0)
    factors = []

    for metric in _CORE_METRICS:
        entry = freshness.get(metric) or {}
        status = entry.get("status") or entry.get("freshness") or "missing"
        if status == "missing":
            strength *= 1.0 - _MISSING_CORE_PENALTY
            confidence *= 1.0 - _MISSING_CORE_PENALTY
            factors.append(f"missing_{metric}")
        elif status == "stale":
            strength *= 1.0 - _STALE_PENALTY
            confidence *= 1.0 - _STALE_PENALTY
            factors.append(f"stale_{metric}")
        elif status == "aging":
            strength *= 1.0 - _AGING_PENALTY
            confidence *= 1.0 - _AGING_PENALTY
            factors.append(f"aging_{metric}")

    if data_quality_score is not None and data_quality_score < 0.5:
        strength *= 0.85
        confidence *= 0.85
        factors.append("low_data_quality_score")

    return {
        "evidence_strength": round(max(0.0, min(1.0, strength)), 3),
        "decision_confidence": round(max(0.0, min(1.0, confidence)), 3),
        "decision_changed": False,
        "confidence_reduced": bool(factors),
        "quality_factors": factors,
        "note": "Missing/stale evidence reduces confidence; it does not auto-force rest.",
    }
