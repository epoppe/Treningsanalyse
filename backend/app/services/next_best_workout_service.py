"""Neste beste økt — evidensbasert anbefaling med kalibrerte terskler og ranking."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .adaptive_threshold_service import AdaptiveThresholdService
from .athlete_calibration_service import AthleteCalibrationService
from .coaching_decision_metrics_service import CoachingDecisionMetricsService
from .coaching_session_types import HARD_SESSION_TYPES, HARD_WORKOUT_TYPES
from .goal_context_service import GoalContextService
from .intensity_prescription_service import IntensityPrescriptionService
from .load_variability_service import LoadVariabilityService
from .metric_evidence import confidence_from_sample_count
from .ppap_metrics_service import PpapMetricsService
from .race_capability_service import RaceCapabilityService
from .session_classifier_service import SessionClassifierService
from .session_quality_service import EASY_TYPES
from .training_phase_service import TrainingPhaseService
from .trend_analysis_service import TrendAnalysisService
from .workout_candidate_ranker import WorkoutCandidateRanker
from .workout_prescription_service import WorkoutPrescriptionService

# Re-eksport for bakoverkompatibilitet (backtest, tester, etc.)
__all__ = ["HARD_SESSION_TYPES", "HARD_WORKOUT_TYPES", "NextBestWorkoutService"]

MIN_RECOVERY_HOURS_AFTER_HARD = 36


class NextBestWorkoutService:
    """Utvider coaching-beslutninger med personlig kalibrering, fase og ranking."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
        goal: Optional[Dict[str, Any]] = None,
    ):
        self.db = db
        self.storage = storage
        self._goal_override = goal
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._decision = CoachingDecisionMetricsService(self.db, self._ppap)
        self._classifier = SessionClassifierService(self.db, storage)
        self._trends = TrendAnalysisService(self.db, storage)
        self._thresholds = AdaptiveThresholdService(self.db, storage)
        self._load_var = LoadVariabilityService(self.db, storage, self._ppap)
        self._calibration = AthleteCalibrationService(self.db, storage, self._ppap)
        self._intensity = IntensityPrescriptionService(self.db, storage, self._ppap)
        self._goals = GoalContextService(self.db, storage, self._ppap, goal=goal)
        self._phase = TrainingPhaseService(self.db, storage, self._ppap, goal=goal)
        self._race = RaceCapabilityService(self.db, storage, self._ppap, goal=goal)
        self._ranker = WorkoutCandidateRanker()
        self._prescription = WorkoutPrescriptionService(self.db, storage, self._ppap)
        self._cal_cache: Dict[date, Dict[str, Dict[str, Any]]] = {}

    def recommend(
        self,
        day: Optional[date] = None,
        *,
        include_treadmill: bool = False,
        engine: str = "auto",
        goal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        day = day or date.today()
        context = self._build_context(day, include_treadmill=include_treadmill, goal=goal)
        workout_type, rationale, contraindications, decision_trace = self._decide(context)
        evidence_strength = self._evidence_strength(context, contraindications)
        context["evidence_strength"] = evidence_strength

        ranking = self._ranker.rank(context)
        used_engine = "cascade"
        rec_conf = evidence_strength
        if engine in {"auto", "ranked"} and not ranking.get("use_rule_fallback"):
            selected = ranking.get("selected")
            if selected:
                workout_type = selected
                used_engine = "ranked"
                rec_conf = float(ranking.get("recommendation_confidence") or evidence_strength)
                rationale = list(rationale) + [f"ranked among eligible: {ranking.get('ranked_eligible')}"]
                decision_trace.append(
                    {
                        "factor": "candidate_ranking",
                        "value": selected,
                        "effect": "selected_eligible_workout",
                        "close_race": ranking.get("close_race"),
                    }
                )
        elif ranking.get("use_rule_fallback"):
            rationale = list(rationale) + ["ranking evidence insufficient — rule cascade fallback"]

        if ranking.get("close_race"):
            rec_conf = min(rec_conf, rec_conf * 0.85)

        phase_name = (context.get("training_phase") or {}).get("phase")
        prescription = self._prescription.prescribe(
            workout_type,
            day=day,
            phase=phase_name,
            include_treadmill=include_treadmill,
        )
        duration_min, target_hr, target_pace = self._targets(workout_type, context, prescription)
        alternative = self._alternative(context)

        return {
            "workout_type": workout_type,
            "duration_min": duration_min,
            "target_hr": target_hr,
            "target_pace": target_pace,
            "priority": context.get("priority", "aerobic_volume"),
            "confidence": round(rec_conf, 2),
            "evidence_strength": round(evidence_strength, 2),
            "recommendation_confidence": round(rec_conf, 2),
            "rationale": rationale,
            "contraindications": contraindications,
            "decision_trace": decision_trace,
            "decision": workout_type,
            "alternative": alternative,
            "load_variability": context.get("load_variability"),
            "workout_prescription": prescription,
            "candidate_workouts": ranking.get("candidates"),
            "decision_engine": used_engine,
            "goal": context.get("goal"),
            "training_phase": context.get("training_phase"),
            "race_capability": {
                "event": (context.get("race_capability") or {}).get("event"),
                "primary_gap": (context.get("race_capability") or {}).get("primary_gap"),
            },
            "context_summary": {
                "readiness": context.get("readiness"),
                "tsb": context.get("tsb"),
                "hard_days_7d": context.get("hard_days_7d"),
                "training_block": context.get("training_block"),
                "top_limiter": context.get("top_limiter"),
                "acwr_diagnostic": context.get("acwr"),
            },
        }

    def _params(self, day: date) -> Dict[str, Dict[str, Any]]:
        if day not in self._cal_cache:
            calibration = self._calibration.calibrate_all(end_date=day, lookback_days=90)
            self._cal_cache[day] = self._calibration.resolve_parameters(
                end_date=day,
                calibration=calibration,
            )
        return self._cal_cache[day]

    def _build_context(
        self,
        day: date,
        *,
        include_treadmill: bool,
        goal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        readiness = self._ppap.get_readiness_component(day, "readiness.total_score")
        tsb = self._ppap.get_tsb(day)
        ctl = self._ppap.get_ctl(day)
        atl = self._ppap.get_atl(day)
        hrv_delta = self._ppap.get_hrv_delta_pct(day)
        rhr_delta = self._ppap.get_rhr_delta_bpm(day)
        sleep_debt = self._ppap.get_sleep_debt_hours(day, 7)
        block = self._decision.get_training_block(day)
        limiters = self._decision.get_limiting_factors(day)
        top_limiter = max(limiters, key=limiters.get) if limiters else None
        hard_days_7d, hard_days_14d = self._hard_day_counts(day, include_treadmill=include_treadmill)
        last_hard = self._last_hard_session(day, include_treadmill=include_treadmill)
        lt1 = self._thresholds.estimate_lt1(end_date=day, include_treadmill=include_treadmill)
        ctl_trend = self._trends.analyze_metric("ctl", end_date=day, window_days=28)
        load_variability = self._load_var.analyze(day)
        params = self._params(day)
        goal_ctx = self._goals.build(day, goal=goal or self._goal_override)
        phase = self._phase.determine(day, goal=goal or self._goal_override)
        race = self._race.assess(day, goal=goal or self._goal_override)

        acwr = (float(atl) / float(ctl)) if ctl and atl and float(ctl) > 0 else None
        load_ratio = acwr
        rapid_ratio = load_variability.get("rapid_load_ratio_vs_prior_window")

        hours_since = last_hard.get("hours_since") if last_hard else None
        spacing = params["hard_session_spacing_hours"]
        hrv_warn = params["hrv_drop_warning_pct"]
        rhr_warn = params["rhr_rise_warning_bpm"]
        tsb_range = params["tsb_hard_session_range"]
        tsb_lo, tsb_hi = self._range_values(tsb_range)
        load_inc = params["load_increase_ratio_caution"]

        rest_required = readiness is not None and readiness < 35
        recovery_required = tsb is not None and tsb < -25
        hard_blocked = False
        if hours_since is not None and hours_since < float(spacing["value"]):
            hard_blocked = True
        if hrv_delta is not None and hrv_delta < float(hrv_warn["value"]):
            hard_blocked = True
        if rhr_delta is not None and rhr_delta > float(rhr_warn["value"]):
            hard_blocked = True
        if hard_days_7d >= 3:
            hard_blocked = True
        flags = load_variability.get("flags") or []
        if "high_hard_session_density" in flags or "inadequate_recovery_spacing" in flags:
            hard_blocked = True
        if rapid_ratio is not None and float(rapid_ratio) >= float(load_inc["value"]):
            hard_blocked = True

        return {
            "day": day,
            "readiness": float(readiness) if readiness is not None else None,
            "tsb": float(tsb) if tsb is not None else None,
            "ctl": float(ctl) if ctl is not None else None,
            "atl": float(atl) if atl is not None else None,
            "acwr": acwr,
            "load_ratio": load_ratio,
            "hrv_delta_pct": float(hrv_delta) if hrv_delta is not None else None,
            "rhr_delta_bpm": float(rhr_delta) if rhr_delta is not None else None,
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
            "params": params,
            "goal": goal_ctx,
            "training_phase": phase,
            "race_capability": race,
            "hard_blocked": hard_blocked,
            "rest_required": rest_required,
            "recovery_required": recovery_required,
            "tsb_lo": tsb_lo,
            "tsb_hi": tsb_hi,
            "easy_volume_7d": self._easy_volume_minutes(day, 7, include_treadmill=include_treadmill),
        }

    def _decide(self, ctx: Dict[str, Any]) -> Tuple[str, List[str], List[str], List[Dict[str, Any]]]:
        rationale: List[str] = []
        contraindications: List[str] = []
        trace: List[Dict[str, Any]] = []
        params = ctx.get("params") or {}

        readiness = ctx.get("readiness")
        tsb = ctx.get("tsb")
        block = ctx.get("training_block")
        phase = (ctx.get("training_phase") or {}).get("phase") or block
        load_flags = (ctx.get("load_variability") or {}).get("flags", [])
        tsb_lo = ctx.get("tsb_lo", -8.0)
        tsb_hi = ctx.get("tsb_hi", 12.0)
        spacing = params.get("hard_session_spacing_hours") or {}
        hrv_warn = params.get("hrv_drop_warning_pct") or {}
        rhr_warn = params.get("rhr_rise_warning_bpm") or {}
        easy_target = params.get("easy_volume_min_min_per_week") or {}
        density = params.get("threshold_density_max_pct") or {}
        load_inc = params.get("load_increase_ratio_caution") or {}

        if readiness is not None:
            effect = "supports_training" if readiness >= 55 else "limits_intensity"
            if readiness < 35:
                effect = "requires_rest"
            trace.append({"factor": "readiness", "value": readiness, "effect": effect})

        if tsb is not None:
            effect = "supports_quality" if tsb_lo <= tsb <= tsb_hi else "limits_hard_work"
            if tsb < -25:
                effect = "requires_recovery"
            tsb_param = params.get("tsb_hard_session_range") or {}
            trace.append(self._trace("tsb", tsb, tsb_param, effect))

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

        rapid = (ctx.get("load_variability") or {}).get("rapid_load_ratio_vs_prior_window")
        if rapid is not None and load_inc:
            effect = "limits_hard_work" if rapid >= float(load_inc.get("value") or 1.5) else "allows_quality"
            trace.append(self._trace("rapid_load_change", rapid, load_inc, effect))

        # ACWR beholdes kun diagnostisk — ikke primær guardrail.
        if ctx.get("acwr") is not None:
            trace.append(
                {
                    "factor": "acwr_diagnostic",
                    "value": round(ctx["acwr"], 2),
                    "effect": "diagnostic_only_not_primary_guardrail",
                    "threshold_source": "not_used_for_decision",
                }
            )

        if ctx.get("rest_required"):
            rationale.append(f"readiness={readiness:.0f} indicates very low recovery")
            return "rest", rationale, contraindications, trace

        if ctx.get("recovery_required"):
            rationale.append(f"TSB={tsb:.0f} suggests high accumulated fatigue")
            return "recovery_run", rationale, contraindications, trace

        if ctx.get("hrv_delta_pct") is not None and hrv_warn:
            effect = (
                "blocks_hard_session"
                if ctx["hrv_delta_pct"] < float(hrv_warn.get("value") or -12)
                else "allows_quality"
            )
            trace.append(self._trace("hrv_delta_pct", ctx["hrv_delta_pct"], hrv_warn, effect))
            if effect == "blocks_hard_session":
                contraindications.append("HRV significantly below personalized/default warning")
                rationale.append("HRV drop suggests incomplete recovery")
                return "easy_run", rationale, contraindications, trace

        if ctx.get("rhr_delta_bpm") is not None and rhr_warn:
            effect = (
                "blocks_hard_session"
                if ctx["rhr_delta_bpm"] > float(rhr_warn.get("value") or 4)
                else "allows_quality"
            )
            trace.append(self._trace("rhr_delta_bpm", ctx["rhr_delta_bpm"], rhr_warn, effect))
            if effect == "blocks_hard_session":
                contraindications.append("RHR elevated vs baseline")
                return "easy_run", rationale, contraindications, trace

        if ctx.get("sleep_debt_hours") is not None and ctx["sleep_debt_hours"] > 8:
            rationale.append(f"sleep debt={ctx['sleep_debt_hours']:.1f}h")
            return "easy_run", rationale, contraindications, trace

        if "rapid_load_change" in load_flags or "monotonous_loading" in load_flags:
            rationale.append(f"load variability flags: {', '.join(load_flags)}")
            contraindications.append("avoid_compensatory_hard_session")
            return "easy_run", rationale, contraindications, trace

        if "high_hard_session_density" in load_flags:
            rationale.append("high hard-session density — quality deferred")
            contraindications.append("high_hard_session_density")
            return "easy_run", rationale, contraindications, trace

        if phase == "recovery" or block == "recovery":
            rationale.append(f"training phase/block={phase or block}")
            return "recovery_run", rationale, contraindications, trace

        if block == "overload":
            rationale.append("training block=overload — prioritize absorption")
            return "easy_run", rationale, contraindications, trace

        last_hard = ctx.get("last_hard_session")
        if last_hard and ctx.get("hard_days_7d", 0) >= 1:
            hours_since = last_hard.get("hours_since", 999)
            threshold_h = float(spacing.get("value") or MIN_RECOVERY_HOURS_AFTER_HARD)
            effect = "blocks_hard_session" if hours_since < threshold_h else "allows_quality"
            trace.append(self._trace("hard_session_spacing", round(hours_since, 1), spacing, effect))
            if hours_since < threshold_h:
                contraindications.append("hard_session_within_spacing")
                rationale.append(
                    f"last hard session ({last_hard.get('session_type')}) "
                    f"{hours_since:.0f}h ago — spacing {threshold_h:.0f}h "
                    f"({spacing.get('threshold_source')})"
                )
                return "easy_run", rationale, contraindications, trace

        if ctx.get("hard_days_7d", 0) >= 3:
            rationale.append(f"{ctx['hard_days_7d']} hard days in last 7 — consolidate")
            return "easy_run", rationale, contraindications, trace

        easy_vol = ctx.get("easy_volume_7d")
        if easy_vol is not None and easy_target.get("value") is not None:
            weekly_target = float(easy_target["value"])
            # 7d volume vs weekly target (scaled)
            effect = "supports_easy_volume" if easy_vol < weekly_target * 0.6 else "volume_on_track"
            trace.append(self._trace("easy_volume_7d", easy_vol, easy_target, effect))

        ctx["priority"] = self._priority(ctx)
        trace.append(
            {
                "factor": "easy_volume_priority",
                "value": ctx["priority"],
                "effect": "supports_easy_volume" if ctx["priority"] == "aerobic_volume" else "supports_quality",
            }
        )

        gap = (ctx.get("race_capability") or {}).get("primary_gap")
        if (
            readiness is not None
            and readiness >= 75
            and tsb is not None
            and tsb_lo <= tsb <= tsb_hi
            and ctx.get("hard_days_7d", 0) <= 1
            and not ctx.get("hard_blocked")
        ):
            rationale.append("good readiness and form window for quality")
            if ctx.get("top_limiter") == "vo2" or gap == "vo2":
                return "vo2_intervals", rationale, contraindications, trace
            if phase == "taper":
                return "race_pace", rationale, contraindications, trace
            return "threshold", rationale, contraindications, trace

        if (
            readiness is not None
            and readiness >= 65
            and tsb is not None
            and tsb_lo <= tsb <= min(tsb_hi, 5)
            and not ctx.get("hard_blocked")
        ):
            rationale.append("moderate readiness supports controlled quality")
            return "threshold", rationale, contraindications, trace

        consistency = self._decision.get_consistency_score(ctx["day"])
        if consistency is not None and consistency < 55:
            rationale.append(f"consistency={consistency:.0f}% — rebuild habit with easy volume")
            return "easy_run", rationale, contraindications, trace

        if ctx.get("ctl_trend_direction") == "declining" and (phase or block) in {"base", "build"}:
            rationale.append("CTL trend declining — easy aerobic volume priority")
            return "easy_run", rationale, contraindications, trace

        if density.get("value") is not None:
            trace.append(self._trace("threshold_density_ceiling", density.get("value"), density, "informational"))

        rationale.append("default aerobic maintenance")
        return "easy_run", rationale, contraindications, trace

    @staticmethod
    def _trace(factor: str, value: Any, param: Dict[str, Any], effect: str) -> Dict[str, Any]:
        return {
            "factor": factor,
            "value": value,
            "threshold": param.get("value"),
            "threshold_source": param.get("threshold_source", "default"),
            "confidence": param.get("confidence"),
            "effect": effect,
        }

    @staticmethod
    def _range_values(param: Dict[str, Any]) -> Tuple[float, float]:
        value = param.get("value") or param.get("default_value") or [-8.0, 12.0]
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return float(value[0]), float(value[1])
        return -8.0, 12.0

    def _priority(self, ctx: Dict[str, Any]) -> str:
        limiter = ctx.get("top_limiter")
        gap = (ctx.get("race_capability") or {}).get("primary_gap")
        mapping = {
            "aerobic": "aerobic_volume",
            "threshold": "threshold_development",
            "vo2": "vo2_development",
            "fatigue": "recovery",
            "sleep": "recovery",
            "consistency": "consistency",
            "durability": "durability",
            "race_specific_endurance": "long_run",
        }
        return mapping.get(gap or "", mapping.get(limiter or "", "aerobic_volume"))

    def _evidence_strength(self, ctx: Dict[str, Any], contraindications: List[str]) -> float:
        signals = [
            ctx.get("readiness") is not None,
            ctx.get("tsb") is not None,
            ctx.get("hrv_delta_pct") is not None,
            ctx.get("lt1_confidence", 0) >= 0.5,
        ]
        base = confidence_from_sample_count(sum(1 for s in signals if s), min_samples=2, target_samples=4)
        if contraindications:
            base *= 0.9
        if ctx.get("readiness") is None:
            base *= 0.7
        return min(0.95, base)

    def _targets(
        self,
        workout_type: str,
        ctx: Dict[str, Any],
        prescription: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[int], Optional[List[int]], Optional[List[int]]]:
        intensity = self._intensity.prescribe(
            workout_type,
            end_date=ctx["day"],
            include_treadmill=ctx.get("include_treadmill", False),
        )
        main = (prescription or {}).get("main_set") or {}
        total = (prescription or {}).get("total_duration_min")
        if isinstance(total, (int, float)) and total > 0:
            duration = [max(20, int(total) - 10), int(total) + 10]
        elif workout_type == "rest":
            duration = [0, 0]
        else:
            duration = [45, 60]
        target_hr = intensity.get("hr_bpm") or main.get("target_hr")
        target_pace = intensity.get("pace_sec_km") or main.get("target_pace_sec_km")
        return duration, target_hr, target_pace

    def _alternative(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        hrv = (ctx.get("params") or {}).get("hrv_drop_warning_pct") or {}
        rhr = (ctx.get("params") or {}).get("rhr_rise_warning_bpm") or {}
        hrv_v = hrv.get("value", -12)
        rhr_v = rhr.get("value", 4)
        return {
            "workout_type": "rest",
            "trigger": (
                f"HRV falls >{abs(float(hrv_v)):.0f}% or resting HR rises >{float(rhr_v):.0f} bpm vs baseline "
                f"({hrv.get('threshold_source', 'default')} thresholds)"
            ),
        }

    def _easy_volume_minutes(self, day: date, window: int, *, include_treadmill: bool) -> Optional[float]:
        start = day - timedelta(days=window - 1)
        total = 0.0
        found = False
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= day,
                )
            )
            .all()
        )
        for activity in activities:
            if not is_running_activity(activity, include_treadmill=include_treadmill) or not activity.duration:
                continue
            st = self._classifier.classify_activity(
                activity,
                end_date=day,
                include_treadmill=include_treadmill,
            ).get("session_type")
            if st in EASY_TYPES:
                total += float(activity.duration) / 60.0
                found = True
        return round(total, 1) if found else None

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
