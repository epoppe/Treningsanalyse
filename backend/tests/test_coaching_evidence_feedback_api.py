"""Coaching evidence dashboard and activity feedback API."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models.activity import Activity, ActivityType
from app.database.models.sleep import HRV
from app.database.models.base import Base
from app.database.models.coaching_v5 import (
    AthleteFeedback,
    CalibrationSnapshot,
    CoachingModelRegistryEntry,
    RecommendationExecution,
    RecommendationRecord,
    TrainingPlanVersion,
)
from app.services.canonical_prospective_observation import CanonicalProspectiveObservationService
from app.services.coaching_evidence_dashboard_service import coaching_change_comparison


def _rec(**overrides) -> RecommendationRecord:
    defaults = dict(
        as_of_date=date(2026, 1, 10),
        model_version="test",
        decision_engine_version="test",
        calibration_version="test",
        application_version="test",
        config_hash="cfg",
        recommended_workout_type="easy_run",
        decision_status="recommend",
        decision_confidence=0.6,
        is_shadow=False,
        is_active=True,
        generated_at=datetime(2026, 1, 10, 8, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return RecommendationRecord(**defaults)


class CoachingEvidenceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'evidence.db'}")
        Base.metadata.create_all(engine)
        self.engine = engine
        self.db = sessionmaker(bind=engine)()
        self.running = ActivityType(type_key="running", type_name="Running")
        self.db.add(self.running)
        self.db.commit()

        from app.dependencies import get_data_storage, get_db
        from app.main import app

        def _db():
            yield self.db

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_data_storage] = lambda: None
        self.client = TestClient(app)

    def tearDown(self):
        from app.main import app

        app.dependency_overrides.clear()
        self.db.close()
        self.tmpdir.cleanup()

    def _counts(self) -> dict:
        return {
            "recommendations": self.db.query(RecommendationRecord).count(),
            "feedback": self.db.query(AthleteFeedback).count(),
            "calibration": self.db.query(CalibrationSnapshot).count(),
            "models": self.db.query(CoachingModelRegistryEntry).count(),
            "plans": self.db.query(TrainingPlanVersion).count(),
        }

    def test_canonical_counts_exclude_shadow_and_superseded(self):
        day = date(2026, 3, 1)
        first = _rec(
            as_of_date=day,
            recommended_workout_type="threshold",
            is_active=False,
            config_hash="a",
            generated_at=datetime(2026, 3, 1, 7, tzinfo=timezone.utc),
        )
        second = _rec(
            as_of_date=day,
            recommended_workout_type="easy_run",
            config_hash="b",
            generated_at=datetime(2026, 3, 1, 9, tzinfo=timezone.utc),
        )
        shadow = _rec(
            as_of_date=day,
            recommended_workout_type="vo2_intervals",
            is_shadow=True,
            is_active=False,
            config_hash="shadow",
        )
        pending = _rec(
            as_of_date=date(2026, 6, 1),
            config_hash="pending",
            recommended_workout_type="long_run",
            generated_at=datetime(2026, 6, 1, 8, tzinfo=timezone.utc),
        )
        self.db.add_all([first, second, shadow, pending])
        self.db.flush()
        first.superseded_by_id = second.id
        self.db.commit()
        before = self._counts()
        res = self.client.get(
            "/api/dashboard/coaching-evidence",
            params={"window_days": 365, "end_date": "2026-06-01"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("no-store", res.headers.get("cache-control", ""))
        body = res.json()
        self.assertTrue(body["read_only"])
        self.assertEqual(body["overview"]["canonical_recommendation_count"], 2)
        self.assertEqual(body["overview"]["pending_count"], 1)
        snapshot = body["data_quality_snapshot"]
        self.assertEqual(snapshot["schema"], "data-quality-snapshot-1")
        self.assertEqual(snapshot["observations"]["pending"], body["overview"]["pending_count"])
        self.assertEqual(
            snapshot["observations"]["pending"] + snapshot["observations"]["evaluated"],
            body["overview"]["canonical_recommendation_count"],
        )
        self.assertEqual(snapshot["observations"]["excluded_detail"]["shadow"], 1)
        self.assertEqual(snapshot["observations"]["excluded_detail"]["superseded"], 1)
        self.assertEqual(snapshot["feedback_coverage"], body["overview"]["feedback_coverage"])
        self.assertEqual(snapshot["execution_matching"]["explicit_share"], body["overview"]["explicit_matching_share"])
        self.assertEqual(body["coaching_change"]["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("prospektiv evidens", body["coaching_change"]["text"])
        self.assertEqual(body["overview"]["short_term_outcome_count"], 0)
        types = {row["workout_type"] for row in body["effectiveness"]}
        self.assertIn("easy_run", types)
        self.assertIn("long_run", types)
        self.assertNotIn("vo2_intervals", types)
        self.assertNotIn("threshold", types)
        self.assertEqual(self._counts(), before)
        joined = " ".join(body["do_not_change"])
        self.assertIn("do not promote", joined)
        self.assertTrue(any("SUPPORTED" in line for line in body["do_not_change"]))

    def test_small_sample_is_insufficient_and_separate_from_feasibility(self):
        day = date(2026, 1, 5)
        record = _rec(as_of_date=day, recommended_workout_type="threshold", config_hash="one")
        self.db.add(record)
        self.db.flush()
        self.db.add(
            RecommendationExecution(
                recommendation_id=record.id,
                activity_id=None,
                execution_status="followed",
                planned_type="threshold",
                actual_type="threshold",
                overall_adherence=0.9,
                linked_at=datetime(2026, 1, 5, 18, tzinfo=timezone.utc),
            )
        )
        self.db.commit()
        res = self.client.get(
            "/api/dashboard/coaching-evidence",
            params={"window_days": 90, "end_date": "2026-04-01"},
        )
        body = res.json()
        threshold = next(row for row in body["effectiveness"] if row["workout_type"] == "threshold")
        self.assertEqual(threshold["recommendation_count"], 1)
        self.assertEqual(threshold["execution_count"], 1)
        self.assertEqual(threshold["evidence_level"], "INSUFFICIENT")
        self.assertEqual(threshold["conclusion_strength"], "none")
        self.assertEqual(threshold["conclusion_strength_label"], "Ingen")
        self.assertEqual(threshold["label"], "Terskel")
        self.assertEqual(body["feasibility"]["followed"], 1)
        self.assertIn("ikke fysiologisk effekt", body["feasibility"]["note"])
        unknown_text = " ".join(row["text"] for row in body["what_we_do_not_know"])
        self.assertIn("kvalitetsøktene", unknown_text)
        self.assertEqual(body["signals"]["subjective"]["fields"]["rpe"], 0)
        self.assertEqual(threshold["data_quality_sample_count"], 0)
        codes = [row["code"] for row in body["what_we_do_not_know"]]
        self.assertIn("taper_not_personalized", codes)
        self.assertNotIn("too_few_races", codes)
        self.assertNotIn("medium_term_not_mature", codes)
        self.assertEqual(body["what_we_know"], [])
        self.assertEqual(body["confidence"]["status"], "INSUFFICIENT_DATA")
        legend = {row["status"]: row["label"] for row in body["maturity_legend"]}
        self.assertEqual(
            legend,
            {
                "pending": "Venter",
                "incomplete_data": "Ufullstendig",
                "evaluated": "Vurdert",
                "insufficient": "Utilstrekkelig evidens",
            },
        )
        self.assertEqual(
            [row["code"] for row in body["operations_lines"]],
            [
                "abstention",
                "distribution",
                "recommendation_churn",
                "plan_churn",
                "data_latency",
                "data_quality_trend",
                "shadow",
            ],
        )
        self.assertTrue(body["do_not_change_nb"])
        self.assertIn("skal ikke promoteres", " ".join(body["do_not_change_nb"]))
        self.assertIn("do not promote", " ".join(body["do_not_change"]))

    def test_get_does_not_resolve_observations_repeatedly(self):
        calls = {"n": 0}
        original = CanonicalProspectiveObservationService.resolve

        def wrapped(service, *args, **kwargs):
            calls["n"] += 1
            return original(service, *args, **kwargs)

        queries = {"n": 0}

        def count_queries(*_args, **_kwargs):
            queries["n"] += 1

        event.listen(self.engine, "before_cursor_execute", count_queries)
        try:
            with patch.object(CanonicalProspectiveObservationService, "resolve", wrapped):
                res = self.client.get(
                    "/api/dashboard/coaching-evidence",
                    params={"window_days": 30, "end_date": "2026-04-01"},
                )
        finally:
            event.remove(self.engine, "before_cursor_execute", count_queries)
        self.assertEqual(res.status_code, 200)
        self.assertLessEqual(calls["n"], 4)
        self.assertLess(queries["n"], 250)
        self.assertEqual(res.json()["overview"]["canonical_recommendation_count"], 0)

    def test_invalid_window_is_422(self):
        res = self.client.get("/api/dashboard/coaching-evidence", params={"window_days": 14})
        self.assertEqual(res.status_code, 422)


class CoachingChangeTests(unittest.TestCase):
    def test_emerging_window_stays_insufficient(self):
        start = date(2026, 1, 1)
        end = date(2026, 7, 1)
        observations, utilities = _halves(start)
        result = coaching_change_comparison(
            observations,
            utilities,
            {"level": "EMERGING"},
            start=start,
            end=end,
        )
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertNotIn("direction", result)

    def test_supported_window_with_thin_halves_stays_insufficient(self):
        start = date(2026, 1, 1)
        end = date(2026, 7, 1)
        observations = []
        utilities = {}
        for index in range(12):
            observations.append(
                {"recommendation_id": index, "as_of_date": (start + timedelta(days=index)).isoformat()}
            )
            utilities[index] = {"short_term_maturity": "evaluated", "short_term_utility": 0.6}
        result = coaching_change_comparison(
            observations,
            utilities,
            {"level": "SUPPORTED"},
            start=start,
            end=end,
        )
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result["later_n"], 0)

    def test_two_full_halves_are_observational(self):
        start = date(2026, 1, 1)
        end = date(2026, 7, 1)
        observations, utilities = _halves(start, earlier=0.4, later=0.7)
        result = coaching_change_comparison(
            observations,
            utilities,
            {"level": "STRONG"},
            start=start,
            end=end,
        )
        self.assertEqual(result["status"], "OBSERVATIONAL")
        self.assertEqual(result["direction"], "later_higher")
        self.assertFalse(result["causal"])
        self.assertEqual(result["earlier_n"], 12)
        self.assertEqual(result["later_n"], 12)
        self.assertIn("ikke en påvist effekt", result["text"])


def _halves(start: date, *, earlier: float = 0.4, later: float = 0.7):
    observations = []
    utilities = {}
    for index in range(12):
        observations.append(
            {"recommendation_id": index, "as_of_date": (start + timedelta(days=index)).isoformat()}
        )
        utilities[index] = {"short_term_maturity": "evaluated", "short_term_utility": earlier}
        late_id = index + 100
        observations.append(
            {"recommendation_id": late_id, "as_of_date": date(2026, 6, 1 + index).isoformat()}
        )
        utilities[late_id] = {"short_term_maturity": "evaluated", "short_term_utility": later}
    return observations, utilities


class MediumGapTests(unittest.TestCase):
    def test_spread_is_separate_from_an_open_window(self):
        from app.services.coaching_evidence_dashboard_service import _medium_unknown

        open_window = _medium_unknown(
            {
                "label": "Terskel",
                "workout_type": "threshold",
                "medium_term_sample_count": 0,
                "short_term_sample_count": 2,
            }
        )
        concentrated = _medium_unknown(
            {
                "label": "Terskel",
                "workout_type": "threshold",
                "medium_term_sample_count": 4,
                "short_term_sample_count": 4,
                "medium_spread_days": 10,
                "medium_evidence_level": "INSUFFICIENT",
            }
        )
        self.assertEqual(open_window["code"], "medium_term_not_mature")
        self.assertEqual(concentrated["code"], "medium_term_spread")
        self.assertIn("spredning", concentrated["text"])


class ActivityFeedbackApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'feedback.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        running = ActivityType(type_key="running", type_name="Running")
        self.db.add(running)
        self.db.flush()
        self.db.add(
            Activity(
                activity_id="act-1",
                activity_name="Easy",
                start_time=datetime.now(timezone.utc),
                duration=3000,
                distance=8000,
                activity_type_id=running.id,
            )
        )
        self.db.add(
            Activity(
                activity_id="race-1",
                activity_name="Park race",
                start_time=datetime.now(timezone.utc),
                duration=1800,
                distance=5000,
                activity_type_id=running.id,
            )
        )
        self.db.add(
            Activity(
                activity_id="old-1",
                activity_name="Park race",
                start_time=datetime.now(timezone.utc) - timedelta(days=40),
                duration=1800,
                distance=5000,
                activity_type_id=running.id,
            )
        )
        self.recommendation = _rec(config_hash="untouched")
        self.db.add(self.recommendation)
        self.db.commit()
        self.recommendation_id = self.recommendation.id

        from app.dependencies import get_data_storage, get_db
        from app.main import app

        def _db():
            yield self.db

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_data_storage] = lambda: None
        self.client = TestClient(app)

    def tearDown(self):
        from app.main import app

        app.dependency_overrides.clear()
        self.db.close()
        self.tmpdir.cleanup()

    def test_put_is_idempotent_and_rejects_ranges(self):
        missing = self.client.get("/api/activities/missing/feedback")
        self.assertEqual(missing.status_code, 404)
        created = self.client.put(
            "/api/activities/act-1/feedback",
            json={"session_feel": "easy", "rpe": 4, "legs": "fresh", "pain": 0, "motivation": 4},
        )
        self.assertEqual(created.status_code, 200)
        again = self.client.put(
            "/api/activities/act-1/feedback",
            json={"session_feel": "as_expected", "rpe": 5, "legs": "normal", "pain": 1, "motivation": 3},
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(self.db.query(AthleteFeedback).count(), 1)
        self.assertEqual(again.json()["feedback"]["id"], created.json()["feedback"]["id"])
        self.assertEqual(again.json()["feedback"]["session_feel"], "as_expected")
        loaded = self.client.get("/api/activities/act-1/feedback")
        self.assertEqual(loaded.json()["feedback"]["rpe"], 5)
        self.assertIn("quick_feel", loaded.json())
        bad = self.client.put("/api/activities/act-1/feedback", json={"rpe": 40, "session_feel": "easy"})
        self.assertEqual(bad.status_code, 422)
        unknown = self.client.put(
            "/api/activities/act-1/feedback",
            json={"session_feel": "sparkly"},
        )
        self.assertEqual(unknown.status_code, 422)
        self.db.refresh(self.recommendation)
        self.assertEqual(self.recommendation.recommended_workout_type, "easy_run")
        self.assertEqual(self.db.query(RecommendationRecord).count(), 1)

    def test_edit_keeps_the_original_recorded_at(self):
        from app.services.athlete_feedback_service import AthleteFeedbackService

        service = AthleteFeedbackService(self.db)
        original = datetime(2026, 1, 12, 8, tzinfo=timezone.utc)
        first = service.record("act-1", session_feel="easy", recorded_at=original)
        updated = service.upsert("act-1", session_feel="hard", rpe=6)
        self.assertEqual(updated["id"], first["id"])
        self.assertEqual(updated["recorded_at"], first["recorded_at"])
        self.assertTrue(updated["recorded_at"].startswith("2026-01-12"))
        self.assertEqual(updated["session_feel"], "hard")
        self.assertEqual(self.db.query(AthleteFeedback).count(), 1)

    def test_prompt_is_selective_and_read_only(self):
        before = self.db.query(AthleteFeedback).count()
        easy = self.client.get("/api/activities/act-1/feedback-prompt")
        race = self.client.get("/api/activities/race-1/feedback-prompt")
        old = self.client.get("/api/activities/old-1/feedback-prompt")
        self.assertEqual(easy.status_code, 200)
        self.assertFalse(easy.json()["should_prompt"])
        self.assertTrue(race.json()["should_prompt"])
        self.assertIn("race", race.json()["reasons"])
        self.assertTrue(any("Konkurranse" in line for line in race.json()["reason_labels"]))
        self.assertFalse(old.json()["should_prompt"])
        self.assertIn("activity_outside_prompt_window", old.json()["reasons"])
        self.client.put("/api/activities/race-1/feedback", json={"session_feel": "hard"})
        again = self.client.get("/api/activities/race-1/feedback-prompt")
        self.assertFalse(again.json()["should_prompt"])
        self.assertTrue(again.json()["already_has_feedback"])
        self.assertIn("no-store", again.headers.get("cache-control", ""))
        self.client.get("/api/activities/race-1/feedback-prompt")
        self.assertEqual(self.db.query(AthleteFeedback).count(), before + 1)

    def test_day_after_hrv_drop_prompts_without_a_new_model(self):
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        marker = yesterday.date() + timedelta(days=1)
        self.db.add(
            Activity(
                activity_id="easy-hrv",
                activity_name="Easy jog",
                start_time=yesterday,
                duration=2400,
                distance=6000,
                activity_type_id=self.db.query(ActivityType).first().id,
            )
        )
        for offset in range(1, 29):
            self.db.add(HRV(measurement_date=marker - timedelta(days=offset), rmssd=50.0))
        self.db.add(HRV(measurement_date=marker, rmssd=40.0))
        self.db.commit()
        prompted = self.client.get("/api/activities/easy-hrv/feedback-prompt")
        self.assertTrue(prompted.json()["should_prompt"])
        self.assertIn("unusual_recovery", prompted.json()["reasons"])
        self.assertTrue(any("HRV" in line for line in prompted.json()["reason_labels"]))
        self.db.query(HRV).filter(HRV.measurement_date == marker).update({"rmssd": 48.0})
        self.db.commit()
        quiet = self.client.get("/api/activities/easy-hrv/feedback-prompt")
        self.assertFalse(quiet.json()["should_prompt"])
        self.assertNotIn("unusual_recovery", quiet.json()["reasons"])
