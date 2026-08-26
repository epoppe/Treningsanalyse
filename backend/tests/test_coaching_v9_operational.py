"""Coaching V9 operational: sufficiency, restore, prospective, monitors, invariants."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.migrations import (
    assert_single_alembic_head,
    get_head_revision,
    get_schema_version,
    run_migrations,
)
from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.database.models.coaching_v5 import (
    RecommendationExecution,
    RecommendationRecord,
    TrainingPlan,
    TrainingPlanVersion,
)
from app.database.models.sync_state import SyncState
from app.services.athlete_concept_drift_service import AthleteConceptDriftService
from app.services.coaching_data_export_service import CoachingDataExportService
from app.services.coaching_integrity_service import CoachingIntegrityService
from app.services.coaching_operational_monitors import (
    DataLatencyMonitor,
    DecisionConfidenceMonitor,
    FeedbackValueService,
    PlanChurnMonitor,
    RecommendationChurnMonitor,
    ShadowPromotionReadinessService,
)
from app.services.evidence_hierarchy import EvidenceHierarchy
from app.services.monthly_coaching_review_service import generate_monthly_coaching_review
from app.services.prospective_evidence_report_service import ProspectiveEvidenceReportService
from app.services.sample_sufficiency_policy import SampleSufficiencyPolicy, SufficiencyLevel
from app.services.status_semantics import DriftStatus


class SampleSufficiencyTests(unittest.TestCase):
    def test_insufficient_prospective_sample(self):
        result = SampleSufficiencyPolicy().assess(domain="recovery_cost", sample_count=3)
        self.assertEqual(result["level"], SufficiencyLevel.INSUFFICIENT.value)
        self.assertFalse(result["may_override_defaults"])

    def test_temporally_concentrated_sample_downweighted(self):
        day = date(2026, 5, 1)
        # 12 samples all in 3 days — should not get full credit
        dates = [day - timedelta(days=i % 3) for i in range(12)]
        concentrated = SampleSufficiencyPolicy().assess(
            domain="recovery_cost",
            sample_count=12,
            observation_dates=dates,
            as_of=day,
        )
        spread_dates = [day - timedelta(days=i * 7) for i in range(12)]
        spread = SampleSufficiencyPolicy().assess(
            domain="recovery_cost",
            sample_count=12,
            observation_dates=spread_dates,
            as_of=day,
        )
        self.assertLess(concentrated["effective_sample_count"], spread["effective_sample_count"])


class EvidenceHierarchyTests(unittest.TestCase):
    def test_prospective_outranks_historical_only_when_sufficient(self):
        day = date(2026, 5, 1)
        dates = [day - timedelta(days=i * 10) for i in range(25)]
        # Insufficient prospective, sufficient historical → historical
        hist = EvidenceHierarchy().resolve(
            domain="recovery_cost",
            prospective_n=2,
            historical_n=25,
            historical_dates=dates,
            as_of=day,
        )
        self.assertEqual(hist["source"], "historical")
        # Sufficient prospective beats historical
        pros = EvidenceHierarchy().resolve(
            domain="recovery_cost",
            prospective_n=25,
            prospective_dates=dates,
            historical_n=25,
            historical_dates=dates,
            as_of=day,
        )
        self.assertEqual(pros["source"], "prospective")
        # Neither sufficient → default
        default = EvidenceHierarchy().resolve(domain="recovery_cost", prospective_n=2, historical_n=2)
        self.assertEqual(default["source"], "default")
        self.assertFalse(default["personalized"])


class RestoreRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'src.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.running = ActivityType(type_key="running", type_name="Running")
        self.db.add(self.running)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_restore_roundtrip(self):
        day = date(2026, 5, 1)
        self.db.add(
            Activity(
                activity_id="act-1",
                activity_name="Run",
                activity_type_id=self.running.id,
                start_time=datetime(2026, 5, 1, 8, tzinfo=timezone.utc),
                duration=2400,
            )
        )
        rec = RecommendationRecord(
            as_of_date=day,
            is_active=True,
            model_version="default",
            decision_engine_version="t",
            calibration_version="t",
            application_version="t",
            config_hash="h",
            recommended_workout_type="easy_run",
            decision_status="recommend",
            decision_confidence=0.6,
        )
        self.db.add(rec)
        self.db.flush()
        self.db.add(
            RecommendationExecution(
                recommendation_id=rec.id,
                activity_id="act-1",
                execution_status="completed",
                planned_type="easy_run",
                actual_type="easy_run",
                overall_adherence=0.9,
            )
        )
        plan = TrainingPlan(week_start=day, is_active=True)
        self.db.add(plan)
        self.db.flush()
        self.db.add(
            TrainingPlanVersion(
                plan_id=plan.id,
                version=1,
                sessions_json=[{"type": "easy_run"}],
                week_objective="aerobic",
            )
        )
        self.db.commit()

        export = CoachingDataExportService(self.db)
        payload = export.export_manifest()
        self.assertFalse(payload["contains_credentials"])

        # Clean DB at alembic head
        dest_path = Path(self.tmpdir.name) / "dest.db"
        dest_url = f"sqlite:///{dest_path}"
        dest_engine = create_engine(dest_url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
        run_migrations(dest_engine, dest_url)
        dest_db = sessionmaker(bind=dest_engine)()
        # Activity FK for feedback/exec — add type + activity
        dest_db.add(ActivityType(type_key="running", type_name="Running"))
        dest_db.flush()
        dest_db.add(
            Activity(
                activity_id="act-1",
                activity_name="Run",
                start_time=datetime(2026, 5, 1, 8, tzinfo=timezone.utc),
                duration=2400,
            )
        )
        dest_db.commit()

        report = CoachingDataExportService(dest_db).restore(payload, commit=True)
        self.assertTrue(report["ok"])
        self.assertEqual(report["restored_counts"]["recommendations"], 1)
        self.assertEqual(report["restored_counts"]["executions"], 1)
        self.assertEqual(report["restored_counts"]["plans"], 1)
        self.assertIsNotNone(report["integrity"])
        self.assertGreaterEqual(dest_db.query(RecommendationRecord).count(), 1)
        dest_db.close()


class ProspectiveAndMonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'ops.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.day = date(2026, 5, 1)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_prospective_report_sparse(self):
        report = ProspectiveEvidenceReportService(self.db).report(end=self.day, window_days=30)
        self.assertEqual(report["recommendations"]["sample_count"], 0)
        self.assertIn("evidence_sufficiency", report)

    def test_confidence_monitor_low_n(self):
        result = DecisionConfidenceMonitor(self.db).assess(
            start=self.day - timedelta(days=30), end=self.day
        )
        self.assertEqual(result["status"], "insufficient_data")

    def test_shadow_insufficient_evidence(self):
        result = ShadowPromotionReadinessService().assess(
            self.db, start=self.day - timedelta(days=30), end=self.day
        )
        self.assertEqual(result["status"], "NOT_READY")

    def test_plan_churn_trivial_hrv_insufficient_history(self):
        result = PlanChurnMonitor().assess(self.db, as_of=self.day)
        self.assertIn(result["status"], {"INSUFFICIENT_DATA", "STABLE", "ADAPTIVE", "OVERREACTIVE"})
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")

    def test_legitimate_replan_after_hard_activity_reason(self):
        plan = TrainingPlan(week_start=self.day, is_active=True)
        self.db.add(plan)
        self.db.flush()
        for i in range(4):
            self.db.add(
                TrainingPlanVersion(
                    plan_id=plan.id,
                    version=i + 1,
                    created_at=datetime(2026, 5, 1, i, tzinfo=timezone.utc),
                    changes_json=[{"action": "delay_quality"}] if i else None,
                    reason_json={"code": "new_activity"} if i else {"code": "initial"},
                )
            )
        self.db.commit()
        result = PlanChurnMonitor().assess(self.db, as_of=self.day, window_days=14)
        self.assertGreaterEqual(result["sample_count"], 3)

    def test_recommendation_churn_without_new_evidence(self):
        for i, wtype in enumerate(["easy_run", "threshold", "easy_run"]):
            self.db.add(
                RecommendationRecord(
                    as_of_date=self.day,
                    is_active=i == 2,
                    model_version="default",
                    decision_engine_version="t",
                    calibration_version="t",
                    application_version="t",
                    config_hash=f"h{i}",
                    decision_payload_hash=f"p{i}",
                    recommended_workout_type=wtype,
                    generated_at=datetime(2026, 5, 1, 8 + i, tzinfo=timezone.utc),
                )
            )
        self.db.commit()
        result = RecommendationChurnMonitor().assess(self.db, day=self.day)
        self.assertEqual(result["status"], "churn_without_evidence")

    def test_stale_local_sync_despite_source(self):
        self.db.add(
            SyncState(
                key="garmin",
                last_synced_at=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
            )
        )
        # Sleep "source" for same day
        from app.database.models.sleep import Sleep

        self.db.add(Sleep(sleep_date=date(2026, 5, 1), sleep_score=80))
        self.db.commit()
        as_of = datetime(2026, 5, 1, 20, 0, tzinfo=timezone.utc)
        result = DataLatencyMonitor().assess(self.db, as_of=as_of)
        self.assertTrue(result["stale_local_despite_source"])

    def test_monthly_review_sparse(self):
        review = generate_monthly_coaching_review(self.db, end=self.day)
        self.assertTrue(review["sparse_data"])
        self.assertIn("10_what_should_not_change", review["answers"])

    def test_feedback_value_no_spam_default(self):
        result = FeedbackValueService().prioritize(context={})
        self.assertEqual(result["feedback_priority"], "none")


class CoachingInvariantSuite(unittest.TestCase):
    """CI-facing invariant checks — fail the build if broken."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'inv.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_insufficient_evidence_not_stable(self):
        result = AthleteConceptDriftService(self.db).assess(date(2026, 5, 1))
        self.assertNotEqual(result["overall"], DriftStatus.STABLE.value)
        self.assertEqual(result["overall"], DriftStatus.INSUFFICIENT_DATA.value)

    def test_supersede_graph_integrity_empty_healthy(self):
        report = CoachingIntegrityService(self.db).check()
        self.assertEqual(report["status"], "healthy")

    def test_alembic_single_head(self):
        head = assert_single_alembic_head()
        self.assertEqual(head, get_head_revision())

    def test_preview_contract_imported(self):
        # Ensure preview_decision exists and is the non-persisting entry
        from app.services.coaching_orchestrator import CoachingOrchestrator

        self.assertTrue(hasattr(CoachingOrchestrator, "preview_decision"))
        self.assertTrue(hasattr(CoachingOrchestrator, "generate_live_decision"))


class AlembicOperationalTests(unittest.TestCase):
    def test_upgrade_from_previous_revision(self):
        from alembic.script import ScriptDirectory
        from app.database.migrations import get_alembic_config

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "step.db"
            url = f"sqlite:///{db_path}"
            engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
            cfg = get_alembic_config(url)
            script = ScriptDirectory.from_config(cfg)
            head = script.get_current_head()
            parent = script.get_revision(head).down_revision
            self.assertIsNotNone(parent)
            from alembic import command

            with engine.connect() as conn:
                cfg.attributes["connection"] = conn
                command.upgrade(cfg, parent)
                conn.commit()
            mid = get_schema_version(engine)
            self.assertEqual(mid["schema_version"], parent)
            self.assertFalse(mid["schema_at_head"])
            run_migrations(engine, url)
            final = get_schema_version(engine)
            self.assertTrue(final["schema_at_head"])
            self.assertEqual(final["schema_version"], head)


if __name__ == "__main__":
    unittest.main()
