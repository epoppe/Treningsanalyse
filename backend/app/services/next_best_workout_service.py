"""Neste beste økt — evidensbasert anbefaling med guardrails og alternativer."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .adaptive_threshold_service import AdaptiveThresholdService
from .coaching_decision_metrics_service import CoachingDecisionMetricsService
from .coaching_session_types import HARD_SESSION_TYPES, HARD_WORKOUT_TYPES
from .load_variability_service import LoadVariabilityService
from .metric_evidence import confidence_from_sample_count
from .ppap_metrics_service import PpapMetricsService
from .session_classifier_service import SessionClassifierService
from .trend_analysis_service import TrendAnalysisService

# Re-eksport for bakoverkompatibilitet (backtest, tester, etc.)
__all__ = ["HARD_SESSION_TYPES", "HARD_WORKOUT_TYPES", "NextBestWorkoutService"]

MIN_RECOVERY_HOURS_AFTER_HARD = 36


class NextBestWorkoutService:
    """Utvider coaching-beslutninger med session classification, trends og guardrails."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._decision = CoachingDecisionMetricsService(self.db, self._ppap)
        self._classifier = SessionClassifierService(self.db, storage)
        self._trends = TrendAnalysisService(self.db, storage)
        self._thresholds = AdaptiveThresholdService(self.db, storage)
        self._load_var = LoadVariabilityService(self.db, storage, self._ppap)

    def recommend(
        self,
        day: Optional[date] = None,
        *,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        day = day or date.today()
        context = self._build_context(day, include_treadmill=include_treadmill)
        workout_type, rationale, contraindications, decision_trace = self._decide(context)
        confidence = self._confidence(context, contraindications)
        duration_min, target_hr = self._targets(workout_type, context)
        alternative = self._alternative(context)

        return {
            "workout_type": workout_type,
            "duration_min": duration_min,
            "target_hr": target_hr,
            "target_pace": None,
            "priority": context.get("priority", "aerobic_volume"),
            "confidence": round(confidence, 2),
            "rationale": rationale,
            "contraindications": contraindications,
            "decision_trace": decision_trace,
            "decision": workout_type,
            "alternative": alternative,
            "load_variability": context.get("load_variability"),
            "context_summary": {
                "readiness": context.get("readiness"),
                "tsb": context.get("tsb"),
                "hard_days_7d": context.get("hard_days_7d"),
                "training_block": context.get("training_block"),
                "top_limiter": context.get("top_limiter"),
            },
        }

    def _build_context(self, day: date, *, include_treadmill: bool) -> Dict[str, Any]:
        readiness = self._ppap.get_readiness_component(day, "readiness.total_score")
        tsb = self._ppap.get_tsb(day)
        ctl = self._ppap.get_ctl(day)
        atl = self._ppap.get_atl(day)
        hrv_delta = self._ppap.get_hrv_delta_pct(day)
        sleep_debt = self._ppap.get_sleep_debt_hours(day, 7)
        block = self._decision.get_training_block(day)
        limiters = self._decision.get_limiting_factors(day)
        top_limiter = max(limiters, key=limiters.get) if limiters else None
        hard_days_7d, hard_days_14d = self._hard_day_counts(day, include_treadmill=include_treadmill)
        last_hard = self._last_hard_session(day, include_treadmill=include_treadmill)
        lt1 = self._thresholds.estimate_lt1(end_date=day, include_treadmill=include_treadmill)
        ctl_trend = self._trends.analyze_metric("ctl", end_date=day, window_days=28)
        load_variability = self._load_var.analyze(day)

        acwr = (float(atl) / float(ctl)) if ctl and atl and float(ctl) > 0 else None
        load_ratio = None
        if ctl is not None and atl is not None and float(ctl) > 0:
            load_ratio = float(atl) / float(ctl)

        return {
            "day": day,
            "readiness": float(readiness) if readiness is not None else None,
            "tsb": float(tsb) if tsb is not None else None,
            "ctl": float(ctl) if ctl is not None else None,
            "atl": float(atl) if atl is not None else None,
            "acwr": acwr,
            "load_ratio": load_ratio,
            "hrv_delta_pct": float(hrv_delta) if hrv_delta is not None else None,
            "sleep_debt_hours": float(sleep_debt) if sleep_debt is not None else None,
            "training_block": block,
            "limiters": limiters,
            "top_limiter": top_limiter,
            "hard_days_7d": hard_days_7d,
            "hard_days_14d": hard_days_14d,
            "last_hard_session": last_hard,
            "lt1_confidence": lt1.get("confidence", 0),
            "lt1_hr": lt1.get("lt1_hr"),
            "ctl_trend_direction": ctl_trend.get("direction"),
            "load_variability": load_variability,
            "include_treadmill": include_treadmill,
        }

    def _decide(self, ctx: Dict[str, Any]) -> Tuple[str, List[str], List[str], List[Dict[str, Any]]]:
        rationale: List[str] = []
        contraindications: List[str] = []
        trace: List[Dict[str, Any]] = []

        readiness = ctx.get("readiness")
        tsb = ctx.get("tsb")
        block = ctx.get("training_block")
        load_flags = (ctx.get("load_variability") or {}).get("flags", [])

        if readiness is not None:
            effect = "supports_training" if readiness >= 55 else "limits_intensity"
            if readiness < 35:
                effect = "requires_rest"
            trace.append({"factor": "readiness", "value": readiness, "effect": effect})

        if tsb is not None:
            effect = "supports_quality" if -8 <= tsb <= 12 else "limits_hard_work"
            if tsb < -25:
                effect = "requires_recovery"
            trace.append({"factor": "tsb", "value": tsb, "effect": effect})

        if ctx.get("hard_days_7d") is not None:
            effect = "blocks_hard_session" if ctx["hard_days_7d"] >= 2 else "allows_quality"
            trace.append(
                {
                    "factor": "hard_sessions_last_7d",
                    "value": ctx["hard_days_7d"],
                    "effect": effect,
                }
            )

        for flag in load_flags:
            trace.append({"factor": "load_variability", "value": flag, "effect": "favors_easy_or_recovery"})

        if readiness is not None and readiness < 35:
            rationale.append(f"readiness={readiness:.0f} indicates very low recovery")
            return "rest", rationale, contraindications, trace

        if tsb is not None and tsb < -25:
            rationale.append(f"TSB={tsb:.0f} suggests high accumulated fatigue")
            return "recovery_run", rationale, contraindications, trace

        if ctx.get("hrv_delta_pct") is not None and ctx["hrv_delta_pct"] < -15:
            contraindications.append("HRV significantly below baseline")
            rationale.append("HRV drop suggests incomplete recovery")
            trace.append(
                {
                    "factor": "hrv_delta_pct",
                    "value": ctx["hrv_delta_pct"],
                    "effect": "blocks_hard_session",
                }
            )
            return "easy_run", rationale, contraindications, trace

        if ctx.get("sleep_debt_hours") is not None and ctx["sleep_debt_hours"] > 8:
            rationale.append(f"sleep debt={ctx['sleep_debt_hours']:.1f}h")
            return "easy_run", rationale, contraindications, trace

        if "rapid_load_change" in load_flags or "monotonous_loading" in load_flags:
            rationale.append(f"load variability flags: {', '.join(load_flags)}")
            contraindications.append("avoid_compensatory_hard_session")
            return "easy_run", rationale, contraindications, trace

        if ctx.get("acwr") is not None and ctx["acwr"] > 1.4:
            rationale.append(f"ACWR={ctx['acwr']:.2f} — rapid load increase")
            contraindications.append("avoid_compensatory_hard_session")
            return "easy_run", rationale, contraindications, trace

        if block == "recovery":
            rationale.append("training block=recovery")
            return "recovery_run", rationale, contraindications, trace

        if block == "overload":
            rationale.append("training block=overload — prioritize absorption")
            return "easy_run", rationale, contraindications, trace

        last_hard = ctx.get("last_hard_session")
        if last_hard and ctx.get("hard_days_7d", 0) >= 1:
            hours_since = last_hard.get("hours_since", 999)
            if hours_since < MIN_RECOVERY_HOURS_AFTER_HARD:
                contraindications.append("hard_session_within_36h")
                rationale.append(
                    f"last hard session ({last_hard.get('session_type')}) "
                    f"{hours_since:.0f}h ago — guardrail: no back-to-back hard days"
                )
                trace.append(
                    {
                        "factor": "hours_since_hard",
                        "value": round(hours_since, 1),
                        "effect": "blocks_hard_session",
                    }
                )
                return "easy_run", rationale, contraindications, trace

        if ctx.get("hard_days_7d", 0) >= 3:
            rationale.append(f"{ctx['hard_days_7d']} hard days in last 7 — consolidate")
            return "easy_run", rationale, contraindications, trace

        ctx["priority"] = self._priority(ctx)
        trace.append(
            {
                "factor": "easy_volume_priority",
                "value": ctx["priority"],
                "effect": "supports_easy_volume" if ctx["priority"] == "aerobic_volume" else "supports_quality",
            }
        )

        if (
            readiness is not None
            and readiness >= 75
            and tsb is not None
            and 0 <= tsb <= 12
            and ctx.get("hard_days_7d", 0) <= 1
        ):
            rationale.append("good readiness and form window for quality")
            if ctx.get("top_limiter") == "vo2":
                return "vo2_intervals", rationale, contraindications, trace
            return "threshold", rationale, contraindications, trace

        if readiness is not None and readiness >= 65 and tsb is not None and -8 <= tsb <= 5:
            rationale.append("moderate readiness supports controlled quality")
            return "threshold", rationale, contraindications, trace

        consistency = self._decision.get_consistency_score(ctx["day"])
        if consistency is not None and consistency < 55:
            rationale.append(f"consistency={consistency:.0f}% — rebuild habit with easy volume")
            return "easy_run", rationale, contraindications, trace

        if ctx.get("ctl_trend_direction") == "declining" and block in {"base", "build"}:
            rationale.append("CTL trend declining — easy aerobic volume priority")
            return "easy_run", rationale, contraindications, trace

        rationale.append("default aerobic maintenance")
        return "easy_run", rationale, contraindications, trace

    def _priority(self, ctx: Dict[str, Any]) -> str:
        limiter = ctx.get("top_limiter")
        mapping = {
            "aerobic": "aerobic_volume",
            "threshold": "threshold_development",
            "vo2": "vo2_development",
            "fatigue": "recovery",
            "sleep": "recovery",
            "consistency": "consistency",
        }
        return mapping.get(limiter or "", "aerobic_volume")

    def _confidence(self, ctx: Dict[str, Any], contraindications: List[str]) -> float:
        signals = [
            ctx.get("readiness") is not None,
            ctx.get("tsb") is not None,
            ctx.get("hrv_delta_pct") is not None,
            ctx.get("lt1_confidence", 0) >= 0.5,
        ]
        base = confidence_from_sample_count(sum(1 for s in signals if s), min_samples=2, target_samples=4)
        if contraindications:
            base *= 0.85
        if ctx.get("readiness") is None:
            base *= 0.7
        return min(0.95, base)

    def _targets(
        self,
        workout_type: str,
        ctx: Dict[str, Any],
    ) -> Tuple[List[int], Optional[List[int]]]:
        lt1 = ctx.get("lt1_hr")
        if workout_type == "rest":
            return [0, 0], None
        if workout_type == "recovery_run":
            if lt1:
                return [30, 45], [int(lt1 * 0.75), int(lt1 * 0.85)]
            return [30, 45], None
        if workout_type == "easy_run":
            if lt1:
                return [45, 70], [int(lt1 * 0.85), int(lt1 * 0.95)]
            return [45, 70], None
        if workout_type == "long_run":
            if lt1:
                return [75, 120], [int(lt1 * 0.85), int(lt1 * 0.92)]
            return [75, 120], None
        if workout_type == "threshold":
            if lt1:
                return [45, 60], [int(lt1 * 0.95), int(lt1 * 1.05)]
            return [45, 60], None
        if workout_type == "vo2_intervals":
            return [50, 65], None
        return [45, 60], None

    def _alternative(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "workout_type": "rest",
            "trigger": "HRV falls >12% or resting HR rises >4 bpm vs baseline",
        }

    def _hard_day_counts(
        self,
        day: date,
        *,
        include_treadmill: bool,
    ) -> Tuple[int, int]:
        hard_7 = 0
        hard_14 = 0
        for offset in range(14):
            check_day = day - timedelta(days=offset)
            if self._day_has_hard_session(check_day, include_treadmill=include_treadmill):
                hard_14 += 1
                if offset < 7:
                    hard_7 += 1
        return hard_7, hard_14

    def _day_has_hard_session(self, day: date, *, include_treadmill: bool) -> bool:
        from sqlalchemy.orm import joinedload

        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(func.date(Activity.start_time) == day)
            .all()
        )
        for activity in activities:
            if not is_running_activity(activity, include_treadmill=include_treadmill):
                continue
            classification = self._classifier.classify_activity(
                activity,
                end_date=day,
                include_treadmill=include_treadmill,
            )
            if classification.get("session_type") in HARD_SESSION_TYPES:
                return True
        return False

    def _last_hard_session(
        self,
        day: date,
        *,
        include_treadmill: bool,
    ) -> Optional[Dict[str, Any]]:
        from sqlalchemy.orm import joinedload

        start = day - timedelta(days=7)
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= day,
                )
            )
            .order_by(Activity.start_time.desc())
            .all()
        )
        for activity in activities:
            if not is_running_activity(activity, include_treadmill=include_treadmill):
                continue
            classification = self._classifier.classify_activity(
                activity,
                end_date=day,
                include_treadmill=include_treadmill,
            )
            if classification.get("session_type") in HARD_SESSION_TYPES:
                if activity.start_time is None:
                    continue
                from datetime import datetime, timezone

                end_of_day = datetime(day.year, day.month, day.day, 23, 59, tzinfo=timezone.utc)
                start_ts = activity.start_time
                if start_ts.tzinfo is None:
                    start_ts = start_ts.replace(tzinfo=timezone.utc)
                hours = (end_of_day - start_ts).total_seconds() / 3600.0
                return {
                    "session_type": classification.get("session_type"),
                    "activity_id": activity.activity_id,
                    "hours_since": hours,
                }
        return None