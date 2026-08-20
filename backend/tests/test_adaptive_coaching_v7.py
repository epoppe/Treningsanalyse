"""Adaptive Coaching Engine v7 — fold isolation, ValidationRun promotion, periodization."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.database.models.coaching_v5 import ValidationRun
from app.services.as_of_training_context import AsOfTrainingContext, FutureLeakageError
from app.services.coaching_model_registry import CoachingModelRegistry
from app.services.confidence_calibration import calibrate_label, reliability_diagram
from app.services.freshness_policy import FreshnessPolicy
from app.services.load_progression_service import LoadProgressionService
from app.services.mesocycle_planner import MesocyclePlanner
from app.services.missingness import classify_signal
from app.services.ppap_metrics_service import PpapMetricsService
from app.services.recommendation_utility_evaluator import RecommendationUtilityEvaluator
from app.services.shadow_outcome_evaluation_service import ShadowOutcomeEvaluationService
from app.services.shadow_recommendation_service import ShadowRecommendationService
from app.services.taper_planner import TaperPlanner
from app.services.temporal_model_validation_service import TemporalModelValidationService
from app.services.validation_run_service import ValidationRunService


class AdaptiveCoachingV7Tests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'v7.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.running = ActivityType(type_key="running", type_name="Running")
        self.db.add(self.running)
        self.db.commit()
        self.ppap = PpapMetricsService(self.db, None)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_fold_isolation_future_data_does_not_alter_trained_fold(self):
        ctx = AsOfTrainingContext(
            train_start=date(2026, 1, 1),
            train_end=date(2026, 3, 31),
            prediction_date=date(2026, 4, 1),
        )
        with self.assertRaises(FutureLeakageError):
            ctx.assert_history_day(date(2026, 4, 15), purpose="calibration")

        calls = []

        def fake_calibrate_all(*, end_date=None, lookback_days=365, training_context=None):
            calls.append(end_date)
            self.assertEqual(end_date, date(2026, 3, 31))
            if training_context is not None:
                self.assertEqual(training_context.train_end, date(2026, 3, 31))
            return {"personalized_count": 0, "end_date": end_date.isoformat()}

        temporal = TemporalModelValidationService(self.db, None)
        with patch("app.services.temporal_model_validation_service.AthleteCalibrationService") as cal_cls:
            with patch("app.services.temporal_model_validation_service.TrainingResponseService") as resp_cls:
                with patch("app.services.temporal_model_validation_service.WorkoutEffectivenessService") as eff_cls:
                    with patch("app.services.temporal_model_validation_service.PbProbabilityCalibrationService") as pb_cls:
                        with patch("app.services.temporal_model_validation_service.NextBestWorkoutService") as nb_cls:
                            with patch("app.services.temporal_model_validation_service.RecommendationOutcomeService") as out_cls:
                                cal_cls.return_value.calibrate_all.side_effect = fake_calibrate_all
                                resp_cls.return_value.analyze_responses.return_value = {
                                    "ranking_eligible_relationships": []
                                }
                                eff_cls.return_value.summary_scores.return_value = {}
                                pb_cls.return_value.build_calibration.return_value = {"bins": []}
                                nb_cls.return_value.recommend.return_value = {
                                    "workout_type": "easy_run",
                                    "decision_confidence": 0.7,
                                    "decision_status": "recommend",
                                    "candidate_workouts": [
                                        {"ranking_score": 80},
                                        {"ranking_score": 70},
                                    ],
                                    "training_phase": {"phase": "build"},
                                }
                                out_cls.return_value.simulate_as_of.return_value = {"actual": "easy_aerobic"}
                                fold_a = temporal._evaluate_fold(ctx)

                                # Extreme future datapoint after train_end must not change fold fit end_date.
                                self.db.add(
                                    Activity(
                                        activity_id="future-huge",
                                        activity_name="Future Spike",
                                        start_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
                                        duration=20000,
                                        distance=50000,
                                        activity_type=self.running,
                                    )
                                )
                                self.db.commit()
                                fold_b = temporal._evaluate_fold(ctx)

        self.assertEqual(calls[0], date(2026, 3, 31))
        self.assertEqual(calls[1], date(2026, 3, 31))
        self.assertEqual(fold_a["model_recommendation"], fold_b["model_recommendation"])
        self.assertEqual(fold_a["fold_models"]["history_end"], "2026-03-31")
        self.assertEqual(fold_b["fold_models"]["history_end"], "2026-03-31")
        self.assertTrue(fold_a["isolation_enforced"])

    def test_imitation_vs_outcome_mismatch_not_automatic_failure(self):
        evaluator = RecommendationUtilityEvaluator(self.db, None, self.ppap)
        with patch.object(self.ppap, "get_hrv_delta_pct", return_value=2.0):
            with patch.object(self.ppap, "get_rhr_delta_bpm", return_value=-1.0):
                with patch.object(self.ppap, "get_tsb", return_value=5.0):
                    with patch.object(self.ppap, "get_ctl", return_value=50.0):
                        result = evaluator.evaluate(
                            recommended_type="threshold",
                            actual_type="easy_aerobic",
                            as_of=date(2026, 5, 1),
                            decision_confidence=0.6,
                        )
        self.assertIs(result["imitation"], False)
        self.assertTrue(result.get("plausible_better_despite_mismatch") or (result["short_term_utility"] or 0) >= 0.5)
        self.assertIn("not a causal counterfactual", result["note"])

    def test_promotion_requires_validation_run(self):
        reg = CoachingModelRegistry(self.db)
        reg.register(model_key="ranker", version="v7-1")
        with self.assertRaises(ValueError):
            reg.promote(
                model_key="ranker",
                version="v7-1",
                gate={"walk_forward": True, "baseline_delta": 0.1, "sample_size": 40, "stability": "stable", "guardrails_pass": True},
            )
        with self.assertRaises(ValueError):
            reg.promote(model_key="ranker", version="v7-1", validation_run_id=99999)

        # Incomplete / failing run cannot promote
        bad = ValidationRun(
            model_key="ranker",
            model_version="v7-1",
            config_hash="abc",
            data_start=date(2026, 1, 1),
            data_end=date(2026, 6, 1),
            metrics_json={
                "walk_forward": True,
                "baseline_delta": -0.1,
                "utility_delta": -0.1,
                "sample_size": 5,
                "stability": "unstable",
                "guardrails_pass": False,
            },
            sample_size=5,
            validation_code_version="v7.0.0",
            status="completed",
        )
        self.db.add(bad)
        self.db.commit()
        with self.assertRaises(ValueError):
            reg.promote(model_key="ranker", version="v7-1", validation_run_id=bad.id)

        good = ValidationRun(
            model_key="ranker",
            model_version="v7-1",
            config_hash="def",
            data_start=date(2026, 1, 1),
            data_end=date(2026, 6, 1),
            metrics_json={
                "walk_forward": True,
                "baseline_delta": 0.04,
                "utility_delta": 0.06,
                "sample_size": 40,
                "stability": "stable",
                "guardrails_pass": True,
            },
            sample_size=40,
            validation_code_version="v7.0.0",
            status="completed",
        )
        self.db.add(good)
        self.db.commit()
        promoted = reg.promote(model_key="ranker", version="v7-1", validation_run_id=good.id)
        self.assertEqual(promoted["status"], "active")
        self.assertEqual(promoted["validation_run_id"], good.id)
        self.assertEqual(promoted["promotion_gate"]["source"], "validation_run")

    def test_mesocycle_personalization_differs_by_load_history(self):
        planner = MesocyclePlanner(self.db, None, self.ppap)
        with patch.object(LoadProgressionService, "envelope", return_value={
            "current_load": 180.0,
            "supported_next_range": [180.0, 200.0],
            "upper_bound_source": "historical_tolerance",
            "n_weeks": 16,
            "n_tolerated_transitions": 8,
            "evidence_strength": 0.7,
        }):
            low = planner.plan(date(2026, 5, 1), weeks=4, compare_candidates=False)
        with patch.object(LoadProgressionService, "envelope", return_value={
            "current_load": 320.0,
            "supported_next_range": [320.0, 350.0],
            "upper_bound_source": "historical_tolerance",
            "n_weeks": 16,
            "n_tolerated_transitions": 10,
            "evidence_strength": 0.75,
        }):
            high = planner.plan(date(2026, 5, 1), weeks=4, compare_candidates=False)
        low_vol = low["mesocycle"][0]["target_volume"]
        high_vol = high["mesocycle"][0]["target_volume"]
        self.assertNotEqual(low_vol, high_vol)
        self.assertLess(sum(low_vol) / 2, sum(high_vol) / 2)
        self.assertIn("rationale_codes", low["mesocycle"][0])

    def test_taper_fallback_and_personalization(self):
        taper = TaperPlanner(self.db, None, self.ppap, goal={"goal_type": "race", "event": "half_marathon"})
        with patch.object(taper, "_personal_taper", return_value={"sample_count": 2}):
            low = taper.plan(date(2026, 5, 1))
        self.assertIn(low["source"], {"default", "default_fatigue_adjusted"})
        self.assertLess(low["sample_count"], 4)

        with patch.object(
            taper,
            "_personal_taper",
            return_value={
                "duration_days": 12,
                "volume_reduction_range": [0.32, 0.48],
                "sample_count": 5,
                "evidence_strength": 0.57,
            },
        ):
            personal = taper.plan(date(2026, 5, 1))
        self.assertEqual(personal["source"], "personal_history")
        self.assertEqual(personal["duration_days"], 12)
        self.assertEqual(personal["sample_count"], 5)

    def test_missing_hrv_not_negative(self):
        missing = classify_signal(None, negative_if_below=-10, name="hrv")
        negative = classify_signal(-15.0, negative_if_below=-10, name="hrv")
        self.assertEqual(missing["status"], "missing")
        self.assertFalse(missing["is_negative"])
        self.assertTrue(negative["is_negative"])

        freshness = FreshnessPolicy.assess("hrv_baseline", as_of=date(2026, 5, 1), age_days=None)
        self.assertEqual(freshness["freshness"], "missing")
        self.assertFalse(freshness.get("high_confidence_primary"))

    def test_shadow_never_affects_production_plan(self):
        shadow = ShadowRecommendationService(self.db).record_shadow(
            day=date(2026, 5, 19),
            production={"workout_type": "easy_run", "candidate_workouts": [
                {"workout_type": "easy_run", "eligible": True, "ranking_score": 70},
                {"workout_type": "threshold", "eligible": True, "ranking_score": 65},
            ]},
        )
        self.assertIsNotNone(shadow.get("shadow") or shadow.get("shadow_workout_type"))
        # No plan rows created by shadow
        from app.database.models.coaching_v5 import TrainingPlan

        self.assertEqual(self.db.query(TrainingPlan).count(), 0)
        eval_svc = ShadowOutcomeEvaluationService(self.db)
        with patch.object(eval_svc._outcomes, "simulate_as_of", return_value={"actual": "easy_aerobic"}):
            report = eval_svc.evaluate_range(start=date(2026, 5, 1), end=date(2026, 5, 30))
        self.assertEqual(report["shadow_active_plan_violations"], 0)
        self.assertGreaterEqual(report["n"], 1)

    def test_reproducibility_same_config_same_fingerprint(self):
        svc = ValidationRunService(self.db)
        with patch.object(svc._temporal, "walk_forward", return_value={
            "validation_type": "walk_forward",
            "folds": [
                {
                    "model_recommendation": "easy_run",
                    "imitation": True,
                    "utility": {"short_term_utility": 0.6},
                }
            ]
            * 4,
            "aggregate": {
                "fold_count": 4,
                "model_metric": 0.5,
                "baseline_metric": 0.4,
                "delta": 0.1,
                "model_utility": 0.6,
                "baseline_utility": 0.5,
                "utility_delta": 0.1,
                "coverage": 1.0,
                "abstention_rate": 0.0,
                "stability": "stable",
                "guardrails_pass": True,
                "confidence_calibration": {"reliability_diagram": []},
            },
        }):
            a = svc.create_walk_forward_run(
                model_key="ranker",
                model_version="v7",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 6, 1),
                config={"x": 1},
            )
            b = svc.create_walk_forward_run(
                model_key="ranker",
                model_version="v7",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 6, 1),
                config={"x": 1},
            )
        self.assertEqual(a["result_fingerprint"], b["result_fingerprint"])
        bundle = svc.export_reproducibility_bundle(a["id"])
        self.assertTrue(bundle["immutable"])
        self.assertIn("metric_definitions", bundle["bundle"])

    def test_confidence_calibration_diagram(self):
        pairs = [(0.75, False), (0.72, False), (0.78, True)] + [(0.55, True)] * 6
        diagram = reliability_diagram(pairs)
        self.assertTrue(any(b["bin"][0] == 0.7 for b in diagram))
        label = calibrate_label(diagram)
        self.assertIn(label["label"], {"decision_confidence", "decision_strength"})


if __name__ == "__main__":
    unittest.main()
