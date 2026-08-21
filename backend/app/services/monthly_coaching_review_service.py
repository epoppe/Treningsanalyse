"""Monthly coaching review — evidence-backed operational summary."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from .coaching_config import MONTHLY_REVIEW_SPARSE_N
from .coaching_health_service import CoachingHealthService
from .coaching_integrity_service import CoachingIntegrityService
from .coaching_model_registry import CoachingModelRegistry
from .coaching_operational_monitors import (
    AbstentionQualityService,
    DataLatencyMonitor,
    DataQualityTrendService,
    DecisionConfidenceMonitor,
    PlanChurnMonitor,
    RecommendationDistributionMonitor,
    ShadowPromotionReadinessService,
)
from .ppap_metrics_service import PpapMetricsService
from .prospective_evidence_report_service import ProspectiveEvidenceReportService


def generate_monthly_coaching_review(
    db: Session,
    *,
    end: Optional[date] = None,
    days: int = 30,
) -> Dict[str, Any]:
    """Canonical monthly review answering the operational questions — no speculative model changes."""
    end = end or date.today()
    start = end - timedelta(days=days)
    ppap = PpapMetricsService(db, None)
    prospective = ProspectiveEvidenceReportService(db).report(start=start, end=end)
    n = prospective["recommendations"]["sample_count"]
    sparse = n < MONTHLY_REVIEW_SPARSE_N

    health = CoachingHealthService(db, ppap).report(end)
    integrity = CoachingIntegrityService(db).check()
    conf = DecisionConfidenceMonitor(db).assess(start=start, end=end)
    abstain = AbstentionQualityService().assess(db, start=start, end=end)
    dist = RecommendationDistributionMonitor().assess(db, start=start, end=end)
    plan = PlanChurnMonitor().assess(db, as_of=end, window_days=days)
    shadow = ShadowPromotionReadinessService().assess(db, start=start, end=end)
    latency = DataLatencyMonitor().assess(db)
    dq = DataQualityTrendService().assess(db, end=end, window_days=days)
    active = CoachingModelRegistry(db).get_active("ranker")

    ctl = ppap.get_ctl(end)
    tsb = ppap.get_tsb(end)

    do_not_change = [
        "Do not add a new predictive coaching model without ProspectiveEvidenceReport deficiency.",
        "Do not treat sparse samples as proof of stability or improvement.",
    ]
    if sparse:
        do_not_change.append("Sample too sparse for model changes — collect more prospective data.")
    if shadow["status"] != "ELIGIBLE":
        do_not_change.append("Shadow model is not ELIGIBLE — do not promote.")
    if conf["status"] in {"overconfident", "insufficient_data"}:
        do_not_change.append("Confidence calibration not proven — do not tune confidence blindly.")

    answers = {
        "1_training_completed": {
            "executed": prospective["recommendations"].get("executed"),
            "modified": prospective["recommendations"].get("modified"),
            "sample_count": n,
        },
        "2_what_was_recommended": {
            "by_type": prospective["recommendations"].get("by_type"),
            "distribution": dist.get("current"),
            "sample_count": dist["sample_count"],
        },
        "3_followed_or_modified": {
            "adherence": prospective["execution"].get("adherence"),
            "executed": prospective["recommendations"].get("executed"),
            "modified": prospective["recommendations"].get("modified"),
            "skipped": prospective["recommendations"].get("skipped"),
            "sample_count": prospective["execution"]["sample_count"],
        },
        "4_recovery_behaviour": {
            "recovery_cost": prospective["outcomes"].get("recovery_cost"),
            "sample_count": prospective["outcomes"]["sample_count"],
        },
        "5_fitness_moving": {
            "ctl": ctl,
            "tsb": tsb,
            "sample_count": 1 if ctl is not None else 0,
            "note": "Point-in-time — not a causal trend claim.",
        },
        "6_plan_stable": {
            "status": plan.get("status"),
            "sample_count": plan["sample_count"],
        },
        "7_personalization_evidence": prospective["personalization"],
        "8_model_drift_or_regression": {
            "health_status": health.get("status"),
            "confidence_status": conf.get("status"),
            "unexpected_distribution_shift": dist.get("unexpected_shift"),
            "sample_count": conf["sample_count"],
        },
        "9_shadow_promising": {
            "status": shadow.get("status"),
            "sample_count": shadow["sample_count"],
        },
        "10_what_should_not_change": do_not_change,
    }

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "sparse_data": sparse,
        "active_model": active,
        "prospective": prospective,
        "health": {"status": health.get("status"), "issues": health.get("issues")},
        "integrity": {"status": integrity.get("status")},
        "abstention": abstain,
        "latency": latency,
        "data_quality_trend": dq,
        "answers": answers,
        "note": "Evidence-backed operational review — no speculative coaching changes recommended.",
    }
