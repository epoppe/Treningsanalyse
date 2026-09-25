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
from .canonical_prospective_observation import CanonicalProspectiveObservationService
from .coaching_config import (
    PLAN_CHURN_OVERREACTIVE_14D,
    RECOMMENDATION_CHURN_SAME_DAY,
    SHADOW_READINESS_MIN_N,
)
from .outcome_maturity import is_usable_status
from .plan_stability import PlanStabilityService
from .recommendation_utility_evaluator import RecommendationUtilityEvaluator
from .sample_sufficiency_policy import DOMAIN_FLOORS, SampleSufficiencyPolicy
from .shadow_outcome_evaluation_service import ShadowOutcomeEvaluationService

# decision_confidence is the estimated probability of this binary target.
# The target is the observed short-term utility, not the confidence input itself.
FAVORABLE_SHORT_TERM_THRESHOLD = 0.55
CALIBRATION_ECE_TOLERANCE = 0.08


def favorable_from_utility(short_term_utility: Optional[float], maturity: Optional[str]) -> Optional[bool]:
    """True when a mature short-term utility clears the documented threshold."""
    if not is_usable_status(maturity) or short_term_utility is None:
        return None
    return float(short_term_utility) >= FAVORABLE_SHORT_TERM_THRESHOLD


def summarize_calibration(
    pairs: List[Tuple[float, bool]],
    *,
    considered: int,
    abstentions: int,
) -> Dict[str, Any]:
    """Brier, bins and ECE. Small n is INSUFFICIENT_DATA — never auto-recalibrated."""
    floors = DOMAIN_FLOORS["confidence_calibration"]
    sample_count = len(pairs)
    sufficiency = SampleSufficiencyPolicy().assess(
        domain="confidence_calibration",
        sample_count=sample_count,
    )
    bins: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    for confidence, favorable in pairs:
        clipped = min(0.999, max(0.0, float(confidence)))
        lower = int(clipped * 10) / 10
        key = f"{lower:.1f}-{lower + 0.1:.1f}"
        bins[key].append((clipped, 1.0 if favorable else 0.0))

    out_bins = []
    ece_mass = 0.0
    brier_total = 0.0
    for key, vals in sorted(bins.items()):
        n = len(vals)
        mean_p = mean(item[0] for item in vals)
        empirical = mean(item[1] for item in vals)
        ece_mass += (n / sample_count) * abs(mean_p - empirical) if sample_count else 0.0
        brier_total += sum((item[0] - item[1]) ** 2 for item in vals)
        out_bins.append(
            {
                "bin": key,
                "n": n,
                "predicted_mean": round(mean_p, 3),
                "empirical_frequency": round(empirical, 3),
                "gap": round(mean_p - empirical, 3),
            }
        )

    mean_confidence = mean(item[0] for item in pairs) if pairs else None
    favorable_rate = mean(1.0 if item[1] else 0.0 for item in pairs) if pairs else None
    brier = (brier_total / sample_count) if sample_count else None
    coverage = (sample_count / considered) if considered else None
    abstention_rate = (abstentions / considered) if considered else None

    if sample_count < floors["emerging"] or sufficiency["level"] == "INSUFFICIENT":
        status = "INSUFFICIENT_DATA"
    elif mean_confidence is None or favorable_rate is None:
        status = "INSUFFICIENT_DATA"
    elif mean_confidence - favorable_rate > CALIBRATION_ECE_TOLERANCE:
        status = "overconfident"
    elif favorable_rate - mean_confidence > CALIBRATION_ECE_TOLERANCE:
        status = "underconfident"
    elif ece_mass <= CALIBRATION_ECE_TOLERANCE:
        status = "well_calibrated"
    else:
        status = "overconfident" if mean_confidence > favorable_rate else "underconfident"

    return {
        "sample_count": sample_count,
        "effective_sample_count": sufficiency["effective_sample_count"],
        "spread_days": sufficiency["spread_days"],
        "level": sufficiency["level"],
        "bins": out_bins,
        "brier_score": round(brier, 4) if brier is not None else None,
        "expected_calibration_error": round(ece_mass, 4) if sample_count else None,
        "mean_confidence": round(mean_confidence, 3) if mean_confidence is not None else None,
        "favorable_rate": round(favorable_rate, 3) if favorable_rate is not None else None,
        "coverage": round(coverage, 3) if coverage is not None else None,
        "abstention_rate": round(abstention_rate, 3) if abstention_rate is not None else None,
        "favorable_outcome_definition": (
            f"favorable_outcome is true iff short_term_maturity is evaluated "
            f"and short_term_utility >= {FAVORABLE_SHORT_TERM_THRESHOLD}. "
            "decision_confidence is the estimated probability of that event. "
            "The target is not built from decision_confidence."
        ),
        "status": status,
        "note": "No automatic recalibration from small samples.",
        "sufficiency": sufficiency,
    }


