"""Decision consistency under insignificant input perturbations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional


class DecisionConsistencyService:
    """
    Small irrelevant changes should not flip recommendations repeatedly.

    Reports: stable | sensitive | unstable
    """

    def evaluate(
        self,
        base_context: Dict[str, Any],
        decide_fn: Callable[[Dict[str, Any]], str],
        *,
        perturbations: Optional[List[Dict[str, float]]] = None,
    ) -> Dict[str, Any]:
        perturbations = perturbations or [
            {"hrv_delta_pct": -0.1},
            {"hrv_delta_pct": 0.1},
            {"ctl": 0.1},
            {"ctl": -0.1},
            {"readiness": 0.5},
            {"readiness": -0.5},
            {"sleep_hours": 0.02},
            {"sleep_hours": -0.02},
        ]
        base_decision = decide_fn(base_context)
        flips = []
        for delta in perturbations:
            ctx = deepcopy(base_context)
            for key, d in delta.items():
                if ctx.get(key) is None:
                    continue
                ctx[key] = float(ctx[key]) + float(d)
            out = decide_fn(ctx)
            if out != base_decision:
                flips.append({"delta": delta, "decision": out})

        rate = len(flips) / max(1, len(perturbations))
        if rate == 0:
            status = "stable"
        elif rate <= 0.25:
            status = "sensitive"
        else:
            status = "unstable"
        return {
            "base_decision": base_decision,
            "status": status,
            "flip_rate": round(rate, 3),
            "flips": flips,
            "note": "Unstable cliffs should use hysteresis or continuous scoring — not more hard rules.",
        }

    @staticmethod
    def with_hysteresis(
        value: Optional[float],
        *,
        threshold: float,
        previous_triggered: bool,
        band: float,
        lower_is_triggered: bool = True,
    ) -> bool:
        """Simple Schmitt-trigger style hysteresis around a threshold."""
        if value is None:
            return previous_triggered
        if lower_is_triggered:
            if previous_triggered:
                return value < threshold + band
            return value < threshold - band
        if previous_triggered:
            return value > threshold - band
        return value > threshold + band
