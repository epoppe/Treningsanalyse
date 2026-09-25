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
        self.assertEqual(body["feasibility"]["followed"], 1)
        self.assertNotEqual(body["feasibility"]["note"], "")
        self.assertTrue(body["what_we_do_not_know"])
        self.assertEqual(body["what_we_know"], [])
        self.assertEqual(body["confidence"]["status"], "INSUFFICIENT_DATA")
        legend = {row["status"] for row in body["maturity_legend"]}
        self.assertEqual(legend, {"pending", "incomplete_data", "evaluated", "insufficient"})

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

    def test_prompt_is_selective_and_read_only(self):
        before = self.db.query(AthleteFeedback).count()
        easy = self.client.get("/api/activities/act-1/feedback-prompt")
        race = self.client.get("/api/activities/race-1/feedback-prompt")
        old = self.client.get("/api/activities/old-1/feedback-prompt")
        self.assertEqual(easy.status_code, 200)
        self.assertFalse(easy.json()["should_prompt"])
        self.assertTrue(race.json()["should_prompt"])
        self.assertIn("race", race.json()["reasons"])
        self.assertFalse(old.json()["should_prompt"])
        self.assertIn("activity_outside_prompt_window", old.json()["reasons"])
        self.client.put("/api/activities/race-1/feedback", json={"session_feel": "hard"})
        again = self.client.get("/api/activities/race-1/feedback-prompt")
        self.assertFalse(again.json()["should_prompt"])
        self.assertTrue(again.json()["already_has_feedback"])
        self.assertIn("no-store", again.headers.get("cache-control", ""))
        self.client.get("/api/activities/race-1/feedback-prompt")
        self.assertEqual(self.db.query(AthleteFeedback).count(), before + 1)
