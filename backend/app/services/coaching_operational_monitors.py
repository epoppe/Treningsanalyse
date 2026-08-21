"""Operational monitors: confidence, abstention, distribution, churn, latency, shadow readiness."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import (
    RecommendationExecution,
    RecommendationRecord,
    ShadowRecommendation,
    TrainingPlanVersion,
)
from ..database.models.sleep import HRV, RestingHeartRate, Sleep
from ..database.models.sync_state import SyncState
from .coaching_config import (
    CONFIDENCE_BIN_MIN_N,
    PLAN_CHURN_OVERREACTIVE_14D,
    RECOMMENDATION_CHURN_SAME_DAY,
    SHADOW_READINESS_MIN_N,
)
from .plan_stability import PlanStabilityService
from .recommendation_utility_evaluator import RecommendationUtilityEvaluator
from .sample_sufficiency_policy import SampleSufficiencyPolicy
from .shadow_outcome_evaluation_service import ShadowOutcomeEvaluationService


class DecisionConfidenceMonitor:
    def __init__(self, db: Session):
        self.db = db
        self._utility = RecommendationUtilityEvaluator(db)

    def assess(self, *, start: date, end: date) -> Dict[str, Any]:
        recs = (
            self.db.query(RecommendationRecord)
            .filter(
                RecommendationRecord.as_of_date >= start,
                RecommendationRecord.as_of_date <= end,
                RecommendationRecord.decision_confidence.isnot(None),
            )
            .all()
        )
        exec_map = {
            e.recommendation_id: e
            for e in self.db.query(RecommendationExecution).all()
            if e.recommendation_id
        }
        bins: Dict[str, List[float]] = defaultdict(list)
        for r in recs:
            ex = exec_map.get(r.id)
            if not ex:
                continue
            util = self._utility.evaluate(
                recommended_type=r.recommended_workout_type,
                actual_type=ex.actual_type,
                as_of=r.as_of_date,
                decision_confidence=r.decision_confidence,
            )
            success = util.get("short_term_utility")
            if success is None:
                continue
            conf = float(r.decision_confidence)
            key = f"{int(conf * 10) / 10:.1f}-{int(conf * 10) / 10 + 0.1:.1f}"
            bins[key].append(float(success))

        out_bins = []
        statuses = []
        for key, vals in sorted(bins.items()):
            n = len(vals)
            emp = mean(vals)
            mid = float(key.split("-")[0]) + 0.05
            if n < CONFIDENCE_BIN_MIN_N:
                status = "insufficient_data"
            elif abs(emp - mid) <= 0.1:
                status = "well_calibrated"
            elif emp < mid - 0.1:
                status = "overconfident"
            else:
                status = "underconfident"
            statuses.append(status)
            out_bins.append(
                {
                    "bin": key,
                    "n": n,
                    "predicted_mid": round(mid, 2),
                    "empirical_success": round(emp, 3),
                    "status": status,
                }
            )

        overall = "insufficient_data"
        if out_bins and all(b["status"] != "insufficient_data" for b in out_bins):
            if any(b["status"] == "overconfident" for b in out_bins):
                overall = "overconfident"
            elif any(b["status"] == "underconfident" for b in out_bins):
                overall = "underconfident"
            else:
                overall = "well_calibrated"
        elif any(b["status"] != "insufficient_data" for b in out_bins):
            material = [b["status"] for b in out_bins if b["status"] != "insufficient_data"]
            overall = Counter(material).most_common(1)[0][0]

        return {
            "sample_count": sum(b["n"] for b in out_bins),
            "bins": out_bins,
            "status": overall,
            "note": "No automatic recalibration from small samples.",
        }


class AbstentionQualityService:
    def assess(self, db: Session, *, start: date, end: date) -> Dict[str, Any]:
        recs = (
            db.query(RecommendationRecord)
            .filter(RecommendationRecord.as_of_date >= start, RecommendationRecord.as_of_date <= end)
            .all()
        )
        n = len(recs)
        abstain = [
            r
            for r in recs
            if (r.decision_status or "") in {"abstain", "insufficient_data"}
        ]
        rate = (len(abstain) / n) if n else None
        contexts = Counter()
        for r in abstain:
            dq = r.data_quality_score
            if dq is not None and dq < 0.45:
                contexts["low_data_quality"] += 1
            else:
                contexts["other"] += 1

        if n < 10:
            status = "INSUFFICIENT_DATA"
        elif rate is not None and rate < 0.02:
            status = "TOO_RARE"
        elif rate is not None and rate > 0.35:
            status = "TOO_FREQUENT"
        else:
            status = "APPROPRIATE"

        return {
            "sample_count": n,
            "abstention_count": len(abstain),
            "abstention_rate": round(rate, 3) if rate is not None else None,
            "contexts": dict(contexts),
            "status": status,
            "note": "Do not optimize abstention rate toward zero.",
        }


class RecommendationDistributionMonitor:
    TYPES = ("easy_run", "long_run", "threshold", "vo2_intervals", "rest", "strength", "cycling")

    def assess(self, db: Session, *, start: date, end: date, prior_start: Optional[date] = None) -> Dict[str, Any]:
        prior_start = prior_start or (start - (end - start))
        current = self._counts(db, start, end)
        prior = self._counts(db, prior_start, start - timedelta(days=1))
        shifts = {}
        for t in self.TYPES:
            c = current.get(t, 0)
            p = prior.get(t, 0)
            if p == 0 and c == 0:
                continue
            ratio = None if p == 0 else round(c / p, 2)
            shifts[t] = {"current": c, "prior": p, "ratio": ratio, "flag": ratio is not None and ratio >= 2.0}

        return {
            "sample_count": sum(current.values()),
            "current": current,
            "prior": prior,
            "shifts": shifts,
            "unexpected_shift": any(v.get("flag") for v in shifts.values()),
            "note": "Monitoring only — not automatic rollback.",
        }

    @staticmethod
    def _counts(db: Session, start: date, end: date) -> Dict[str, int]:
        rows = (
            db.query(RecommendationRecord)
            .filter(RecommendationRecord.as_of_date >= start, RecommendationRecord.as_of_date <= end)
            .all()
        )
        return dict(Counter(r.recommended_workout_type or "unknown" for r in rows))


class ModelChangeImpactService:
    def compare(
        self,
        db: Session,
        *,
        before_start: date,
        before_end: date,
        after_start: date,
        after_end: date,
    ) -> Dict[str, Any]:
        dist = RecommendationDistributionMonitor()
        before = dist.assess(db, start=before_start, end=before_end)
        after = dist.assess(db, start=after_start, end=after_end)
        abs_svc = AbstentionQualityService().assess(db, start=after_start, end=after_end)
        n = before["sample_count"] + after["sample_count"]
        if before["sample_count"] < 10 or after["sample_count"] < 10:
            verdict = "insufficient_evidence"
        elif after.get("unexpected_shift"):
            verdict = "possible_regression"
        elif abs_svc["status"] == "TOO_FREQUENT":
            verdict = "possible_regression"
        elif not after.get("unexpected_shift"):
            verdict = "no_material_change"
        else:
            verdict = "consistent_with_improvement"

        return {
            "sample_count": n,
            "before": before,
            "after": after,
            "abstention_after": abs_svc,
            "verdict": verdict,
            "note": "Not a causal claim of improvement.",
        }


class ShadowPromotionReadinessService:
    def assess(self, db: Session, *, start: date, end: date) -> Dict[str, Any]:
        shadows = (
            db.query(ShadowRecommendation)
            .filter(ShadowRecommendation.as_of_date >= start, ShadowRecommendation.as_of_date <= end)
            .all()
        )
        n = len(shadows)
        sufficiency = SampleSufficiencyPolicy().assess(
            domain="shadow_comparison",
            sample_count=n,
            observation_dates=[s.as_of_date for s in shadows],
            as_of=end,
        )
        eval_range = ShadowOutcomeEvaluationService(db).evaluate_range(start=start, end=end)
        wins = sum(
            1 for row in (eval_range.get("comparisons") or []) if row.get("shadow_plausible_better")
        )
        compared = len(eval_range.get("comparisons") or [])

        if n < SHADOW_READINESS_MIN_N or not sufficiency["may_override_defaults"]:
            status = "NOT_READY"
        elif compared >= 15 and wins / max(compared, 1) >= 0.55:
            status = "ELIGIBLE" if sufficiency["level"] == "STRONG" else "PROMISING"
        elif compared >= 10:
            status = "PROMISING"
        else:
            status = "NOT_READY"

        return {
            "sample_count": n,
            "compared": compared,
            "shadow_wins": wins,
            "sufficiency": sufficiency,
            "status": status,
            "note": "Eligibility ≠ promotion. Use CoachingModelRegistry.promote + ValidationRun.",
        }


class PlanChurnMonitor:
    def assess(self, db: Session, *, as_of: Optional[date] = None, window_days: int = 14) -> Dict[str, Any]:
        as_of = as_of or date.today()
        stability = PlanStabilityService().from_history(db, as_of=as_of, window_days=window_days)
        versions = (
            db.query(TrainingPlanVersion)
            .filter(TrainingPlanVersion.created_at.isnot(None))
            .all()
        )
        reasons = Counter()
        material = minor = 0
        for v in versions:
            created = v.created_at.date() if isinstance(v.created_at, datetime) else None
            if created is None or created < as_of - timedelta(days=window_days):
                continue
            if v.changes_json:
                material += 1
            else:
                minor += 1
            reason = v.reason_json
            if isinstance(reason, dict):
                code = str(reason.get("code") or reason.get("reason") or "unknown")
            elif isinstance(reason, str):
                code = reason
            else:
                code = "unknown"
            # Classify noise-like reasons
            low = code.lower()
            if "hrv" in low or "sleep" in low:
                reasons["recovery_signal"] += 1
            elif "availability" in low:
                reasons["availability"] += 1
            elif "activity" in low or "execution" in low:
                reasons["new_activity"] += 1
            elif "threshold" in low or "marginal" in low:
                reasons["marginal_threshold"] += 1
            else:
                reasons[code] += 1

        status = stability.get("status")
        if status == "insufficient_data":
            flag = "INSUFFICIENT_DATA"
        elif (stability.get("plan_change_count_14d") or 0) >= PLAN_CHURN_OVERREACTIVE_14D:
            flag = "OVERREACTIVE"
        elif status == "adaptive":
            flag = "ADAPTIVE"
        else:
            flag = "STABLE"

        return {
            "sample_count": stability.get("history_points") or 0,
            "material_changes": material,
            "minor_changes": minor,
            "reason_counts": dict(reasons),
            "stability": stability,
            "status": flag,
            "note": "Flag repeated HRV/sleep noise replans as OVERREACTIVE when history is sufficient.",
        }


class RecommendationChurnMonitor:
    def assess(self, db: Session, *, day: date) -> Dict[str, Any]:
        rows = (
            db.query(RecommendationRecord)
            .filter(RecommendationRecord.as_of_date == day)
            .order_by(RecommendationRecord.generated_at.asc())
            .all()
        )
        types = [r.recommended_workout_type for r in rows]
        hashes = [r.decision_payload_hash or r.config_hash for r in rows]
        unique_types = len(set(types))
        changes = sum(1 for a, b in zip(types, types[1:]) if a != b)

        # Legitimate if new activity that day
        activity_n = (
            db.query(Activity)
            .filter(Activity.start_time >= datetime(day.year, day.month, day.day, tzinfo=timezone.utc))
            .filter(
                Activity.start_time
                < datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)
            )
            .count()
        )
        sleep_n = db.query(Sleep).filter(Sleep.sleep_date == day).count()

        if len(rows) < 2:
            status = "insufficient_data"
        elif changes >= RECOMMENDATION_CHURN_SAME_DAY and activity_n == 0 and sleep_n == 0:
            status = "churn_without_evidence"
        elif changes and (activity_n or sleep_n):
            status = "legitimate_change"
        else:
            status = "stable"

        return {
            "sample_count": len(rows),
            "unique_types": unique_types,
            "type_changes": changes,
            "payload_hashes": hashes,
            "new_activity_count": activity_n,
            "sleep_rows": sleep_n,
            "status": status,
            "note": "Do not count legitimate changes after activity/sleep/feedback/availability.",
        }


class DataLatencyMonitor:
    def assess(self, db: Session, *, as_of: Optional[datetime] = None) -> Dict[str, Any]:
        as_of = as_of or datetime.now(timezone.utc)
        sync = db.query(SyncState).order_by(SyncState.updated_at.desc()).first()
        last_sync = sync.last_synced_at if sync else None
        last_act = db.query(Activity.start_time).order_by(Activity.start_time.desc()).first()
        act_ts = last_act[0] if last_act else None
        last_sleep = db.query(Sleep.sleep_date).order_by(Sleep.sleep_date.desc()).first()
        sleep_day = last_sleep[0] if last_sleep else None

        def hours_between(a, b) -> Optional[float]:
            if a is None or b is None:
                return None
            if isinstance(a, date) and not isinstance(a, datetime):
                a = datetime(a.year, a.month, a.day, tzinfo=timezone.utc)
            if isinstance(b, date) and not isinstance(b, datetime):
                b = datetime(b.year, b.month, b.day, tzinfo=timezone.utc)
            if a.tzinfo is None:
                a = a.replace(tzinfo=timezone.utc)
            if b.tzinfo is None:
                b = b.replace(tzinfo=timezone.utc)
            return round((b - a).total_seconds() / 3600.0, 2)

        source_latency = hours_between(act_ts, as_of)
        sync_latency = hours_between(last_sync, as_of) if last_sync else None
        # Derivation ≈ time from sync to now when metrics would be built
        derivation_latency = sync_latency

        stale_local = False
        if sleep_day and last_sync:
            # Source sleep exists for a recent day but sync is >12h behind as_of
            if (as_of.date() - sleep_day).days <= 1 and sync_latency is not None and sync_latency > 12:
                stale_local = True

        return {
            "sample_count": 1 if last_sync or act_ts else 0,
            "source_latency_hours": source_latency,
            "sync_latency_hours": sync_latency,
            "derivation_latency_hours": derivation_latency,
            "last_activity_at": act_ts.isoformat() if act_ts else None,
            "last_sync_at": last_sync.isoformat() if last_sync else None,
            "last_sleep_date": sleep_day.isoformat() if sleep_day else None,
            "stale_local_despite_source": stale_local,
            "note": "Detects pipeline lag even when Garmin source data is valid.",
        }


class DataQualityTrendService:
    def assess(self, db: Session, *, end: date, window_days: int = 28) -> Dict[str, Any]:
        start = end - timedelta(days=window_days)
        days = [start + timedelta(days=i) for i in range(window_days + 1)]
        hrv = {r[0] for r in db.query(HRV.measurement_date).filter(HRV.measurement_date >= start).all()}
        sleep = {r[0] for r in db.query(Sleep.sleep_date).filter(Sleep.sleep_date >= start).all()}
        rhr = {
            r[0]
            for r in db.query(RestingHeartRate.measurement_date)
            .filter(RestingHeartRate.measurement_date >= start)
            .all()
        }
        acts = db.query(Activity).filter(Activity.start_time >= start.isoformat()).all()
        tss_n = sum(1 for a in acts if a.training_stress_score is not None or a.epoc is not None)

        def coverage(present: set) -> float:
            return round(len([d for d in days if d in present]) / max(len(days), 1), 3)

        return {
            "sample_count": len(days),
            "hrv_coverage": coverage(hrv),
            "sleep_coverage": coverage(sleep),
            "rhr_coverage": coverage(rhr),
            "tss_epoc_activity_share": round(tss_n / max(len(acts), 1), 3) if acts else 0.0,
            "activity_count": len(acts),
            "note": "Separates input-data degradation from model degradation.",
        }


class FeedbackValueService:
    def prioritize(self, *, context: Dict[str, Any]) -> Dict[str, Any]:
        score = 0
        reasons = []
        if context.get("unusual_recovery"):
            score += 2
            reasons.append("unusual_recovery")
        if context.get("modified_quality_session"):
            score += 2
            reasons.append("modified_quality")
        if context.get("is_race"):
            score += 2
            reasons.append("race")
        if context.get("new_prescription"):
            score += 1
            reasons.append("new_prescription")
        if context.get("shadow_disagreement"):
            score += 1
            reasons.append("shadow_disagreement")
        if context.get("unexpected_execution_quality"):
            score += 1
            reasons.append("unexpected_execution")

        if score >= 3:
            priority = "high_value"
        elif score >= 1:
            priority = "useful"
        else:
            priority = "none"
        return {
            "feedback_priority": priority,
            "reasons": reasons,
            "note": "Do not require feedback after every workout.",
        }
