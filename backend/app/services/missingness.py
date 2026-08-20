"""Missingness-aware evidence — missing ≠ negative."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def classify_signal(
    value: Optional[float],
    *,
    negative_if_below: Optional[float] = None,
    negative_if_above: Optional[float] = None,
    name: str = "signal",
) -> Dict[str, Any]:
    if value is None:
        return {
            "name": name,
            "status": "missing",
            "is_negative": False,
            "value": None,
            "note": "Missing signal is not treated as a negative finding.",
        }
    is_negative = False
    if negative_if_below is not None and value < negative_if_below:
        is_negative = True
    if negative_if_above is not None and value > negative_if_above:
        is_negative = True
    return {
        "name": name,
        "status": "negative" if is_negative else "ok",
        "is_negative": is_negative,
        "value": value,
    }


def missing_evidence_list(signals: Dict[str, Optional[Any]]) -> List[str]:
    return [k for k, v in signals.items() if v is None]


def annotate_model_output(payload: Dict[str, Any], signals: Dict[str, Optional[Any]]) -> Dict[str, Any]:
    out = dict(payload)
    out["missing_evidence"] = missing_evidence_list(signals)
    out["signal_classes"] = {
        k: classify_signal(v if isinstance(v, (int, float)) or v is None else None, name=k)
        for k, v in signals.items()
    }
    return out
