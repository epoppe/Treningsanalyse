"""Bootstrap / robust uncertainty helpers for coaching signals."""

from __future__ import annotations

import random
from statistics import mean, median
from typing import Any, Dict, List, Optional, Sequence


def bootstrap_ci(
    samples: Sequence[float],
    *,
    n_boot: int = 500,
    alpha: float = 0.05,
    seed: int = 42,
    statistic: str = "mean",
) -> Dict[str, Any]:
    values = [float(x) for x in samples if x is not None]
    n = len(values)
    if n == 0:
        return {"estimate": None, "ci95": None, "sample_count": 0}
    rng = random.Random(seed)
    stat_fn = median if statistic == "median" else mean
    estimate = float(stat_fn(values))
    if n == 1:
        return {"estimate": estimate, "ci95": [estimate, estimate], "sample_count": 1}
    boots: List[float] = []
    for _ in range(n_boot):
        draw = [values[rng.randrange(n)] for _ in range(n)]
        boots.append(float(stat_fn(draw)))
    boots.sort()
    lo_i = int((alpha / 2) * (n_boot - 1))
    hi_i = int((1 - alpha / 2) * (n_boot - 1))
    return {
        "estimate": round(estimate, 4),
        "ci95": [round(boots[lo_i], 4), round(boots[hi_i], 4)],
        "sample_count": n,
    }


def ci_width_penalty(ci95: Optional[Sequence[float]], scale: float) -> float:
    """Wider CI → lower evidence factor in [0, 1]."""
    if not ci95 or len(ci95) < 2 or scale <= 0:
        return 0.5
    width = abs(float(ci95[1]) - float(ci95[0]))
    return max(0.15, min(1.0, 1.0 - (width / scale) * 0.5))


def evidence_band(
    *,
    sample_count: int,
    effect_size: Optional[float],
    min_n: int = 12,
    min_effect: float = 0.15,
    stable_folds: int = 0,
    required_stable_folds: int = 2,
) -> str:
    if sample_count < min_n or effect_size is None or abs(effect_size) < min_effect:
        return "weak"
    if stable_folds >= required_stable_folds and sample_count >= min_n * 2:
        return "strong"
    return "moderate"
