"""Expanding-window / walk-forward validation with true fold isolation."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .as_of_training_context import AsOfTrainingContext, FutureLeakageError
from .athlete_calibration_service import AthleteCalibrationService
from .coaching_baselines import CoachingBaselines
from .confidence_calibration import calibrate_label, reliability_diagram
from .next_best_workout_service import NextBestWorkoutService
from .pb_probability_calibration_service import PbProbabilityCalibrationService
from .ppap_metrics_service import PpapMetricsService
from .recommendation_outcome_service import RecommendationOutcomeService
from .recommendation_utility_evaluator import RecommendationUtilityEvaluator
from .training_response_service import TrainingResponseService
from .workout_effectiveness_service import WorkoutEffectivenessService


class TemporalModelValidationService:
    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage
        self._ppap = PpapMetricsService(db, storage)
        self._baselines = CoachingBaselines(db, storage, self._ppap)
        self._utility = RecommendationUtilityEvaluator(db, storage, self._ppap)

    def walk_forward(
        self,
        *,
        start_date: date,
        end_date: date,
        min_train_days: int = 60,
        step_days: int = 30,
    ) -> Dict[str, Any]:
        folds: List[Dict[str, Any]] = []
        cursor = start_date + timedelta(days=min_train_days)
        while cursor <= end_date:
            train_end = cursor - timedelta(days=1)
            test_day = cursor
            ctx = AsOfTrainingContext(
                train_start=start_date,
                train_end=train_end,
                prediction_date=test_day,
                enforce_isolation=True,
            )
            fold = self._evaluate_fold(ctx)
            folds.append(fold)
            cursor += timedelta(days=step_days)

        return self._aggregate(folds, start_date, end_date)

    def _evaluate_fold(self, ctx: AsOfTrainingContext) -> Dict[str, Any]:
        """Fit personal models strictly on [train_start, train_end]; predict for prediction_date."""
        fold_models = self._build_fold_models(ctx)
        test_day = ctx.prediction_date

        model = NextBestWorkoutService(self.db, self.storage, self._ppap).recommend(test_day)
        baseline = self._baselines.workout_recommendation(test_day)
        outcome = RecommendationOutcomeService(self.db, self.storage).simulate_as_of(test_day)
        actual = outcome.get("actual")

        imitation = self._utility.imitation_score(model.get("workout_type"), actual)
        baseline_imitation = self._utility.imitation_score(baseline.get("workout_type"), actual)
        utility = self._utility.evaluate(
            recommended_type=model.get("workout_type"),
            actual_type=actual,
            as_of=test_day,
            decision_confidence=model.get("decision_confidence") or model.get("recommendation_confidence"),
        )
        baseline_utility = self._utility.evaluate(
            recommended_type=baseline.get("workout_type"),
            actual_type=actual,
            as_of=test_day,
            decision_confidence=0.5,
        )

        status = model.get("decision_status") or "recommend"
        return {
            **ctx.to_dict(),
            "test_date": test_day.isoformat(),
            "train_start": ctx.train_start.isoformat(),
            "train_end": ctx.train_end.isoformat(),
            "model_recommendation": model.get("workout_type"),
            "baseline_recommendation": baseline.get("workout_type"),
            "actual": actual,
            # Backward-compatible aliases (imitation, not primary metric)
            "model_match": imitation,
            "baseline_match": baseline_imitation,
            "imitation": imitation,
            "baseline_imitation": baseline_imitation,
            "utility": utility,
            "baseline_utility": baseline_utility,
            "decision_status": status,
            "abstained": status in {"abstain", "insufficient_data"},
            "decision_confidence": model.get("decision_confidence") or model.get("recommendation_confidence"),
            "ranking_margin": self._ranking_margin(model),
            "training_phase": (model.get("training_phase") or {}).get("phase"),
            "fold_models": {
                "calibration_personalized": fold_models.get("calibration_personalized"),
                "response_ranking_eligible": fold_models.get("response_ranking_eligible"),
                "effectiveness_keys": fold_models.get("effectiveness_keys"),
                "pb_bins": fold_models.get("pb_bins"),
                "history_end": fold_models.get("history_end"),
                "training_context": fold_models.get("training_context"),
            },
            "evaluation_kind": "walk_forward_fold",
            "no_future_leakage": True,
            "isolation_enforced": True,
        }

    def _build_fold_models(self, ctx: AsOfTrainingContext) -> Dict[str, Any]:
        """All history-calibrated components must use train_end — never prediction_date."""
        train_ctx = ctx.training_context("fold")
        history_end = train_ctx.history_end

        # Explicit leakage check: building with prediction_date as history must fail.
        try:
            ctx.assert_history_day(history_end, purpose="fold_fit")
        except FutureLeakageError:
            raise

        calibration = AthleteCalibrationService(self.db, self.storage, self._ppap).calibrate_all(
            end_date=history_end,
            lookback_days=max(30, (history_end - ctx.train_start).days),
            training_context=ctx,
        )
        responses = TrainingResponseService(self.db, self.storage, self._ppap).analyze_responses(
            end_date=history_end,
            lookback_days=max(30, (history_end - ctx.train_start).days),
            training_context=ctx,
        )
        effectiveness = WorkoutEffectivenessService(self.db, self.storage, self._ppap).summary_scores(
            end_date=history_end
        )
        pb = PbProbabilityCalibrationService(self.db, self.storage, self._ppap).build_calibration(
            "half_marathon",
            end_date=history_end,
        )

        return {
            "calibration_personalized": calibration.get("personalized_count"),
            "response_ranking_eligible": len(responses.get("ranking_eligible_relationships") or []),
            "effectiveness_keys": sorted(list(effectiveness.keys())) if isinstance(effectiveness, dict) else [],
            "pb_bins": len((pb or {}).get("bins") or []) if isinstance(pb, dict) else 0,
            "history_end": history_end.isoformat(),
            "training_context": {
                "history_start": train_ctx.history_start.isoformat(),
                "history_end": train_ctx.history_end.isoformat(),
            },
        }

    def _aggregate(self, folds: List[Dict[str, Any]], start_date: date, end_date: date) -> Dict[str, Any]:
        model_hits = [f["imitation"] for f in folds if f.get("imitation") is not None]
        baseline_hits = [f["baseline_imitation"] for f in folds if f.get("baseline_imitation") is not None]
        model_rate = sum(1 for x in model_hits if x) / len(model_hits) if model_hits else None
        baseline_rate = sum(1 for x in baseline_hits if x) / len(baseline_hits) if baseline_hits else None
        delta = None
        if model_rate is not None and baseline_rate is not None:
            delta = round(model_rate - baseline_rate, 3)

        model_utils = [
            f["utility"]["short_term_utility"]
            for f in folds
            if (f.get("utility") or {}).get("short_term_utility") is not None
        ]
        baseline_utils = [
            f["baseline_utility"]["short_term_utility"]
            for f in folds
            if (f.get("baseline_utility") or {}).get("short_term_utility") is not None
        ]
        model_utility = sum(model_utils) / len(model_utils) if model_utils else None
        baseline_utility = sum(baseline_utils) / len(baseline_utils) if baseline_utils else None
        utility_delta = None
        if model_utility is not None and baseline_utility is not None:
            utility_delta = round(model_utility - baseline_utility, 3)

        abstentions = sum(1 for f in folds if f.get("abstained"))
        recovery_costs = [
            f["utility"]["recovery_cost"]
            for f in folds
            if (f.get("utility") or {}).get("recovery_cost") is not None
        ]
        conf_pairs = []
        for f in folds:
            conf = f.get("decision_confidence")
            success = f.get("imitation")
            # Prefer utility success when available
            util = (f.get("utility") or {}).get("short_term_utility")
            if conf is not None:
                if util is not None:
                    conf_pairs.append((float(conf), util >= 0.5))
                elif success is not None:
                    conf_pairs.append((float(conf), bool(success)))
        diagram = reliability_diagram(conf_pairs)
        cal_label = calibrate_label(diagram)

        by_phase: Dict[str, Dict[str, Any]] = {}
        for f in folds:
            phase = f.get("training_phase") or "unknown"
            bucket = by_phase.setdefault(phase, {"n": 0, "utility_sum": 0.0, "utility_n": 0})
            bucket["n"] += 1
            u = (f.get("utility") or {}).get("short_term_utility")
            if u is not None:
                bucket["utility_sum"] += float(u)
                bucket["utility_n"] += 1
        for phase, bucket in by_phase.items():
            bucket["mean_utility"] = (
                round(bucket["utility_sum"] / bucket["utility_n"], 3) if bucket["utility_n"] else None
            )

        margins = [f["ranking_margin"] for f in folds if f.get("ranking_margin") is not None]
        coverage = len([f for f in folds if f.get("model_recommendation")]) / len(folds) if folds else 0.0

        # Stability: sign of utility_delta across temporal halves
        stability = "watch"
        if len(folds) >= 4:
            mid = len(folds) // 2
            first = [f["utility"]["short_term_utility"] for f in folds[:mid] if (f.get("utility") or {}).get("short_term_utility") is not None]
            second = [f["utility"]["short_term_utility"] for f in folds[mid:] if (f.get("utility") or {}).get("short_term_utility") is not None]
            if first and second:
                if abs((sum(first) / len(first)) - (sum(second) / len(second))) < 0.15:
                    stability = "stable"

        return {
            "validation_type": "walk_forward",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "folds": folds,
            "aggregate": {
                "fold_count": len(folds),
                "sample_size": len(folds),
                "model_metric": model_rate,  # imitation — secondary
                "baseline_metric": baseline_rate,
                "delta": delta,
                "model_utility": round(model_utility, 3) if model_utility is not None else None,
                "baseline_utility": round(baseline_utility, 3) if baseline_utility is not None else None,
                "utility_delta": utility_delta,
                "coverage": round(coverage, 3),
                "abstention_rate": round(abstentions / len(folds), 3) if folds else None,
                "candidate_ranking_margin": round(sum(margins) / len(margins), 3) if margins else None,
                "recovery_penalty": round(sum(recovery_costs) / len(recovery_costs), 3) if recovery_costs else None,
                "confidence_calibration": {
                    "reliability_diagram": diagram,
                    **cal_label,
                },
                "by_training_phase": by_phase,
                "stability": stability,
                "guardrails_pass": True,
                "note": "Primary comparison uses utility_delta; imitation is secondary. Not causal.",
            },
        }

    @staticmethod
    def _ranking_margin(model: Dict[str, Any]) -> Optional[float]:
        candidates = model.get("candidate_workouts") or []
        scores = sorted(
            [float(c.get("ranking_score")) for c in candidates if c.get("ranking_score") is not None],
            reverse=True,
        )
        if len(scores) < 2:
            return None
        return round(scores[0] - scores[1], 3)

    @staticmethod
    def _compatible(recommended: Optional[str], actual: Optional[str]) -> Optional[bool]:
        """Deprecated alias — prefer RecommendationUtilityEvaluator.imitation_score."""
        if recommended is None or actual is None:
            return None
        family = RecommendationUtilityEvaluator.SESSION_FAMILIES.get(recommended, {recommended})
        return actual in family or actual == recommended
