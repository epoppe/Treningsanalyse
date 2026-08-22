"""Material change detection between recommendation ledger snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from .coaching_reason_codes import map_trace_item


_METRIC_RULES: Tuple[Tuple[str, str, float, float], ...] = (
    ("hrv_delta_pct", "HRV", 0.03, 3.0),
    ("readiness", "Readiness", 0.05, 5.0),
    ("tsb", "TSB", 0.15, 2.0),
    ("ctl", "CTL", 0.05, 0.3),
    ("atl", "ATL", 0.05, 0.3),
    ("sleep_hours", "Søvn", 0.08, 0.5),
    ("sleep_minutes", "Søvn", 0.08, 20.0),
    ("rhr", "Hvilepuls", 0.03, 2.0),
    ("body_battery", "Body Battery", 0.05, 5.0),
    ("lt2_pace", "Terskel", 0.02, 5.0),
    ("vo2max", "VO₂max", 0.02, 0.5),
    ("ef_30d", "Aerob effektivitet", 0.03, 1.0),
    ("durability", "Holdbarhet", 0.05, 3.0),
)


def _extract_metrics(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not record:
        return {}
    metrics: Dict[str, Any] = {}
    ctx = record.get("input_context") or {}
    summary = ctx.get("context_summary") if isinstance(ctx, dict) else {}
    if isinstance(summary, dict):
        metrics.update(summary)
    state = record.get("athlete_state_snapshot") or {}
    if isinstance(state, dict):
        for key in ("fitness", "recovery", "fatigue", "durability", "aerobic_efficiency"):
            dim = state.get(key)
            if isinstance(dim, dict) and dim.get("value") is not None:
                metrics.setdefault(key, dim.get("value"))
    phase = (ctx.get("training_phase") if isinstance(ctx, dict) else None) or record.get(
        "goal_snapshot"
    )
    if isinstance(phase, dict):
        if phase.get("phase"):
            metrics["training_phase"] = phase.get("phase")
        if phase.get("primary_limiter"):
            metrics["primary_limiter"] = phase.get("primary_limiter")
    return metrics


def _reason_codes(record: Optional[Dict[str, Any]]) -> Set[str]:
    if not record:
        return set()
    trace = record.get("decision_trace") or []
    if isinstance(trace, dict):
        trace = trace.get("items") or []
    codes: Set[str] = set()
    for item in trace:
        if not isinstance(item, dict):
            continue
        code = map_trace_item(item)
        if code:
            codes.add(code)
    return codes


def _direction(before: float, after: float, higher_is_better: bool = True) -> str:
    delta = after - before
    if abs(delta) < 1e-9:
        return "unchanged"
    improved = delta > 0 if higher_is_better else delta < 0
    return "improved" if improved else "worsened"


def _materiality(abs_delta: float, rel_delta: float, abs_thr: float, rel_thr: float) -> str:
    if abs_delta >= abs_thr * 2 or rel_delta >= rel_thr * 2:
        return "high"
    if abs_delta >= abs_thr or rel_delta >= rel_thr:
        return "moderate"
    return "low"


class UpdateDeltaService:
    def compute(
        self,
        before: Optional[Dict[str, Any]],
        after: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        before_metrics = _extract_metrics(before)
        after_metrics = _extract_metrics(after)
        before_type = (before or {}).get("recommended_workout_type")
        after_type = (after or {}).get("recommended_workout_type")
        recommendation_changed = bool(
            before_type and after_type and before_type != after_type
        ) or (before is None and after is not None and after_type)

        material_changes: List[Dict[str, Any]] = []
        for key, label, rel_thr, abs_thr in _METRIC_RULES:
            b = before_metrics.get(key)
            a = after_metrics.get(key)
            if b is None or a is None:
                continue
            try:
                b_f, a_f = float(b), float(a)
            except (TypeError, ValueError):
                continue
            abs_delta = abs(a_f - b_f)
            rel_delta = abs_delta / max(abs(b_f), 1e-6)
            if abs_delta < abs_thr and rel_delta < rel_thr:
                continue
            higher_better = key not in {"atl", "fatigue", "rhr", "lt2_pace"}
            material_changes.append(
                {
                    "metric": key,
                    "label": label,
                    "before": b_f,
                    "after": a_f,
                    "direction": _direction(b_f, a_f, higher_better),
                    "materiality": _materiality(abs_delta, rel_delta, abs_thr, rel_thr),
                }
            )

        for key, label in (("training_phase", "Treningsfase"), ("primary_limiter", "Primær limiter")):
            b, a = before_metrics.get(key), after_metrics.get(key)
            if b is not None and a is not None and b != a:
                material_changes.append(
                    {
                        "metric": key,
                        "label": label,
                        "before": b,
                        "after": a,
                        "direction": "changed",
                        "materiality": "moderate",
                    }
                )

        before_codes = _reason_codes(before)
        after_codes = _reason_codes(after)
        added = sorted(after_codes - before_codes)
        removed = sorted(before_codes - after_codes)

        if before is None:
            summary = "Første registrerte anbefaling etter oppdatering."
        elif not material_changes and not recommendation_changed:
            summary = "Ingen vesentlige endringer — dagens anbefaling er uendret."
        elif recommendation_changed:
            summary = f"Anbefaling endret fra {before_type} til {after_type}."
        else:
            summary = "Data oppdatert med vesentlige signalendringer, men anbefalingen er uendret."

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "material_changes": material_changes,
            "recommendation_changed": recommendation_changed,
            "before_recommendation": before_type,
            "after_recommendation": after_type,
            "reason_codes_added": added,
            "reason_codes_removed": removed,
            "has_material_change": bool(material_changes or recommendation_changed),
            "summary": summary,
        }
