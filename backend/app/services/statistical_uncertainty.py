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


def block_bootstrap_delta(
    period_a: Sequence[float],
    period_b: Sequence[float],
    *,
    block_size: int = 7,
    n_boot: int = 400,
    alpha: float = 0.05,
    seed: int = 42,
) -> Dict[str, Any]:
    """Week-block bootstrap of mean(A) - mean(B).

    Daily points inside a rolling metric are not independent. Resampling
    contiguous blocks is a conservative uncertainty check, not an exact CI.
    """

    def _blocks(values: Sequence[float]) -> List[List[float]]:
        cleaned = [float(v) for v in values if v is not None]
        if not cleaned:
            return []
        size = max(1, block_size)
        if len(cleaned) <= size:
            return [cleaned]
        chunks = [cleaned[i : i + size] for i in range(0, len(cleaned), size)]
        return [chunk for chunk in chunks if chunk]

    blocks_a = _blocks(period_a)
    blocks_b = _blocks(period_b)
    if not blocks_a or not blocks_b:
        return {
            "estimate": None,
            "ci95": None,
            "sample_count": 0,
            "method": "week_block_bootstrap",
            "heuristic": True,
        }

    def _mean(blocks: Sequence[Sequence[float]]) -> float:
        flat = [v for block in blocks for v in block]
        return sum(flat) / len(flat)

    estimate = _mean(blocks_a) - _mean(blocks_b)
    rng = random.Random(seed)
    boots: List[float] = []
    for _ in range(n_boot):
        draw_a = [blocks_a[rng.randrange(len(blocks_a))] for _ in range(len(blocks_a))]
        draw_b = [blocks_b[rng.randrange(len(blocks_b))] for _ in range(len(blocks_b))]
        boots.append(_mean(draw_a) - _mean(draw_b))
    boots.sort()
    lo_i = int((alpha / 2) * (n_boot - 1))
    hi_i = int((1 - alpha / 2) * (n_boot - 1))
    return {
        "estimate": round(estimate, 4),
        "ci95": [round(boots[lo_i], 4), round(boots[hi_i], 4)],
        "sample_count": len(period_a) + len(period_b),
        "block_size_days": block_size,
        "method": "week_block_bootstrap",
        "heuristic": True,
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
