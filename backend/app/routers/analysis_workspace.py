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
from ..services.training_response_service import TrainingResponseService
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
    {"domain": "fitness", "metric": "ctl", "label": "Form (CTL)"},
    {"domain": "threshold", "metric": "lactate_threshold_pace", "label": "Terskel"},
    {"domain": "aerobic_efficiency", "metric": "easy_run_efficiency", "label": "Aerob effektivitet"},
    {"domain": "durability", "metric": "durability", "label": "Holdbarhet"},
    {"domain": "training_load", "metric": "ctl", "label": "Treningsbelastning"},
    {"domain": "recovery", "metric": "hrv_rmssd", "label": "Restitusjon (HRV)"},
    {"domain": "consistency", "metric": "vo2max", "label": "VO₂max"},
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


@router.get("/development")
def get_development(
    period: str = Query("90d", description="28d|90d|6m|1y|2y|all"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    """Domain summary cards for the Utvikling tab."""
    end = end_date or date.today()
    days = _period_days(period)
    window = _window_key(min(days, 365))
    window_days = int(window.replace("d", ""))
    try:
        trends = TrendAnalysisService(db, storage).analyze_all(
            end_date=end,
            windows=(window_days,),
        )
        metrics = trends.get("metrics") or {}
        domains: List[Dict[str, Any]] = []
        for spec in DOMAIN_METRICS:
            metric_trends = metrics.get(spec["metric"]) or {}
            # Prefer requested window; fall back to largest available.
            block = metric_trends.get(window) or metric_trends.get("90d") or metric_trends.get("28d")
            if not block and metric_trends:
                block = next(iter(metric_trends.values()))
            if not block:
                domains.append(
                    {
                        **spec,
                        "direction": "uncertain",
                        "direction_label": "Usikker",
                        "relative_change_pct": None,
                        "current": None,
                        "sample_count": 0,
                        "confidence": 0.0,
                        "evidence": "insufficient",
                        "change_point_detected": False,
                    }
                )
                continue
            hib = bool(block.get("higher_is_better", True))
            domains.append(
                {
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
            )
        return {
            "date": end.isoformat(),
            "period": period,
            "period_days": days,
            "window": window,
            "domains": domains,
            "raw_metrics": metrics,
            "disclaimer": "Trends are observational summaries — not causal claims.",
            "available_metrics": sorted(METRIC_FETCHERS.keys()),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/timeseries")
def get_timeseries(
    metrics: str = Query("ctl,hrv_rmssd", description="Comma-separated metric keys"),
    period: str = Query("90d"),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage),
) -> Dict[str, Any]:
    end = end_date or date.today()
    days = _period_days(period)
    start = end - timedelta(days=days - 1)
    keys = [m.strip() for m in metrics.split(",") if m.strip()][:4]
    invalid = [k for k in keys if k not in METRIC_FETCHERS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown metrics: {invalid}. Allowed: {sorted(METRIC_FETCHERS)}",
        )
    try:
        svc = TrendAnalysisService(db, storage)
        series: Dict[str, Any] = {}
        for key in keys:
            points = svc.series_for_metric(key, start_date=start, end_date=end)
            series[key] = {
                "metric": key,
                "unit_note": "native units — not cross-normalized",
                "points": points,
                "sample_count": len(points),
                "missing_days_approx": max(0, days - len(points)),
            }
        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "period": period,
            "series": series,
            "note": "Metrics keep native units; plot on separate panels when incompatible.",
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
