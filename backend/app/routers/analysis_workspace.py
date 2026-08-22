"""Analysis workspace summary API — wraps existing services for /analyse.

Does not invent coaching/analytics algorithms. Presentation payloads only.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..database.models.summaries import MonthlySummary, WeeklySummary
from ..dependencies import get_db, get_data_storage
from ..services.trend_analysis_service import METRIC_FETCHERS, TrendAnalysisService
from ..services.history_cockpit_service import HistoryCockpitService
from ..services.training_response_service import TrainingResponseService
from ..services.mcp_derived_metrics_service import McpDerivedMetricsService
from ..services.analytics_metric_registry import (
    ANALYSIS_PRESETS,
    MATRIX_OUTCOMES,
    MATRIX_PREDICTORS,
    STIMULUS_AGGREGATES,
    catalog_payload,
    dependency_relation,
    get_analytics_metric,
    list_analytics_metrics,
    recommended_outcomes_for,
    should_suppress_correlation,
)
from ..storage import DataStorage

router = APIRouter(tags=["Analysis Workspace"])

PERIOD_DAYS = {
    "28d": 28,
    "90d": 90,
    "6m": 183,
    "1y": 365,
    "2y": 730,
    "all": 3650,
}

DOMAIN_METRICS = [
    {"domain": "fitness", "metric": "ctl", "mcp_key": "fitness.ctl", "label": "Form (CTL)"},
    {"domain": "threshold", "metric": "critical_speed", "mcp_key": "running.critical_speed", "label": "Critical speed"},
    {"domain": "aerobic_efficiency", "metric": "easy_run_efficiency", "mcp_key": "fitness.ef_30d", "label": "Aerobic efficiency"},
    {"domain": "durability", "metric": "durability", "mcp_key": "running.durability_score", "label": "Holdbarhet"},
    {"domain": "training_load", "metric": "ctl", "mcp_key": "fitness.atl", "label": "Akutt belastning (ATL)"},
    {"domain": "recovery", "metric": "hrv_rmssd", "mcp_key": "cardio.hrv_7d", "label": "Restitusjon (HRV)"},
    {"domain": "consistency", "metric": "vo2max", "mcp_key": "consistency.score", "label": "Konsistens"},
]

RELATIONSHIP_PRESETS = [
    {
        "id": "easy_volume_efficiency",
        "question": "Henger lett volum sammen med aerob effektivitet?",
        "stimulus": "easy_volume",
        "outcome": "easy_efficiency",
        "section": "TRAINING → FITNESS",
    },
    {
        "id": "threshold_volume_pace",
        "question": "Henger terskelminutter sammen med senere terskelfart?",
        "stimulus": "threshold_volume",
        "outcome": "threshold_pace",
        "section": "TRAINING → FITNESS",
    },
    {
        "id": "weekly_tss_hrv",
        "question": "Hvordan følger HRV belastningen?",
        "stimulus": "weekly_tss",
        "outcome": "hrv",
        "section": "LOAD → RECOVERY",
    },
    {
        "id": "high_intensity_durability",
        "question": "Henger hard volum sammen med holdbarhet?",
        "stimulus": "high_intensity_volume",
        "outcome": "durability",
        "section": "TRAINING → FITNESS",
    },
]


def _period_days(period: str) -> int:
    return PERIOD_DAYS.get(period, 90)


def _window_key(days: int) -> str:
    if days <= 28:
        return "28d"
    if days <= 90:
        return "90d"
    return "365d"


def _evidence_label(confidence: Optional[float], sample_count: int) -> str:
    if sample_count < 5 or confidence is None or confidence < 0.35:
        return "insufficient"
    if confidence < 0.55:
        return "emerging"
    if confidence < 0.75:
        return "supported"
    return "strong"


def _direction_no(direction: str, higher_is_better: bool = True) -> str:
    d = (direction or "uncertain").lower()
    if d == "improving":
        return "Forbedring"
    if d == "declining":
        return "Nedgang"
    if d == "stable":
        return "Stabil"
    return "Usikker"


def _domain_from_block(spec: Dict[str, Any], block: Optional[Dict[str, Any]], window: str) -> Dict[str, Any]:
    if not block:
        return {
            **spec,
            "direction": "uncertain",
            "direction_label": "Usikker",
            "relative_change_pct": None,
            "current": None,
            "sample_count": 0,
            "confidence": 0.0,
            "evidence": "insufficient",
            "change_point_detected": False,
            "window": window,
        }
    hib = bool(block.get("higher_is_better", True))
    return {
        **spec,
        "direction": block.get("direction"),
        "direction_label": _direction_no(str(block.get("direction")), hib),
        "relative_change_pct": block.get("relative_change_pct"),
        "absolute_change": block.get("absolute_change"),
        "current": block.get("current"),
        "baseline": block.get("baseline"),
        "sample_count": block.get("sample_count") or 0,
        "confidence": block.get("confidence"),
        "evidence": _evidence_label(
            block.get("confidence"), int(block.get("sample_count") or 0)
        ),
        "change_point_detected": bool(block.get("change_point_detected")),
        "window": window,
        "start_date": block.get("start_date"),
        "end_date": block.get("end_date"),
    }


def _period_explanation_nb(metric: str, diff: Optional[float], evidence: str) -> str:
    label = metric.replace("_", " ")
    if diff is None:
        return f"{label}: utilstrekkelig data for sammenligning."
    if evidence == "insufficient":
        return f"{label}: for få datapunkter til sikker vurdering."
    if abs(diff) < 0.05:
        return f"{label}: omtrent uendret vs. forrige periode."
    direction = "høyere" if diff > 0 else "lavere"
    return f"{label} er {direction} enn forrige periode (Δ {diff:+.1f})."


@router.get("/development")
def get_development(
    period: str = Query("90d", description="28d|90d|6m|1y|2y|all"),
    end_date: Optional[date] = Query(None),
    multi_horizon: bool = Query(
        False,
        description="Include 28d/90d/365d trend blocks per domain",
    ),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    """Domain summary cards for the Utvikling tab."""
    end = end_date or date.today()
    days = _period_days(period)
    window = _window_key(min(days, 365))
    window_days = int(window.replace("d", ""))
    try:
        windows = (28, 90, 365) if multi_horizon else (window_days,)
        trends = TrendAnalysisService(db, storage).analyze_all(
            end_date=end,
            windows=windows,
        )
        metrics = trends.get("metrics") or {}
        domains: List[Dict[str, Any]] = []
        for spec in DOMAIN_METRICS:
            metric_trends = metrics.get(spec["metric"]) or {}
            block = metric_trends.get(window) or metric_trends.get("90d") or metric_trends.get("28d")
            if not block and metric_trends:
                block = next(iter(metric_trends.values()))
            domain = _domain_from_block(spec, block, window)
            if multi_horizon:
                domain["horizons"] = {
                    key: _domain_from_block(spec, metric_trends.get(key), key)
                    for key in ("28d", "90d", "365d")
                }
            domains.append(domain)
        return {
            "date": end.isoformat(),
            "period": period,
            "period_days": days,
            "window": window,
            "multi_horizon": multi_horizon,
            "domains": domains,
            "raw_metrics": metrics,
            "disclaimer": "Trends are observational summaries — not causal claims.",
            "available_metrics": [
                m["key"]
                for m in list_analytics_metrics(include_stimulus=False)
                if m.get("supports_trend")
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/timeseries")
def get_timeseries(
    metrics: str = Query(
        "fitness.ctl,cardio.hrv_7d",
        description="Comma-separated analytics/MCP metric keys (max 4)",
    ),
    period: str = Query("90d"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    end = end_date or date.today()
    days = _period_days(period)
    start = end - timedelta(days=days - 1)
    keys = [m.strip() for m in metrics.split(",") if m.strip()][:4]
    if not keys:
        raise HTTPException(status_code=400, detail="At least one metric required")

    short_to_mcp = {
        "ctl": "fitness.ctl",
        "hrv_rmssd": "cardio.hrv_7d",
        "easy_run_efficiency": "fitness.ef_30d",
        "durability": "running.durability_score",
        "critical_speed": "running.critical_speed",
        "resting_hr": "cardio.rhr_7d",
    }
    resolved = [short_to_mcp.get(k, k) for k in keys]

    try:
        derived = McpDerivedMetricsService(db, storage)
        trend = TrendAnalysisService(db, storage)
        series: Dict[str, Any] = {}
        for original, key in zip(keys, resolved):
            spec = get_analytics_metric(key) or {}
            if key.startswith("stimulus.") or key in STIMULUS_AGGREGATES:
                points = _stimulus_aggregate_series(db, storage, key, start, end)
                series[original] = {
                    "metric": key,
                    "label": spec.get("label") or key,
                    "points": points,
                    "sample_count": len(points),
                    "scope": spec.get("scope") or "weekly",
                    "unit": spec.get("unit"),
                    "unit_note": "server-side stimulus aggregation (weekly samples)",
                    "alignment": "weekly_end_date",
                }
                continue
            if derived.metric_definition(key):
                result = derived.query_timeseries(
                    key, start_date=start, end_date=end, limit=days + 5
                )
                points = [
                    {
                        "date": str(p.get("date") or p.get("activity_date"))[:10],
                        "value": round(float(p["value"]), 4),
                    }
                    for p in (result.get("points") or [])
                    if p.get("value") is not None
                ]
                series[original] = {
                    "metric": key,
                    "label": spec.get("label") or key,
                    "unit": (derived.metric_definition(key) or {}).get("unit"),
                    "unit_note": "native units — not cross-normalized",
                    "scope": (derived.metric_definition(key) or {}).get("scope"),
                    "points": points,
                    "sample_count": len(points),
                    "missing_days_approx": max(0, days - len(points)),
                }
                continue
            if original in METRIC_FETCHERS or key in METRIC_FETCHERS:
                fetch_key = original if original in METRIC_FETCHERS else key
                points = trend.series_for_metric(fetch_key, start_date=start, end_date=end)
                series[original] = {
                    "metric": fetch_key,
                    "points": points,
                    "sample_count": len(points),
                    "unit_note": "native units — not cross-normalized",
                    "missing_days_approx": max(0, days - len(points)),
                }
            else:
                raise HTTPException(status_code=400, detail=f"Unknown metric: {original}")
        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "period": period,
            "series": series,
            "note": "Metrics keep native units and scopes; plot incompatible units on separate panels.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/catalog")
def get_analysis_catalog() -> Dict[str, Any]:
    """Curated analytics metric registry for /analyse pickers and presets."""
    return catalog_payload()


@router.get("/dependency-check")
def get_dependency_check(
    x: str = Query(...),
    y: str = Query(...),
    advanced: bool = Query(False),
) -> Dict[str, Any]:
    rel = dependency_relation(x, y)
    suppress, message = should_suppress_correlation(x, y, advanced=advanced)
    return {
        "x": x,
        "y": y,
        "relationship_kind": rel,
        "relationship_type": "MATHEMATICAL_DEPENDENCY"
        if rel == "DIRECT_DEPENDENCY"
        else "SAME_TIME_ASSOCIATION",
        "suppress_default": suppress and not advanced,
        "warning": message or None,
        "allow_advanced": rel == "SHARED_COMPONENT",
    }


@router.get("/presets")
def get_analysis_presets() -> Dict[str, Any]:
    return {"presets": ANALYSIS_PRESETS}


@router.get("/relationship-matrix")
def get_relationship_matrix(
    period: str = Query("1y"),
    end_date: Optional[date] = Query(None),
    advanced: bool = Query(False),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    end = end_date or date.today()
    lookback = _period_days(period)
    stimulus_map = {
        "stimulus.easy_minutes_28d": "easy_volume",
        "stimulus.threshold_minutes_14d": "threshold_volume",
        "stimulus.tss_28d": "weekly_tss",
        "stimulus.tss_7d": "weekly_tss",
    }
    outcome_map = {
        "fitness.ef_30d": "easy_efficiency",
        "running.critical_speed": "critical_speed",
        "running.durability_score": "durability",
        "recovery.hrv_delta_pct": "hrv",
        "cardio.hrv_7d": "hrv",
    }
    try:
        raw = TrainingResponseService(db, storage).analyze_responses(
            end_date=end,
            lookback_days=lookback,
        )
        by_pair = {
            (r.get("stimulus"), r.get("outcome")): r for r in (raw.get("relationships") or [])
        }
        cells: List[Dict[str, Any]] = []
        for pred in MATRIX_PREDICTORS:
            for outcome in MATRIX_OUTCOMES:
                suppress, msg = should_suppress_correlation(pred, outcome, advanced=advanced)
                if suppress and not advanced:
                    cells.append(
                        {
                            "predictor": pred,
                            "outcome": outcome,
                            "status": "suppressed",
                            "relationship_type": "MATHEMATICAL_DEPENDENCY",
                            "warning": msg,
                        }
                    )
                    continue
                stim = stimulus_map.get(pred)
                out = outcome_map.get(outcome)
                if not stim or not out:
                    cells.append(
                        {
                            "predictor": pred,
                            "outcome": outcome,
                            "status": "insufficient",
                            "relationship_type": "LAGGED_ASSOCIATION",
                            "note": "No training-response mapping for this pair yet.",
                        }
                    )
                    continue
                hit = by_pair.get((stim, out))
                if not hit:
                    cells.append(
                        {
                            "predictor": pred,
                            "outcome": outcome,
                            "status": "insufficient",
                            "relationship_type": "TRAINING_RESPONSE",
                            "sample_count": 0,
                        }
                    )
                    continue
                cells.append(
                    {
                        "predictor": pred,
                        "outcome": outcome,
                        "status": "ok",
                        "relationship_type": "TRAINING_RESPONSE",
                        "association": hit.get("relationship"),
                        "effect": hit.get("effect_size"),
                        "lag_days": hit.get("lag_days"),
                        "sample_count": hit.get("sample_count") or 0,
                        "evidence": hit.get("statistical_support"),
                        "warning": msg or None,
                    }
                )
        return {
            "date": end.isoformat(),
            "period": period,
            "predictors": MATRIX_PREDICTORS,
            "outcomes": MATRIX_OUTCOMES,
            "cells": cells,
            "disclaimer": raw.get("disclaimer")
            or "Observational associations — not causal claims.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/training-response")
def get_training_response_mode(
    outcome: str = Query("fitness.ef_30d"),
    period: str = Query("1y"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    end = end_date or date.today()
    lookback = _period_days(period)
    outcome_map = {
        "fitness.ef_30d": "easy_efficiency",
        "running.critical_speed": "critical_speed",
        "running.durability_score": "durability",
        "recovery.hrv_delta_pct": "hrv",
        "cardio.hrv_7d": "hrv",
        "easy_efficiency": "easy_efficiency",
        "critical_speed": "critical_speed",
        "durability": "durability",
        "hrv": "hrv",
    }
    tr_outcome = outcome_map.get(outcome)
    if not tr_outcome:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported outcome for training-response mode: {outcome}",
        )
    try:
        raw = TrainingResponseService(db, storage).analyze_responses(
            end_date=end,
            lookback_days=lookback,
        )
        matches = [r for r in (raw.get("relationships") or []) if r.get("outcome") == tr_outcome]
        matches.sort(
            key=lambda r: (
                0 if r.get("statistical_support") in {"strong", "moderate"} else 1,
                -(r.get("evidence_strength") or 0),
            )
        )
        suggested: List[str] = []
        for preset in ANALYSIS_PRESETS:
            if preset.get("outcome") == outcome or outcome_map.get(preset.get("outcome", "")) == tr_outcome:
                suggested = list(preset.get("predictors") or [])
                break
        return {
            "date": end.isoformat(),
            "period": period,
            "outcome": outcome,
            "mode": "TRAINING_RESPONSE",
            "suggested_predictors": suggested,
            "relationships": [
                {
                    "stimulus": r.get("stimulus"),
                    "outcome": r.get("outcome"),
                    "association": r.get("relationship"),
                    "lag_days": r.get("lag_days"),
                    "effect_size": r.get("effect_size"),
                    "sample_count": r.get("sample_count"),
                    "evidence": r.get("statistical_support"),
                    "relationship_type": "TRAINING_RESPONSE",
                    "wording": (
                        f"{str(r.get('stimulus')).replace('_', ' ')} is historically linked to "
                        f"{str(r.get('outcome')).replace('_', ' ')} "
                        f"(observational association — not causation)."
                    ),
                }
                for r in matches[:12]
            ],
            "disclaimer": raw.get("disclaimer"),
            "multiple_testing": raw.get("multiple_testing"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/relationships")
def get_relationships(
    period: str = Query("1y"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    end = end_date or date.today()
    lookback = _period_days(period)
    try:
        raw = TrainingResponseService(db, storage).analyze_responses(
            end_date=end,
            lookback_days=lookback,
        )
        by_pair = {
            (r.get("stimulus"), r.get("outcome")): r for r in (raw.get("relationships") or [])
        }
        cards: List[Dict[str, Any]] = []
        for preset in RELATIONSHIP_PRESETS:
            hit = by_pair.get((preset["stimulus"], preset["outcome"]))
            if not hit:
                cards.append(
                    {
                        **preset,
                        "status": "insufficient",
                        "association": "unclear",
                        "strength": "insufficient",
                        "relationship_type": "TRAINING_RESPONSE",
                        "lag_days": None,
                        "sample_count": 0,
                        "evidence": "insufficient",
                        "wording": "For lite data til å beskrive en assosiasjon.",
                    }
                )
                continue
            support = str(hit.get("statistical_support") or "weak")
            association = str(hit.get("relationship") or "unclear")
            effect = hit.get("effect_size")
            cards.append(
                {
                    **preset,
                    "status": "ok",
                    "association": association,
                    "strength": support,
                    "relationship_type": "TRAINING_RESPONSE",
                    "lag_days": hit.get("lag_days"),
                    "lag_profile": None,
                    "sample_count": hit.get("sample_count") or 0,
                    "evidence": {
                        "strong": "strong",
                        "moderate": "supported",
                        "weak": "emerging",
                        "insufficient": "insufficient",
                    }.get(support, "emerging"),
                    "effect": round(float(effect), 2) if isinstance(effect, (int, float)) else None,
                    "wording": (
                        f"{preset['stimulus'].replace('_', ' ')} er historisk knyttet til "
                        f"{preset['outcome'].replace('_', ' ')} "
                        f"(observasjonell assosiasjon — ikke årsak)."
                    ),
                    "raw": {
                        "statistical_support": support,
                        "effect_size": effect,
                        "limitations": hit.get("limitations"),
                    },
                }
            )
        return {
            "date": end.isoformat(),
            "period": period,
            "lookback_days": lookback,
            "cards": cards,
            "sections": sorted({c["section"] for c in RELATIONSHIP_PRESETS}),
            "advanced_scatter": "/sammenhenger",
            "disclaimer": raw.get("disclaimer")
            or "Relationships are observational associations, not causal claims.",
            "multiple_testing": raw.get("multiple_testing"),
            "ranking_eligible_count": len(raw.get("ranking_eligible_relationships") or []),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/history")
def get_history(
    period: str = Query("2y"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    end = end_date or date.today()
    start = end - timedelta(days=_period_days(period) - 1)
    try:
        months = (
            db.query(MonthlySummary)
            .filter(
                MonthlySummary.month_start_date >= start,
                MonthlySummary.month_end_date <= end + timedelta(days=31),
            )
            .order_by(MonthlySummary.month_start_date.desc())
            .limit(36)
            .all()
        )
        years: Dict[str, List[Dict[str, Any]]] = {}
        for m in months:
            payload = {
                "month_start": m.month_start_date.isoformat() if m.month_start_date else None,
                "month_end": m.month_end_date.isoformat() if m.month_end_date else None,
                "year": m.year,
                "month": m.month,
                "total_duration_seconds": m.total_duration,
                "total_distance_meters": m.total_distance,
                "activity_count": m.total_activities,
                "total_tss": m.total_tss,
            }
            year = str(m.month_start_date.year) if m.month_start_date else "unknown"
            years.setdefault(year, []).append(payload)
        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "period": period,
            "years": [
                {"year": y, "months": ms}
                for y, ms in sorted(years.items(), key=lambda item: item[0], reverse=True)
            ],
            "month_count": len(months),
            "note": "Hierarchical history from MonthlySummary — expand for weeks/sessions later.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/history/yoy")
def get_history_yoy(
    months: int = Query(12, ge=1, le=36),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    """Year-over-year monthly volume comparison for Historikk tab."""
    try:
        return HistoryCockpitService(db, storage).yoy_months(end_date=end_date, months=months)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/history/performance-recovery")
def get_history_performance_recovery(
    months: int = Query(12, ge=3, le=24),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    """Monthly performance/recovery snapshots."""
    try:
        return HistoryCockpitService(db, storage).performance_recovery_history(
            end_date=end_date,
            months=months,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/history/annotations")
def get_history_annotations(
    limit: int = Query(24, ge=1, le=60),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    """Notable plan/recommendation milestones for historical context."""
    try:
        return HistoryCockpitService(db, storage).annotations(end_date=end_date, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/period-comparison")
def get_period_comparison(
    period: str = Query("90d"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    """Compare last N days vs previous N days using TrendAnalysisService windows."""
    end = end_date or date.today()
    days = min(_period_days(period), 365)
    window = _window_key(days)
    window_days = int(window.replace("d", ""))
    try:
        svc = TrendAnalysisService(db, storage)
        current = svc.analyze_all(end_date=end, windows=(window_days,))
        previous_end = end - timedelta(days=days)
        previous = svc.analyze_all(end_date=previous_end, windows=(window_days,))
        rows: List[Dict[str, Any]] = []
        for metric in sorted(METRIC_FETCHERS.keys()):
            a = ((current.get("metrics") or {}).get(metric) or {}).get(window) or {}
            b = ((previous.get("metrics") or {}).get(metric) or {}).get(window) or {}
            a_val = a.get("current")
            b_val = b.get("current")
            diff = None
            if isinstance(a_val, (int, float)) and isinstance(b_val, (int, float)):
                diff = round(float(a_val) - float(b_val), 4)
            n = min(int(a.get("sample_count") or 0), int(b.get("sample_count") or 0))
            rows.append(
                {
                    "metric": metric,
                    "period_a": {
                        "label": f"Siste {days}d",
                        "end": end.isoformat(),
                        "value": a_val,
                        "sample_count": a.get("sample_count") or 0,
                    },
                    "period_b": {
                        "label": f"Forrige {days}d",
                        "end": previous_end.isoformat(),
                        "value": b_val,
                        "sample_count": b.get("sample_count") or 0,
                    },
                    "difference": diff,
                    "evidence": _evidence_label(
                        min(float(a.get("confidence") or 0), float(b.get("confidence") or 0)),
                        n,
                    ),
                    "explanation": _period_explanation_nb(
                        metric,
                        diff,
                        _evidence_label(
                            min(float(a.get("confidence") or 0), float(b.get("confidence") or 0)),
                            n,
                        ),
                    ),
                }
            )
        return {
            "period": period,
            "days": days,
            "window": window,
            "rows": rows,
            "disclaimer": "Differences are descriptive. Low sample → insufficient evidence.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/relationship-lag")
def get_relationship_lag(
    stimulus: str = Query(..., description="Stimulus key e.g. threshold_volume"),
    outcome: str = Query(..., description="Outcome key e.g. threshold_pace"),
    period: str = Query("1y"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    """Lag profile for a stimulus→outcome pair — observational only."""
    end = end_date or date.today()
    lookback = _period_days(period)
    start = end - timedelta(days=lookback)
    try:
        tr = TrainingResponseService(db, storage)
        profile: List[Dict[str, Any]] = []
        for lag in (7, 14, 21, 28, 42):
            hit = tr._correlate(stimulus, outcome, start, end, lag, family_size=1)  # noqa: SLF001
            if hit:
                profile.append(
                    {
                        "lag_days": lag,
                        "effect_size": hit.get("effect_size"),
                        "relationship": hit.get("relationship"),
                        "sample_count": hit.get("sample_count"),
                        "evidence": _evidence_label(
                            hit.get("confidence"), int(hit.get("sample_count") or 0)
                        ),
                    }
                )
            else:
                profile.append(
                    {
                        "lag_days": lag,
                        "effect_size": None,
                        "relationship": "uncertain",
                        "sample_count": 0,
                        "evidence": "insufficient",
                    }
                )
        scored = [p for p in profile if p.get("effect_size") is not None]
        best = max(scored, key=lambda p: abs(float(p["effect_size"]))) if scored else None
        return {
            "date": end.isoformat(),
            "period": period,
            "stimulus": stimulus,
            "outcome": outcome,
            "profile": profile,
            "best_lag_days": best.get("lag_days") if best else None,
            "disclaimer": "Lag profile is observational — not a causal dose recommendation.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/week/{week_date}")
def get_week(
    week_date: date = Path(..., description="Any date within the ISO week"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    monday = week_date - timedelta(days=week_date.weekday())
    sunday = monday + timedelta(days=6)
    try:
        weekly = (
            db.query(WeeklySummary)
            .filter(
                WeeklySummary.week_start_date <= sunday,
                WeeklySummary.week_end_date >= monday,
            )
            .order_by(WeeklySummary.week_start_date.desc())
            .first()
        )
        activities = (
            db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) >= monday,
                    func.date(Activity.start_time) <= sunday,
                )
            )
            .order_by(Activity.start_time.asc())
            .limit(50)
            .all()
        )
        sessions = [
            {
                "activity_id": a.activity_id,
                "name": a.activity_name,
                "type": (
                    a.activity_type.type_key
                    if getattr(a, "activity_type", None) is not None
                    else None
                ),
                "date": a.start_time.date().isoformat() if a.start_time else None,
                "distance_m": a.distance,
                "duration_s": a.duration,
            }
            for a in activities
        ]
        return {
            "week_start": monday.isoformat(),
            "week_end": sunday.isoformat(),
            "summary": {
                "total_duration": weekly.total_duration if weekly else None,
                "total_distance": weekly.total_distance if weekly else None,
                "activity_count": weekly.total_activities if weekly else len(sessions),
            }
            if weekly or sessions
            else None,
            "sessions": sessions,
            "compare_links": {
                "previous_week": (monday - timedelta(days=7)).isoformat(),
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _stimulus_aggregate_series(
    db: Session,
    storage: DataStorage,
    key: str,
    start: date,
    end: date,
) -> List[Dict[str, Any]]:
    """Build weekly samples for stimulus.* aggregates via TrainingResponseService."""
    spec = STIMULUS_AGGREGATES.get(key) or get_analytics_metric(key) or {}
    window = int(spec.get("aggregation_days") or 28)
    kind = str(spec.get("stimulus_kind") or "")
    stimulus_id = {
        "easy_volume": "easy_volume",
        "threshold_volume": "threshold_volume",
        "vo2_volume": "high_intensity_volume",
        "long_run_volume": "easy_volume",
        "weekly_tss": "weekly_tss",
    }.get(kind)
    if not stimulus_id:
        return []
    tr = TrainingResponseService(db, storage)
    points: List[Dict[str, Any]] = []
    cursor = start + timedelta(days=window)
    while cursor <= end:
        win_start = cursor - timedelta(days=window - 1)
        val = tr._stimulus_value(stimulus_id, win_start, cursor)  # noqa: SLF001
        if val is not None:
            points.append({"date": cursor.isoformat(), "value": round(float(val), 3)})
        cursor += timedelta(days=7)
    return points


@router.get("/intensity-distribution")
def get_intensity_distribution(
    period: str = Query("1y"),
    windows: str = Query("28,56,90"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    """Rolling zone1/2/3 % history for intensity-distribution questions."""
    end = end_date or date.today()
    days = _period_days(period)
    start = end - timedelta(days=days - 1)
    window_list = [int(w.strip()) for w in windows.split(",") if w.strip().isdigit()][:3]
    if not window_list:
        window_list = [28, 56, 90]
    keys = ["coaching.zone1_pct", "coaching.zone2_pct", "coaching.zone3_pct"]
    try:
        derived = McpDerivedMetricsService(db, storage)
        series: Dict[str, Any] = {}
        for key in keys:
            result = derived.query_timeseries(key, start_date=start, end_date=end, limit=days + 5)
            points = [
                {
                    "date": str(p.get("date") or p.get("activity_date"))[:10],
                    "value": round(float(p["value"]), 3),
                }
                for p in (result.get("points") or [])
                if p.get("value") is not None
            ]
            series[key] = {
                "metric": key,
                "points": points,
                "sample_count": len(points),
                "scope": "rolling_daily",
            }
        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "period": period,
            "requested_windows_days": window_list,
            "series": series,
            "note": (
                "Zone % series are daily coaching metrics (already rolling internally). "
                "Use requested_windows_days as analysis presets when comparing eras."
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/duration-curve-history")
def get_duration_curve_history(
    period: str = Query("1y"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    """Historical duration-curve development via *_hist MCP metrics."""
    end = end_date or date.today()
    days = _period_days(period)
    start = end - timedelta(days=days - 1)
    hist_keys = [
        "running.speed_5m_hist",
        "running.speed_10m_hist",
        "running.speed_20m_hist",
        "running.speed_40m_hist",
        "running.speed_60m_hist",
    ]
    try:
        derived = McpDerivedMetricsService(db, storage)
        curves: List[Dict[str, Any]] = []
        for key in hist_keys:
            if not derived.metric_definition(key):
                continue
            result = derived.query_timeseries(key, start_date=start, end_date=end, limit=days + 5)
            points = [
                {
                    "date": str(p.get("date") or p.get("activity_date"))[:10],
                    "value": round(float(p["value"]), 4),
                }
                for p in (result.get("points") or [])
                if p.get("value") is not None
            ]
            current = points[-1]["value"] if points else None
            year_ago_target = (end - timedelta(days=365)).isoformat()
            prev_year = None
            for p in reversed(points):
                if p["date"] <= year_ago_target:
                    prev_year = p["value"]
                    break
            best = max((p["value"] for p in points), default=None)
            curves.append(
                {
                    "metric": key,
                    "duration_label": key.replace("running.speed_", "").replace("_hist", ""),
                    "current": current,
                    "previous_year": prev_year,
                    "rolling_best": best,
                    "sample_count": len(points),
                    "points": points[:: max(1, len(points) // 90)] if points else [],
                }
            )
        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "period": period,
            "curves": curves,
            "disclaimer": "Uses *_hist duration-curve series — observational performance development.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/best-period-backtrace")
def get_best_period_backtrace(
    metric: str = Query("fitness.ef_30d"),
    period: str = Query("2y"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    """What did training look like before best historical periods?"""
    end = end_date or date.today()
    days = _period_days(period)
    start = end - timedelta(days=days - 1)
    short_to_mcp = {
        "ef": "fitness.ef_30d",
        "critical_speed": "running.critical_speed",
        "durability": "running.durability_score",
        "lt2": "running.critical_speed",
    }
    key = short_to_mcp.get(metric, metric)
    try:
        derived = McpDerivedMetricsService(db, storage)
        if not derived.metric_definition(key):
            raise HTTPException(status_code=400, detail=f"Unsupported metric: {metric}")
        result = derived.query_timeseries(key, start_date=start, end_date=end, limit=days + 5)
        points = [
            {
                "date": date.fromisoformat(str(p.get("date") or p.get("activity_date"))[:10]),
                "value": float(p["value"]),
            }
            for p in (result.get("points") or [])
            if p.get("value") is not None
        ]
        if len(points) < 8:
            return {
                "metric": key,
                "status": "insufficient",
                "best_periods": [],
                "note": "Too few samples for best-period backtrace.",
            }
        ranked = sorted(points, key=lambda p: p["value"], reverse=True)
        selected: List[Dict[str, Any]] = []
        for peak in ranked:
            if any(abs((peak["date"] - s["peak_date"]).days) < 28 for s in selected):
                continue
            blocks = []
            for weeks in (4, 8, 12):
                block_end = peak["date"] - timedelta(days=1)
                block_start = block_end - timedelta(days=weeks * 7 - 1)
                weeks_rows = (
                    db.query(WeeklySummary)
                    .filter(
                        WeeklySummary.week_start_date >= block_start - timedelta(days=7),
                        WeeklySummary.week_end_date <= block_end + timedelta(days=7),
                    )
                    .order_by(WeeklySummary.week_start_date.asc())
                    .all()
                )
                if not weeks_rows:
                    blocks.append(
                        {
                            "weeks": weeks,
                            "status": "insufficient",
                            "sample_weeks": 0,
                        }
                    )
                    continue
                total_duration = sum(float(w.total_duration or 0) for w in weeks_rows)
                total_tss = sum(float(w.total_tss or 0) for w in weeks_rows)
                total_distance = sum(float(w.total_distance or 0) for w in weeks_rows)
                activity_count = sum(int(w.total_activities or 0) for w in weeks_rows)
                blocks.append(
                    {
                        "weeks": weeks,
                        "status": "ok",
                        "sample_weeks": len(weeks_rows),
                        "total_duration_seconds": round(total_duration, 1),
                        "total_tss": round(total_tss, 2),
                        "total_distance_meters": round(total_distance, 1),
                        "activity_count": activity_count,
                        "avg_weekly_duration_seconds": round(
                            total_duration / max(1, len(weeks_rows)), 1
                        ),
                    }
                )
            selected.append(
                {
                    "peak_date": peak["date"],
                    "peak_value": round(peak["value"], 4),
                    "preceding_blocks": blocks,
                    "wording": (
                        f"Training structure in the weeks before the {peak['date'].isoformat()} "
                        f"peak — descriptive, not causal."
                    ),
                }
            )
            if len(selected) >= 3:
                break
        for s in selected:
            s["peak_date"] = s["peak_date"].isoformat()
        return {
            "metric": key,
            "status": "ok",
            "period": period,
            "best_periods": selected,
            "disclaimer": (
                "Shows preceding training structure before historically strong periods. "
                "Not causal attribution."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/change-aligned")
def get_change_aligned(
    metric: str = Query("fitness.ef_30d"),
    period: str = Query("1y"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    """Compare training in 6 weeks before a fitness change vs prior 6 weeks."""
    end = end_date or date.today()
    days = _period_days(period)
    window = _window_key(min(days, 365))
    window_days = int(window.replace("d", ""))
    legacy = {
        "fitness.ef_30d": "easy_run_efficiency",
        "running.critical_speed": "critical_speed",
        "running.durability_score": "durability",
        "fitness.ctl": "ctl",
    }.get(metric, metric)
    try:
        trends = TrendAnalysisService(db, storage).analyze_all(
            end_date=end, windows=(window_days,)
        )
        block = ((trends.get("metrics") or {}).get(legacy) or {}).get(window) or {}
        if not block.get("change_point_detected"):
            return {
                "metric": metric,
                "status": "no_change_point",
                "wording": "No meaningful change point detected in the selected window.",
                "comparison": None,
            }
        change_day = end - timedelta(days=window_days // 2)
        before_end = change_day - timedelta(days=1)
        before_start = before_end - timedelta(days=41)
        prior_end = before_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=41)

        def _week_stats(a: date, b: date) -> Dict[str, Any]:
            rows = (
                db.query(WeeklySummary)
                .filter(
                    WeeklySummary.week_start_date >= a - timedelta(days=7),
                    WeeklySummary.week_end_date <= b + timedelta(days=7),
                )
                .all()
            )
            if not rows:
                return {"status": "insufficient", "sample_weeks": 0}
            return {
                "status": "ok",
                "sample_weeks": len(rows),
                "total_duration_seconds": round(
                    sum(float(w.total_duration or 0) for w in rows), 1
                ),
                "total_tss": round(sum(float(w.total_tss or 0) for w in rows), 2),
                "activity_count": sum(int(w.total_activities or 0) for w in rows),
            }

        return {
            "metric": metric,
            "status": "ok",
            "change_approx_date": change_day.isoformat(),
            "direction": block.get("direction"),
            "comparison": {
                "preceding_6_weeks": _week_stats(before_start, before_end),
                "prior_6_weeks": _week_stats(prior_start, prior_end),
            },
            "wording": "Changes observed before the improvement — not causal attribution.",
            "disclaimer": "Change date is approximate from trend window midpoint.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/recommend-outcomes")
def get_recommend_outcomes(x: str = Query(...)) -> Dict[str, Any]:
    return {
        "predictor": x,
        "recommended_outcomes": recommended_outcomes_for(x),
        "metric": get_analytics_metric(x),
    }


@router.get("/highlights")
def get_highlights(
    period: str = Query("1y"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    end = end_date or date.today()
    try:
        window_days = 90 if _period_days(period) >= 90 else 28
        trends = TrendAnalysisService(db, storage).analyze_all(
            end_date=end,
            windows=(window_days,),
        )
        highlights: List[Dict[str, Any]] = []
        for metric, windows in (trends.get("metrics") or {}).items():
            block = windows.get("90d") or windows.get("28d") or windows.get("365d")
            if not block:
                continue
            if block.get("change_point_detected"):
                highlights.append(
                    {
                        "type": "change_point",
                        "metric": metric,
                        "direction": block.get("direction"),
                        "relative_change_pct": block.get("relative_change_pct"),
                        "evidence": _evidence_label(
                            block.get("confidence"), int(block.get("sample_count") or 0)
                        ),
                        "summary": (
                            f"{metric.replace('_', ' ')} shows a detected change "
                            f"({block.get('direction')}) over the window."
                        ),
                    }
                )
            elif block.get("direction") in {"improving", "declining"} and (
                block.get("sample_count") or 0
            ) >= 8:
                highlights.append(
                    {
                        "type": "trend",
                        "metric": metric,
                        "direction": block.get("direction"),
                        "relative_change_pct": block.get("relative_change_pct"),
                        "evidence": _evidence_label(
                            block.get("confidence"), int(block.get("sample_count") or 0)
                        ),
                        "summary": (
                            f"{metric.replace('_', ' ')}: {block.get('direction')} "
                            f"({block.get('relative_change_pct')}%)."
                        ),
                    }
                )
        return {
            "date": end.isoformat(),
            "period": period,
            "highlights": highlights[:12],
            "disclaimer": "Exploratory highlights from trend service — not coaching prescriptions.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
