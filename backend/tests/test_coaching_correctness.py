"""Coaching correctness pass — semantic fixes after v8 (no new model layer)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.database.models.coaching_v5 import (
    RecommendationExecution,
    RecommendationRecord,
    ValidationRun,
)
from app.database.models.lactate_threshold_history import LactateThresholdHistory
from app.services.athlete_concept_drift_service import AthleteConceptDriftService, MIN_SAMPLES_PER_WINDOW
from app.services.builtin_model_registry import BuiltinModelRegistry
from app.services.coaching_health_service import CoachingHealthService
from app.services.coaching_integrity_service import CoachingIntegrityService
from app.services.decision_explanation_service import REQUIRED_FIELDS, DecisionExplanationService
from app.services.evidence_quality_propagation import apply_data_quality_to_evidence
from app.services.health_status_policy import HealthStatusPolicy
from app.services.plan_stability import PlanStabilityService
from app.services.ppap_metrics_service import PpapMetricsService
from app.services.recovery_cost_service import RecoveryCostService
from app.services.status_semantics import DriftStatus, IntegritySeverity


class CoachingCorrectnessTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'correctness.db'}")
        Base.metadata.create_all(engine)
        self.engine = engine
        self.db = sessionmaker(bind=engine)()
        self.running = ActivityType(type_key="running", type_name="Running")
        self.db.add(self.running)
        self.db.commit()
        self.ppap = PpapMetricsService(self.db, None)
        self.day = date(2026, 5, 1)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def _activity(self, aid: str, day: date, *, speed=3.2, hr=140, tss=50.0, ascent=10.0, distance=8000.0):
        act = Activity(
            activity_id=aid,
            activity_name="Run",
            activity_type_id=self.running.id,
            start_time=datetime(day.year, day.month, day.day, 8, 0, tzinfo=timezone.utc),
            average_speed=speed,
            average_heart_rate=hr,
            training_stress_score=tss,
            total_ascent=ascent,
            distance=distance,
            duration=2400,
        )
        act.activity_type = self.running
        self.db.add(act)
        return act

    def test_pace_hr_uses_speed_and_hr(self):
        for i in range(MIN_SAMPLES_PER_WINDOW + 1):
            self._activity(f"r{i}", self.day - timedelta(days=i + 1), speed=3.0 + i * 0.01, hr=135 + i)
            self._activity(f"p{i}", self.day - timedelta(days=60 + i), speed=3.5, hr=150)
        self.db.commit()

        with patch.object(
            AthleteConceptDriftService,
            "_safe_classify",
            return_value="easy_run",
        ):
            svc = AthleteConceptDriftService(self.db, self.ppap)
            recent = svc._pace_hr_signals(self.day - timedelta(days=56), self.day)
        self.assertGreaterEqual(recent["sample_count"], MIN_SAMPLES_PER_WINDOW)
        self.assertEqual(recent["variables"], ["average_speed", "average_heart_rate"])
        self.assertTrue(all(v > 0 for v in recent["values"]))
        # Coupling is speed/hr — not CTL
        self.assertNotIn("ctl", str(recent["variables"]).lower())

    def test_rpe_load_requires_rpe(self):
        self._activity("a1", self.day - timedelta(days=2), tss=60)
        self.db.commit()
        result = AthleteConceptDriftService(self.db, self.ppap).assess(self.day)
        rpe = next(r for r in result["relationships"] if r["relationship"] == "rpe_load")
        self.assertEqual(rpe["status"], DriftStatus.INSUFFICIENT_DATA.value)
        self.assertEqual(rpe.get("reason"), "no_rpe_feedback")

    def test_insufficient_sample_not_stable(self):
        result = AthleteConceptDriftService(self.db, self.ppap).assess(self.day)
        self.assertEqual(result["overall"], DriftStatus.INSUFFICIENT_DATA.value)
        for rel in result["relationships"]:
            self.assertNotEqual(rel["status"], DriftStatus.STABLE.value)

    def test_lt2_freshness_observed_timestamp(self):
        observed = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
        self.db.add(
            LactateThresholdHistory(
                observed_at=observed,
                source="garmin",
                lactate_threshold_speed=3.5,
                lactate_threshold_heart_rate=165,
            )
        )
        self.db.commit()
        with patch("app.services.coaching_health_service.get_schema_version") as schema:
            schema.return_value = {
                "schema_version": "abc",
                "schema_head": "abc",
                "schema_at_head": True,
            }
            report = CoachingHealthService(self.db, self.ppap).report(self.day)
        lt2 = report["checks"]["data_freshness"]["lt2"]
        self.assertEqual(lt2["observed_at"], "2026-04-20")
        self.assertEqual(lt2["status"], "fresh")
        self.assertIsNotNone(lt2["age_days"])
        self.assertNotEqual(lt2["status"], "missing")

    def test_missing_lt2_is_missing_not_stale(self):
        with patch("app.services.coaching_health_service.get_schema_version") as schema:
            schema.return_value = {
                "schema_version": "abc",
                "schema_head": "abc",
                "schema_at_head": True,
            }
            report = CoachingHealthService(self.db, self.ppap).report(self.day)
        lt2 = report["checks"]["data_freshness"]["lt2"]
        self.assertIsNone(lt2["observed_at"])
        self.assertEqual(lt2["status"], "missing")
        self.assertNotEqual(lt2["status"], "stale")

    def test_database_behind_alembic_head(self):
        with patch("app.services.coaching_health_service.get_schema_version") as schema:
            schema.return_value = {
                "schema_version": "old_rev",
                "schema_head": "new_rev",
                "schema_at_head": False,
            }
            report = CoachingHealthService(self.db, self.ppap).report(self.day)
        mig = report["checks"]["db_migration"]
        self.assertEqual(mig["current_revision"], "old_rev")
        self.assertEqual(mig["expected_head"], "new_rev")
        self.assertFalse(mig["up_to_date"])
        self.assertNotEqual(mig.get("current_revision"), "alembic_head_runtime")
        self.assertEqual(report["status"], "critical")
        self.assertIn("migration_behind", report["issues"])

    def test_orphan_execution_severity(self):
        self.db.add(
            RecommendationExecution(
                recommendation_id=None,
                execution_status="completed",
                planned_type="easy_run",
            )
        )
        self.db.commit()
        report = CoachingIntegrityService(self.db).check()
        finding = next(f for f in report["findings"] if f["code"] == "ORPHAN_EXECUTION")
        self.assertEqual(finding["severity"], IntegritySeverity.ERROR.value)
        self.assertEqual(finding["count"], 1)
        self.assertFalse(finding["repairable"])
        self.assertIn("description", finding)
        self.assertEqual(report["status"], "attention_required")

    def test_supersede_cycle_detection(self):
        a = RecommendationRecord(
            as_of_date=self.day,
            is_active=False,
            model_version="default",
            decision_engine_version="t",
            calibration_version="t",
            application_version="t",
            config_hash="h1",
            recommended_workout_type="easy_run",
        )
        b = RecommendationRecord(
            as_of_date=self.day,
            is_active=False,
            model_version="default",
            decision_engine_version="t",
            calibration_version="t",
            application_version="t",
            config_hash="h2",
            recommended_workout_type="easy_run",
        )
        self.db.add_all([a, b])
        self.db.flush()
        a.superseded_by_id = b.id
        b.superseded_by_id = a.id
        self.db.commit()
        report = CoachingIntegrityService(self.db).check()
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("SUPERSEDE_CYCLE", codes)
        self.assertEqual(report["status"], "critical")

    def test_integrity_query_budget(self):
        for i in range(40):
            self.db.add(
                RecommendationRecord(
                    as_of_date=self.day - timedelta(days=i % 10),
                    is_active=i == 0,
                    model_version="default",
                    decision_engine_version="t",
                    calibration_version="t",
                    application_version="t",
                    config_hash=f"h{i}",
                    recommended_workout_type="easy_run",
                )
            )
        self.db.commit()
        # Set-based integrity must stay within a fixed budget even with history
        report = CoachingIntegrityService(self.db).check(max_queries=25)
        self.assertIn(report["status"], {"healthy", "warnings", "attention_required", "critical"})

    def test_validation_run_unknown_model(self):
        self.assertFalse(BuiltinModelRegistry.is_known("ranker", "exp-1"))
        self.db.add(
            ValidationRun(
                model_key="ranker",
                model_version="totally-unknown-xyz",
                config_hash="c",
                data_start=self.day - timedelta(days=30),
                data_end=self.day,
                sample_size=10,
                validation_code_version="test",
                status="completed",
            )
        )
        self.db.commit()
        report = CoachingIntegrityService(self.db).check()
        finding = next(f for f in report["findings"] if f["code"] == "VALIDATION_RUN_UNKNOWN_VERSION")
        self.assertEqual(finding["severity"], IntegritySeverity.WARNING.value)

    def test_health_status_policy(self):
        self.assertEqual(HealthStatusPolicy.aggregate([]), "healthy")
        self.assertEqual(HealthStatusPolicy.aggregate(["low_prospective_n"]), "degraded")
        self.assertEqual(HealthStatusPolicy.aggregate(["orphan_executions"]), "attention_required")
        self.assertEqual(HealthStatusPolicy.aggregate(["migration_behind"]), "critical")
        self.assertEqual(
            HealthStatusPolicy.aggregate(["low_prospective_n", "migration_behind"]),
            "critical",
        )

    def test_recovery_cost_default_vs_personalized(self):
        cost = RecoveryCostService(self.db, self.ppap).estimate("threshold", as_of=self.day)
        self.assertEqual(cost["source"], "default")
        self.assertFalse(cost["personalized"])
        self.assertIsNone(cost.get("ci"))

    def test_plan_stability_insufficient_data(self):
        result = PlanStabilityService().classify(1)
        self.assertEqual(result["status"], DriftStatus.INSUFFICIENT_DATA.value)
        hist = PlanStabilityService().from_history(self.db, as_of=self.day)
        self.assertEqual(hist["status"], DriftStatus.INSUFFICIENT_DATA.value)

    def test_stale_input_reduces_evidence_not_decision(self):
        adj = apply_data_quality_to_evidence(
            0.8,
            0.75,
            {
                "lt2": {"status": "stale"},
                "hrv_baseline": {"status": "missing"},
                "critical_speed": {"status": "fresh"},
            },
        )
        self.assertLess(adj["evidence_strength"], 0.8)
        self.assertLess(adj["decision_confidence"], 0.75)
        self.assertFalse(adj["decision_changed"])
        self.assertTrue(adj["confidence_reduced"])

    def test_decision_explanation_contract(self):
        expl = DecisionExplanationService().build(
            {
                "workout_type": "easy_run",
                "decision_status": "recommend",
                "evidence_strength": 0.6,
                "decision_confidence": 0.55,
                "data_quality": 0.7,
                "decision_trace": [{"factor": "tsb", "value": -5, "effect": "informational"}],
                "candidate_workouts": [{"workout_type": "easy_run", "eligible": True}],
            }
        )
        DecisionExplanationService.assert_contract(expl)
        for field in REQUIRED_FIELDS:
            self.assertIn(field, expl)
        self.assertIsInstance(expl["reason_codes"], list)
        self.assertTrue(all(isinstance(c, str) for c in expl["reason_codes"]))

    def test_self_consistency_scenarios(self):
        """Health/integrity expected statuses across key fixture scenarios."""
        with patch("app.services.coaching_health_service.get_schema_version") as schema:
            schema.return_value = {
                "schema_version": "head",
                "schema_head": "head",
                "schema_at_head": True,
            }
            empty = CoachingHealthService(self.db, self.ppap).report(self.day)
        self.assertIn(empty["status"], {"degraded", "attention_required", "healthy"})
        self.assertEqual(empty["checks"]["data_freshness"]["lt2"]["status"], "missing")

        integrity_empty = CoachingIntegrityService(self.db).check()
        self.assertEqual(integrity_empty["status"], "healthy")

        # No prospective recommendations → degraded via low_prospective_n
        self.assertIn("low_prospective_n", empty["issues"])

        # Missing HRV freshness
        self.assertEqual(empty["checks"]["data_freshness"]["hrv_baseline"]["status"], "missing")

        # Stale LT2
        self.db.add(
            LactateThresholdHistory(
                observed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                source="garmin",
                lactate_threshold_speed=3.4,
                lactate_threshold_heart_rate=160,
            )
        )
        self.db.commit()
        with patch("app.services.coaching_health_service.get_schema_version") as schema:
            schema.return_value = {
                "schema_version": "head",
                "schema_head": "head",
                "schema_at_head": True,
            }
            stale = CoachingHealthService(self.db, self.ppap).report(self.day)
        self.assertEqual(stale["checks"]["data_freshness"]["lt2"]["status"], "stale")
        self.assertIn("stale_lt2", stale["issues"])


if __name__ == "__main__":
    unittest.main()
