"""Hardening tests for Adaptive Coaching Engine (post-v5): tx, idempotency, schemas, invariants."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.database.models.coaching_v5 import RecommendationExecution, RecommendationRecord, TrainingPlan
from app.schemas.coaching import DecisionStatus, ExecutionStatus, validate_snapshot, RecommendationSnapshotV1
from app.services.coaching_baselines import CoachingBaselines
from app.services.coaching_data_export_service import CoachingDataExportService
from app.services.coaching_model_registry import CoachingModelRegistry
from app.services.coaching_orchestrator import CoachingOrchestrator
from app.services.coaching_tx import coaching_transaction
from app.services.deload_need_service import DeloadNeedService
from app.services.mesocycle_planner import MesocyclePlanner
from app.services.ppap_metrics_service import PpapMetricsService
from app.services.query_budget import assert_query_budget, QueryBudgetExceeded
from app.services.recommendation_execution_service import RecommendationExecutionService
from app.services.recommendation_ledger_service import RecommendationLedgerService
from app.services.shadow_recommendation_service import ShadowRecommendationService
from app.services.statistical_uncertainty import bootstrap_ci, evidence_band
from app.services.taper_planner import TaperPlanner
from app.services.temporal_model_validation_service import TemporalModelValidationService
from app.services.training_availability_service import TrainingAvailabilityService
from app.services.training_plan_store import TrainingPlanStore
from app.services.weekly_plan_service import WeeklyPlanService


def _rec_payload(**overrides):
    payload = {
        "workout_type": "threshold",
        "recommendation_confidence": 0.72,
        "decision_confidence": 0.72,
        "evidence_strength": 0.7,
        "data_quality": 0.8,
        "decision_status": "recommend",
        "decision_trace": [{"factor": "hard_session_spacing", "threshold": 48}],
        "training_phase": {"phase": "build"},
        "goal": {"target_event": "half_marathon", "goal_type": "race"},
        "race_capability": {"primary_gap": "durability"},
        "workout_prescription": {
            "total_duration_min": 55,
            "main_set": {"repetitions": 3, "work_duration_min": 10, "target_hr": [158, 164]},
        },
        "candidate_workouts": [
            {"workout_type": "threshold", "eligible": True, "ranking_score": 80},
            {"workout_type": "easy_run", "eligible": True, "ranking_score": 70},
        ],
        "context_summary": {"readiness": 70, "tsb": 2, "as_of_date": "2026-05-19"},
        "decision_engine": "ranked",
    }
    payload.update(overrides)
    return payload


class CoachingHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.running = ActivityType(type_key="running", type_name="Running")
        self.db.add(self.running)
        self.db.commit()
        self.ppap = PpapMetricsService(self.db, None)
        self.ledger = RecommendationLedgerService(self.db)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def _activity(self, activity_id, day, *, duration=3300, hr=160, name="Run"):
        activity = Activity(
            activity_id=activity_id,
            activity_name=name,
            start_time=datetime(day.year, day.month, day.day, 8, tzinfo=timezone.utc),
            duration=duration,
            distance=10000,
            average_heart_rate=hr,
            average_speed=3.0,
            total_training_effect=3.5,
            training_stress_score=70,
            activity_type_id=self.running.id,
        )
        activity.activity_type = self.running
        self.db.add(activity)
        self.db.commit()
        return activity

    def test_atomic_live_decision_rolls_back_on_failure(self):
        store = TrainingPlanStore(self.db)
        with self.assertRaises(RuntimeError):
            with coaching_transaction(self.db):
                self.ledger.record_recommendation(
                    _rec_payload(),
                    as_of_date=date(2026, 5, 19),
                    persist=True,
                    commit=False,
                )
                store.persist_new_plan(
                    week_start=date(2026, 5, 19),
                    payload={"week_objective": "build", "sessions": [{"day_offset": 0, "type": "easy_run"}]},
                    commit=False,
                )
                raise RuntimeError("simulated failure")
        self.assertEqual(self.db.query(RecommendationRecord).count(), 0)
        self.assertEqual(self.db.query(TrainingPlan).count(), 0)

    def test_idempotent_recommendation_and_execution(self):
        first = self.ledger.record_recommendation(_rec_payload(), as_of_date=date(2026, 5, 19), persist=True)
        second = self.ledger.record_recommendation(_rec_payload(), as_of_date=date(2026, 5, 19), persist=True)
        self.assertTrue(second.get("idempotent_reuse"))
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.db.query(RecommendationRecord).count(), 1)

        activity = self._activity("dup-sync", date(2026, 5, 19), duration=55 * 60, hr=161)
        svc = RecommendationExecutionService(self.db, None)
        with patch.object(svc._classifier, "classify_activity", return_value={"session_type": "threshold"}):
            a = svc.link_activity(activity)
            b = svc.link_activity(activity)
        self.assertTrue(b.get("idempotent_reuse"))
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(
            self.db.query(RecommendationExecution)
            .filter(RecommendationExecution.activity_id == "dup-sync")
            .count(),
            1,
        )

    def test_plan_version_skips_identical_payload(self):
        store = TrainingPlanStore(self.db)
        plan = store.persist_new_plan(
            week_start=date(2026, 5, 18),
            payload={"week_objective": "build", "sessions": [{"day_offset": 0, "type": "easy_run"}]},
        )
        again = store.append_version(
            plan["plan_id"],
            sessions=[{"day_offset": 0, "type": "easy_run"}],
            week_objective="build",
        )
        self.assertTrue(again.get("idempotent_reuse"))
        self.assertEqual(again["version"], 1)

    def test_schema_validation_degrades_invalid_legacy(self):
        degraded = validate_snapshot(RecommendationSnapshotV1, {"oops": True})
        self.assertTrue(degraded.get("degraded"))
        self.assertEqual(degraded.get("schema_version"), 1)
        ok = validate_snapshot(RecommendationSnapshotV1, {"workout_type": "easy_run"})
        self.assertFalse(ok.get("degraded"))
        self.assertEqual(ok["workout_type"], "easy_run")

    def test_uncertainty_semantics_separated(self):
        orch = CoachingOrchestrator(self.db, None)
        with patch.object(orch, "_build", wraps=None):
            pass
        with patch("app.services.coaching_orchestrator.NextBestWorkoutService.recommend") as rec:
            rec.return_value = _rec_payload()
            with patch("app.services.coaching_orchestrator.CoachingModelHealthService.assess") as health:
                health.return_value = {"status": "healthy", "warnings": [], "checks": {"hrv_delta_present": True, "ctl_present": True}}
                with patch("app.services.coaching_orchestrator.AthleteStateService.build_state") as state:
                    state.return_value = {"recovery": {"value": 70, "trend": "stable"}, "fitness": {"value": 50}}
                    with patch("app.services.coaching_orchestrator.WeeklyPlanService.build") as weekly:
                        weekly.return_value = {
                            "plan_id": None,
                            "version": None,
                            "week_objective": "build",
                            "sessions": [{"day_offset": 0, "type": "easy_run"}],
                            "simulation": {},
                        }
                        with patch("app.services.coaching_orchestrator.PlanAdaptationService.assess") as adapt:
                            adapt.return_value = {"plan_status": "keep", "changes": [], "reason": []}
                            brief = orch.preview_decision(date(2026, 5, 19), detail="concise")
        rec_payload = brief["recommendation"]
        self.assertIn("data_quality", rec_payload)
        self.assertIn("evidence_strength", rec_payload)
        self.assertIn("decision_confidence", rec_payload)
        self.assertEqual(brief["detail"], "concise")
        self.assertNotIn("candidate_workouts", brief)

    def test_invariants_unavailable_day_and_pain_and_shadow(self):
        avail = TrainingAvailabilityService(self.db)
        avail.upsert(weekday="tuesday", available=False, reason="travel")
        fake = _rec_payload(workout_type="easy_run")
        weekly = WeeklyPlanService(self.db, None, self.ppap)
        with patch.object(weekly._optimizer._next, "recommend", return_value=fake):
            with patch.object(weekly._optimizer._rx, "prescribe", return_value={"total_duration_min": 45}):
                plan = weekly.build(date(2026, 5, 18), next_rec=fake)  # Monday
        by_offset = {s["day_offset"]: s for s in plan["sessions"]}
        self.assertEqual(by_offset[1]["type"], "rest")

        saved = self.ledger.record_recommendation(_rec_payload(), as_of_date=date(2026, 5, 19), persist=True)
        superseded = self.ledger.supersede_recommendation(
            saved["id"],
            _rec_payload(workout_type="easy_run"),
            as_of_date=date(2026, 5, 19),
        )
        original = self.ledger.get_recommendation(saved["id"])
        self.assertEqual(original["recommended_workout_type"], "threshold")
        self.assertFalse(original["is_active"])
        self.assertTrue(superseded["original_snapshot_unchanged"])

        shadow = ShadowRecommendationService(self.db).record_shadow(
            day=date(2026, 5, 19),
            production=_rec_payload(),
            production_recommendation_id=saved["id"],
        )
        self.assertEqual(shadow["production"], "threshold")
        self.assertIn(shadow["shadow"], {"easy_run", "threshold", "long_run", "race_pace"})
        # Shadow must not create/alter plan
        self.assertIsNone(TrainingPlanStore(self.db).get_active_plan(date(2026, 5, 19)))

    def test_abstain_not_aggressive(self):
        from app.services.next_best_workout_service import NextBestWorkoutService

        status, alts, workout, conf = NextBestWorkoutService._decision_status(
            {"hrv_delta_pct": None, "readiness": None, "musculoskeletal": {}},
            {"close_race": True, "ranked_eligible": ["threshold", "easy_run"]},
            "threshold",
            0.7,
            0.3,
            "degraded",
        )
        self.assertEqual(status, DecisionStatus.ABSTAIN.value)
        self.assertEqual(workout, "easy_run")
        self.assertEqual(len(alts), 2)
        self.assertLessEqual(conf, 0.35)

    def test_walk_forward_and_baselines(self):
        baselines = CoachingBaselines(self.db, None, self.ppap)
        with patch.object(self.ppap, "get_readiness_component", return_value=75.0):
            with patch.object(self.ppap, "get_tsb", return_value=2.0):
                workout = baselines.workout_recommendation(date(2026, 5, 18))
        self.assertIn(workout["workout_type"], {"easy_run", "threshold", "rest"})
        cmp = baselines.compare(0.6, 0.5)
        self.assertTrue(cmp["beats_baseline"])
        cmp2 = baselines.compare(0.4, 0.5)
        self.assertFalse(cmp2["beats_baseline"])

        validator = TemporalModelValidationService(self.db, None)
        with patch.object(validator, "_evaluate_fold") as fold:
            fold.return_value = {
                "train_start": "2026-01-01",
                "train_end": "2026-03-01",
                "test_date": "2026-03-02",
                "model_match": True,
                "baseline_match": False,
                "no_future_leakage": True,
            }
            result = validator.walk_forward(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 4, 1),
                min_train_days=60,
                step_days=30,
            )
        self.assertEqual(result["validation_type"], "walk_forward")
        self.assertGreaterEqual(result["aggregate"]["fold_count"], 1)

    def test_bootstrap_and_evidence_band(self):
        ci = bootstrap_ci([1.0, 1.2, 0.9, 1.1, 1.05], n_boot=200)
        self.assertIsNotNone(ci["estimate"])
        self.assertEqual(len(ci["ci95"]), 2)
        self.assertEqual(evidence_band(sample_count=5, effect_size=0.5), "weak")
        self.assertEqual(evidence_band(sample_count=30, effect_size=0.3, stable_folds=2), "strong")

    def test_model_registry_promotion_gate(self):
        reg = CoachingModelRegistry(self.db)
        reg.register(model_key="ranker", version="exp-1")
        with self.assertRaises(ValueError):
            reg.promote(
                model_key="ranker",
                version="exp-1",
                gate={"walk_forward": {}, "baseline_delta": -0.1, "sample_size": 5, "stability": "unstable", "guardrails_pass": False},
            )
        promoted = reg.promote(
            model_key="ranker",
            version="exp-1",
            gate={
                "walk_forward": {"folds": 3},
                "baseline_delta": 0.05,
                "sample_size": 40,
                "stability": "stable",
                "guardrails_pass": True,
            },
        )
        self.assertEqual(promoted["status"], "active")

    def test_export_and_mesocycle_taper_deload(self):
        self.ledger.record_recommendation(_rec_payload(), as_of_date=date(2026, 5, 19), persist=True)
        export = CoachingDataExportService(self.db).export_manifest()
        self.assertFalse(export["contains_credentials"])
        self.assertGreaterEqual(len(export["recommendations"]), 1)
        validation = CoachingDataExportService(self.db).validate_restore_payload(export)
        self.assertTrue(validation["valid"])

        meso = MesocyclePlanner(self.db, None, self.ppap).plan(date(2026, 5, 1), weeks=5)
        self.assertEqual(len(meso["mesocycle"]), 5)
        self.assertIn("volume_target_min", meso["mesocycle"][0])

        with patch.object(self.ppap, "get_tsb", return_value=-25.0):
            with patch.object(self.ppap, "get_hrv_delta_pct", return_value=-12.0):
                with patch.object(self.ppap, "get_rhr_delta_bpm", return_value=5.0):
                    deload = DeloadNeedService(self.db, None, self.ppap).assess(date(2026, 5, 19))
        self.assertIn(deload["deload_need"], {"not_needed", "consider", "recommended"})

        taper = TaperPlanner(self.db, None, self.ppap, goal={
            "goal_type": "race",
            "event": "half_marathon",
            "target_date": "2026-06-20",
        }).plan(date(2026, 5, 19))
        self.assertIn("duration_days", taper)
        self.assertIn("volume_reduction_range", taper)

    def test_query_budget_helper(self):
        with assert_query_budget(self.db, max_queries=50, label="smoke"):
            self.db.query(RecommendationRecord).count()
        with self.assertRaises(QueryBudgetExceeded):
            with assert_query_budget(self.db, max_queries=0, label="fail"):
                self.db.query(RecommendationRecord).count()

    def test_e2e_travel_week_and_duplicate_sync(self):
        TrainingAvailabilityService(self.db).upsert(on_date=date(2026, 5, 20), available=False, reason="travel")
        orch = CoachingOrchestrator(self.db, None)
        with patch("app.services.coaching_orchestrator.NextBestWorkoutService.recommend", return_value=_rec_payload(workout_type="easy_run")):
            with patch("app.services.coaching_orchestrator.CoachingModelHealthService.assess", return_value={"status": "healthy", "warnings": [], "checks": {}}):
                with patch("app.services.coaching_orchestrator.AthleteStateService.build_state", return_value={"recovery": {"value": 60}}):
                    brief = orch.generate_live_decision(date(2026, 5, 19), detail="standard", run_shadow=True)
        self.assertTrue(brief["persisted"])
        self.assertIsNotNone(brief["current_recommendation_id"])
        self.assertIsNotNone(brief.get("shadow"))
        # Duplicate sync
        activity = self._activity("e2e-1", date(2026, 5, 19))
        exec_svc = RecommendationExecutionService(self.db)
        with patch.object(exec_svc._classifier, "classify_activity", return_value={"session_type": "easy_aerobic"}):
            first = exec_svc.link_activity(activity)
            second = exec_svc.link_activity(activity)
        self.assertTrue(second.get("idempotent_reuse"))
        self.assertEqual(first["id"], second["id"])

    def test_failure_modes_malformed_snapshot_and_missing_goal(self):
        degraded = validate_snapshot(
            RecommendationSnapshotV1,
            {"workout_type": 123, "not_a_field": True},
        )
        self.assertTrue(degraded.get("degraded") or degraded.get("schema_version") == 1)
        orch = CoachingOrchestrator(self.db, None, goal=None)
        with patch("app.services.coaching_orchestrator.NextBestWorkoutService.recommend", return_value=_rec_payload()):
            with patch("app.services.coaching_orchestrator.CoachingModelHealthService.assess", return_value={"status": "degraded", "warnings": ["missing_goal"], "checks": {}}):
                with patch("app.services.coaching_orchestrator.AthleteStateService.build_state", return_value={}):
                    brief = orch.preview_decision(date(2026, 5, 19), detail="concise")
        self.assertIn(brief.get("detail"), {"concise", None})
        self.assertFalse(brief.get("persisted", False))

    def test_weak_evidence_not_ranking_eligible(self):
        self.assertEqual(evidence_band(sample_count=4, effect_size=0.9), "weak")
        self.assertNotEqual(evidence_band(sample_count=40, effect_size=0.4, stable_folds=2), "weak")


if __name__ == "__main__":
    unittest.main()
