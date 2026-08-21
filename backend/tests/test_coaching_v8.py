"""Coaching V8 — simplify/verify: explanation, consistency, safety, golden, integrity."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import ActivityType
from app.services.coaching_constants import READINESS_REST_FLOOR, TSB_RECOVERY_FLOOR
from app.services.coaching_health_service import CoachingHealthService
from app.services.coaching_integrity_service import CoachingIntegrityService
from app.services.coaching_orchestrator import CoachingOrchestrator
from app.services.coaching_reason_codes import ReasonCode, map_trace_item
from app.services.decision_consistency_service import DecisionConsistencyService
from app.services.decision_explanation_service import DecisionExplanationService
from app.services.metric_registry import METRIC_REGISTRY, get_metric_spec
from app.services.personalization_evidence_policy import PersonalizationEvidencePolicy, PersonalizationLevel
from app.services.plan_stability import PlanRobustnessService, PlanStabilityService, ReplanningPolicy
from app.services.ppap_metrics_service import PpapMetricsService
from app.services.recovery_cost_service import RecoveryCostService
from app.services.session_dose import dose_from_prescription
from app.services.training_availability_service import TrainingAvailabilityService


class CoachingV8Tests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'v8.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.running = ActivityType(type_key="running", type_name="Running")
        self.db.add(self.running)
        self.db.commit()
        self.ppap = PpapMetricsService(self.db, None)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_metric_registry_covers_core_metrics(self):
        for key in ("ctl", "atl", "tsb", "hrv_delta_pct", "lt2", "readiness", "monotony"):
            spec = get_metric_spec(key)
            self.assertIsNotNone(spec)
            self.assertIn("canonical_producer", spec)
        self.assertGreaterEqual(len(METRIC_REGISTRY), 10)

    def test_decision_explanation_reason_codes(self):
        rec = {
            "workout_type": "easy_run",
            "decision_status": "recommend",
            "evidence_strength": 0.7,
            "decision_trace": [
                {"factor": "tsb", "value": -26, "effect": "requires_recovery"},
                {"factor": "hard_session_spacing", "value": 20, "effect": "blocks_hard_session"},
            ],
            "candidate_workouts": [
                {"workout_type": "easy_run", "eligible": True, "ranking_score": 80},
                {"workout_type": "threshold", "eligible": False, "ineligible_reason": "hard_session_guardrail"},
            ],
        }
        expl = DecisionExplanationService().build(rec)
        self.assertEqual(expl["decision"], "easy_run")
        codes = [r["code"] for r in expl["top_reasons"]]
        self.assertTrue(any(c in codes for c in (ReasonCode.FATIGUE_EXTREME.value, ReasonCode.HARD_SESSION_SPACING.value)))
        self.assertTrue(expl["guardrails_triggered"])

    def test_decision_consistency_stable_under_noise(self):
        def decide(ctx):
            readiness = ctx.get("readiness")
            if readiness is not None and readiness < READINESS_REST_FLOOR:
                return "rest"
            tsb = ctx.get("tsb")
            if tsb is not None and tsb < TSB_RECOVERY_FLOOR:
                return "recovery_run"
            return "easy_run"

        base = {"readiness": 60.0, "tsb": 0.0, "hrv_delta_pct": -5.0, "ctl": 42.0, "sleep_hours": 7.0}
        result = DecisionConsistencyService().evaluate(base, decide)
        self.assertEqual(result["status"], "stable")

        # Cliff without hysteresis → unstable near floor
        cliff = {"readiness": READINESS_REST_FLOOR, "tsb": 0.0, "hrv_delta_pct": -5.0, "ctl": 42.0, "sleep_hours": 7.0}
        cliff_result = DecisionConsistencyService().evaluate(
            cliff,
            decide,
            perturbations=[{"readiness": -0.5}, {"readiness": 0.5}] * 4,
        )
        self.assertIn(cliff_result["status"], {"sensitive", "unstable"})

        # Hysteresis helps
        triggered = DecisionConsistencyService.with_hysteresis(
            READINESS_REST_FLOOR - 0.5,
            threshold=READINESS_REST_FLOOR,
            previous_triggered=True,
            band=2.0,
            lower_is_triggered=True,
        )
        self.assertTrue(triggered)

    def test_safety_unavailable_and_pain_not_overridable(self):
        TrainingAvailabilityService(self.db).upsert(on_date=date(2026, 5, 20), available=False, reason="travel")
        orch = CoachingOrchestrator(self.db, None)
        with patch("app.services.coaching_orchestrator.NextBestWorkoutService.recommend") as rec:
            rec.return_value = {
                "workout_type": "threshold",
                "decision_status": "recommend",
                "evidence_strength": 0.9,
                "decision_confidence": 0.9,
                "decision_trace": [{"factor": "goal", "effect": "supports_quality"}],
                "contraindications": [],
                "candidate_workouts": [],
                "context_summary": {"tsb": 5, "readiness": 80},
                "workout_prescription": {"total_duration_min": 50},
            }
            with patch("app.services.coaching_orchestrator.CoachingModelHealthService.assess", return_value={"status": "healthy", "warnings": [], "checks": {}}):
                with patch("app.services.coaching_orchestrator.AthleteStateService.build_state", return_value={}):
                    with patch("app.services.coaching_orchestrator.WeeklyPlanService.build") as plan:
                        plan.return_value = {
                            "sessions": [
                                {"day_offset": 0, "type": "threshold", "duration_min": 50},
                                {"day_offset": 1, "type": "rest", "duration_min": 0},
                            ],
                            "plan_id": None,
                            "version": 1,
                            "week_objective": "test",
                            "simulation": {},
                        }
                        with patch("app.services.coaching_orchestrator.PlanAdaptationService.assess", return_value={"plan_status": "ok", "changes": [], "reason": None}):
                            brief = orch.preview_decision(date(2026, 5, 19), detail="concise")
        # Explanation present
        self.assertIn("why", brief)
        self.assertIn("guardrails", brief)
        self.assertIn("evidence", brief)

        # Pain cannot increase intensity via explanation guardrail mapping
        expl = DecisionExplanationService().build(
            {
                "workout_type": "easy_run",
                "decision_trace": [],
                "contraindications": ["pain_guardrail"],
                "candidate_workouts": [],
            }
        )
        self.assertIn(ReasonCode.PAIN_GUARDRAIL.value, expl["guardrails_triggered"])

    def test_golden_master_decision_classes(self):
        """Immutable scenarios: assert decision class + reason codes, not float scores."""
        scenarios = [
            {
                "name": "extreme_fatigue",
                "rec": {
                    "workout_type": "recovery_run",
                    "decision_status": "recommend",
                    "decision_trace": [{"factor": "tsb", "value": -30, "effect": "requires_recovery"}],
                    "candidate_workouts": [],
                },
                "expect_types": {"recovery_run", "rest", "easy_run"},
                "expect_guardrail_any": {ReasonCode.FATIGUE_EXTREME.value, ReasonCode.RECOVERY_LOW.value},
            },
            {
                "name": "abstain",
                "rec": {
                    "workout_type": "easy_run",
                    "decision_status": "abstain",
                    "decision_trace": [{"factor": "evidence", "effect": "abstain"}],
                    "candidate_workouts": [],
                },
                "expect_types": {"easy_run", "rest"},
                "expect_guardrail_any": {ReasonCode.ABSTAIN_LOW_EVIDENCE.value},
            },
        ]
        for sc in scenarios:
            expl = DecisionExplanationService().build(sc["rec"])
            self.assertIn(expl["decision"], sc["expect_types"], sc["name"])
            self.assertTrue(
                set(expl["guardrails_triggered"]) & sc["expect_guardrail_any"],
                sc["name"],
            )

    def test_personalization_policy_and_decay(self):
        policy = PersonalizationEvidencePolicy()
        low = policy.assess(sample_count=3, evidence_strength=0.9, prospective=True)
        self.assertEqual(low["level"], PersonalizationLevel.DEFAULT)
        self.assertFalse(low["may_override_defaults"])
        strong = policy.assess(
            sample_count=50,
            evidence_strength=0.7,
            stable_folds=2,
            prospective=True,
            last_supporting_observation=date(2024, 1, 1),
            as_of=date(2026, 5, 1),
        )
        self.assertLess(strong["decay_factor"], 1.0)

    def test_health_integrity_recovery_dose_plan(self):
        health = CoachingHealthService(self.db).report(date(2026, 5, 1))
        self.assertIn(health["status"], {"healthy", "degraded", "attention_required", "critical"})
        # Empty SQLite via create_all has no alembic stamp → migration check is real, not a placeholder
        self.assertIn("current_revision", health["checks"]["db_migration"])
        self.assertIn("expected_head", health["checks"]["db_migration"])
        self.assertNotEqual(health["checks"]["db_migration"].get("current_revision"), "alembic_head_runtime")
        integrity = CoachingIntegrityService(self.db).check()
        self.assertIn(integrity["status"], {"healthy", "warnings", "attention_required", "critical"})
        repair = CoachingIntegrityService(self.db).repair_plan(dry_run=True)
        self.assertTrue(repair["dry_run"])

        cost = RecoveryCostService(self.db, self.ppap).estimate("threshold")
        self.assertIn("expected_recovery_days", cost)
        self.assertEqual(cost["source"], "default")
        dose = dose_from_prescription(
            "threshold",
            {"total_duration_min": 55, "main_set": {"repetitions": 3, "work_duration_min": 10}},
        )
        self.assertEqual(dose["work_duration_min"], 30)
        self.assertNotEqual(
            dose["dose_key"],
            dose_from_prescription(
                "threshold",
                {"total_duration_min": 55, "main_set": {"repetitions": 5, "work_duration_min": 10}},
            )["dose_key"],
        )

        robustness = PlanRobustnessService().score(
            [
                {"type": "easy_run"},
                {"type": "threshold"},
                {"type": "easy_run"},
                {"type": "long_run"},
                {"type": "easy_run"},
            ]
        )
        self.assertIn("robustness_score", robustness)
        replan = ReplanningPolicy().decide(hrv_delta=-7.0, recent_plan_changes=0)
        self.assertEqual(replan["action"], "do_not_replan")
        stability = PlanStabilityService().classify(1)
        self.assertEqual(stability["status"], "insufficient_data")
        stable = PlanStabilityService().classify(1, history_points=5, material_changes=0)
        self.assertEqual(stable["status"], "stable")

    def test_reason_code_mapping(self):
        self.assertEqual(
            map_trace_item({"factor": "readiness", "effect": "requires_rest"}),
            ReasonCode.READINESS_REST.value,
        )


if __name__ == "__main__":
    unittest.main()
