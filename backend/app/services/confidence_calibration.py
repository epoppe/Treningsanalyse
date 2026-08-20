"""Confidence calibration for recommendation decision_confidence."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


def reliability_diagram(
    pairs: Sequence[Tuple[float, bool]],
    *,
    bins: Optional[Sequence[Tuple[float, float]]] = None,
) -> List[Dict[str, Any]]:
    """
    pairs: (predicted_confidence, empirical_success)
    Returns reliability diagram bins.
    """
    if bins is None:
        bins = [(i / 10.0, (i + 1) / 10.0) for i in range(10)]
    out: List[Dict[str, Any]] = []
    for lo, hi in bins:
        in_bin = [(p, s) for p, s in pairs if lo <= p < hi or (hi == 1.0 and p == 1.0)]
        if not in_bin:
            continue
        mean_pred = sum(p for p, _ in in_bin) / len(in_bin)
        empirical = sum(1 for _, s in in_bin if s) / len(in_bin)
        out.append(
            {
                "bin": [lo, hi],
                "mean_predicted_confidence": round(mean_pred, 3),
                "empirical_success": round(empirical, 3),
                "n": len(in_bin),
                "overconfidence": round(mean_pred - empirical, 3),
            }
        )
    return out


def calibrate_label(diagram: List[Dict[str, Any]]) -> Dict[str, Any]:
    """If systematically overconfident, rename/use as decision_strength."""
    if not diagram:
        return {
            "label": "decision_confidence",
            "overconfident": False,
            "mean_gap": None,
        }
    gaps = [b["overconfidence"] for b in diagram if b.get("n", 0) >= 5]
    if not gaps:
        gaps = [b["overconfidence"] for b in diagram]
    mean_gap = sum(gaps) / len(gaps)
    overconfident = mean_gap > 0.08
    return {
        "label": "decision_strength" if overconfident else "decision_confidence",
        "overconfident": overconfident,
        "mean_gap": round(mean_gap, 3),
        "note": "Use decision_strength when confidence is systematically optimistic.",
    }