_OUTCOME_MIN_N = DOMAIN_FLOORS["workout_effectiveness"]["emerging"]
_IMPROVEMENT_DELTA = 0.10


def impact_verdict(
    *,
    before_n: int,
    after_n: int,
    unexpected_shift: bool,
    abstention_status: str,
    before_favorable_rate: Optional[float],
    after_favorable_rate: Optional[float],
    before_outcome_n: int,
    after_outcome_n: int,
) -> str:
    """Improvement requires outcome evidence, not a change in recommendation mix."""
    if before_n < 10 or after_n < 10:
        return "insufficient_evidence"
    if unexpected_shift or abstention_status == "TOO_FREQUENT":
        return "possible_regression"
    has_outcome = (
        before_outcome_n >= _OUTCOME_MIN_N
        and after_outcome_n >= _OUTCOME_MIN_N
        and before_favorable_rate is not None
        and after_favorable_rate is not None
    )
    if not has_outcome:
        return "no_material_change"
    if after_favorable_rate >= before_favorable_rate + _IMPROVEMENT_DELTA:
        return "consistent_with_improvement"
    if before_favorable_rate >= after_favorable_rate + _IMPROVEMENT_DELTA:
        return "possible_regression"
    return "no_material_change"


class DecisionConfidenceMonitor:
    """Calibration of decision_confidence against a binary favorable outcome.

    decision_confidence means: estimated probability that the recommendation
    achieves the defined favorable outcome. It is not a utility forecast.
    """

    def __init__(self, db: Session):
        self.db = db
        self._utility = RecommendationUtilityEvaluator(db)
        self._canonical = CanonicalProspectiveObservationService(db)

    def assess(
        self,
        *,
        start: date,
        end: date,
        observations: Optional[List[Dict[str, Any]]] = None,
        utility_by_id: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if observations is None:
            observations = self._canonical.resolve(start=start, end=end, today=end)
        pairs: List[Tuple[float, bool]] = []
        abstentions = 0
        for observation in observations:
            if (observation.get("decision_status") or "") in {"abstain", "insufficient_data"}:
                abstentions += 1
            confidence = observation.get("decision_confidence")
            if confidence is None:
                continue
            if utility_by_id is not None:
                utility = utility_by_id.get(observation.get("recommendation_id"))
                if utility is None:
                    continue
            else:
                utility = self._utility.evaluate_for_observation(observation, today=end)
            favorable = favorable_from_utility(
                utility.get("short_term_utility"),
                utility.get("short_term_maturity"),
            )
            if favorable is None:
                continue
            pairs.append((float(confidence), favorable))
        return summarize_calibration(pairs, considered=len(observations), abstentions=abstentions)


class AbstentionQualityService:
    def assess(
        self,
        db: Session,
        *,
        start: date,
        end: date,
        observations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        recs = (
            observations
            if observations is not None
            else CanonicalProspectiveObservationService(db).resolve(start=start, end=end, today=end)
        )
        n = len(recs)
        abstain = [
            r
            for r in recs
            if (r.get("decision_status") or "") in {"abstain", "insufficient_data"}
        ]
        rate = (len(abstain) / n) if n else None
        contexts = Counter()
        for r in abstain:
            dq = r.get("data_quality_score")
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

    def assess(
        self,
        db: Session,
        *,
        start: date,
        end: date,
        prior_start: Optional[date] = None,
        current_observations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        prior_start = prior_start or (start - (end - start))
        if current_observations is None:
            current = self._counts(db, start, end)
        else:
            current = dict(
                Counter(r.get("recommended_workout_type") or "unknown" for r in current_observations)
            )
        prior = self._counts(db, prior_start, start - timedelta(days=1))
        shifts = {}
        for t in self.TYPES:
            c = current.get(t, 0)
            p = prior.get(t, 0)
            if p == 0 and c == 0:
                continue
            ratio = None if p == 0 else round(c / p, 2)
            # from_zero is visible. It is not `flag`: a new type must not
            # turn an outcome improvement into possible_regression.
            shifts[t] = {
                "current": c,
                "prior": p,
                "ratio": ratio,
                "from_zero": p == 0 and c > 0,
                "flag": ratio is not None and ratio >= 2.0,
            }

        return {
            "sample_count": sum(current.values()),
            "current": current,
            "prior": prior,
            "shifts": shifts,
            "unexpected_shift": any(v.get("flag") for v in shifts.values()),
            "types_from_zero": [name for name, row in shifts.items() if row.get("from_zero")],
            "note": (
                "Monitoring only — not automatic rollback. "
                "from_zero means the type was absent in the prior window. "
                "That is not an unexpected shift and does not block an outcome-based improvement."
            ),
        }

    @staticmethod
    def _counts(db: Session, start: date, end: date) -> Dict[str, int]:
        rows = CanonicalProspectiveObservationService(db).resolve(start=start, end=end, today=end)
        return dict(Counter(r.get("recommended_workout_type") or "unknown" for r in rows))


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
        before_outcome = self.outcome_evidence(db, start=before_start, end=before_end, today=after_end)
        after_outcome = self.outcome_evidence(db, start=after_start, end=after_end, today=after_end)
        verdict = impact_verdict(
            before_n=before["sample_count"],
            after_n=after["sample_count"],
            unexpected_shift=bool(after.get("unexpected_shift")),
            abstention_status=abs_svc["status"],
            before_favorable_rate=before_outcome["favorable_rate"],
            after_favorable_rate=after_outcome["favorable_rate"],
            before_outcome_n=before_outcome["sample_count"],
            after_outcome_n=after_outcome["sample_count"],
        )

        return {
            "sample_count": n,
            "before": before,
            "after": after,
            "abstention_after": abs_svc,
            "outcome_before": before_outcome,
            "outcome_after": after_outcome,
            "verdict": verdict,
            "note": (
                "Improvement requires a higher favorable-outcome rate with enough mature "
                "outcomes in both windows. A distribution shift alone is not improvement."
            ),
        }

    def outcome_evidence(
        self,
        db: Session,
        *,
        start: date,
        end: date,
        today: date,
    ) -> Dict[str, Any]:
        utility = RecommendationUtilityEvaluator(db)
        observations = CanonicalProspectiveObservationService(db).resolve(start=start, end=end, today=today)
        labels: List[bool] = []
        for observation in observations:
            assessed = utility.evaluate_for_observation(observation, today=today)
            favorable = favorable_from_utility(
                assessed.get("short_term_utility"),
                assessed.get("short_term_maturity"),
            )
            if favorable is None:
                continue
            labels.append(favorable)
        sufficiency = SampleSufficiencyPolicy().assess(
            domain="workout_effectiveness",
            sample_count=len(labels),
            observation_dates=None,
            as_of=today,
        )
        rate = (sum(1 for item in labels if item) / len(labels)) if labels else None
        return {
            "sample_count": len(labels),
            "favorable_rate": round(rate, 3) if rate is not None else None,
            "effective_sample_count": sufficiency["effective_sample_count"],
            "level": sufficiency["level"],
            "spread_days": sufficiency["spread_days"],
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
