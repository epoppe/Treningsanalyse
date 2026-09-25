"""Query-count guardrails for canonical prospective observations.

These tests lock chain closure and bounded reads. They do not assert milliseconds.
"""

from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from app.database.models.activity import Activity, ActivityType
from app.database.models.base import Base
from app.database.models.coaching_v5 import AthleteFeedback, RecommendationExecution, RecommendationRecord
from app.services.canonical_prospective_observation import SCHEMA, CanonicalProspectiveObservationService
from app.services.data_quality_snapshot import explicit_execution_coverage
from tests.sqlite_test_utils import dispose_engine, file_sqlite_url, make_file_engine


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


def _selects(engine):
    counts: Counter = Counter()

    def grab(_conn, _cursor, statement, _params, _context, _executemany):
        low = " ".join(statement.lower().split())
        if not low.startswith("select"):
            return
        for name in (
            "recommendation_records",
            "recommendation_executions",
            "from activities",
            "athlete_feedback",
        ):
            if name in low:
                counts[name] += 1

    event.listen(engine, "before_cursor_execute", grab)
    return counts


class ChainClosureTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.engine = make_file_engine(file_sqlite_url(Path(self.tmpdir.name) / "scale.db"))
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.running = ActivityType(type_key="running", type_name="Running")
        self.db.add(self.running)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        dispose_engine(self.engine)
        self.tmpdir.cleanup()

    def test_window_does_not_publish_a_predecessor_whose_tip_is_outside(self):
        predecessor = _rec(
            as_of_date=date(2025, 2, 1),
            is_active=False,
            config_hash="pred",
            generated_at=datetime(2025, 2, 1, 8, tzinfo=timezone.utc),
        )
        tip = _rec(
            as_of_date=date(2025, 8, 1),
            is_active=True,
            config_hash="tip",
            generated_at=datetime(2025, 8, 1, 8, tzinfo=timezone.utc),
        )
        self.db.add_all([predecessor, tip])
        self.db.flush()
        predecessor.superseded_by_id = tip.id
        self.db.commit()

        hidden = CanonicalProspectiveObservationService(self.db).resolve(
            start=date(2025, 1, 1),
            end=date(2025, 4, 1),
            today=date(2025, 9, 1),
        )
        self.assertEqual(hidden, [])

        visible = CanonicalProspectiveObservationService(self.db).resolve(
            start=date(2025, 7, 1),
            end=date(2025, 9, 1),
            today=date(2025, 9, 1),
        )
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["schema"], SCHEMA)
        self.assertEqual(visible[0]["recommendation_id"], tip.id)
        self.assertEqual(set(visible[0]["chain_member_ids"]), {predecessor.id, tip.id})

    def test_windowed_reads_do_not_grow_per_observation(self):
        noise = []
        for index in range(90):
            noise.append(
                _rec(
                    as_of_date=date(2024, 1, 1) + timedelta(days=index),
                    is_active=False,
                    config_hash=f"noise-{index}",
                    generated_at=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
                )
            )
        predecessors = []
        tips = []
        for index in range(12):
            predecessors.append(
                _rec(
                    as_of_date=date(2024, 3, 1) + timedelta(days=index),
                    is_active=False,
                    config_hash=f"pred-{index}",
                    generated_at=datetime(2024, 3, 1, tzinfo=timezone.utc) + timedelta(days=index),
                )
            )
            tips.append(
                _rec(
                    as_of_date=date(2026, 6, 1) + timedelta(days=index),
                    is_active=True,
                    config_hash=f"tip-{index}",
                    generated_at=datetime(2026, 6, 1, tzinfo=timezone.utc) + timedelta(days=index),
                )
            )
        recs = noise + predecessors + tips
        self.db.add_all(recs)
        self.db.flush()
        for index in range(0, 90, 3):
            noise[index].superseded_by_id = noise[index + 1].id
            noise[index + 1].superseded_by_id = noise[index + 2].id
        for index in range(12):
            predecessors[index].superseded_by_id = tips[index].id
        old = []
        for index in range(1000):
            day = date(2020, 1, 1) + timedelta(days=index % 300)
            old.append(
                Activity(
                    activity_id=f"old-{index}",
                    activity_name="Old",
                    start_time=datetime(day.year, day.month, day.day, 8, tzinfo=timezone.utc),
                    duration=2000,
                    distance=5000,
                    activity_type_id=self.running.id,
                )
            )
        self.db.add_all(old)
        window_activities = []
        for index in range(12):
            day = date(2026, 6, 1) + timedelta(days=index)
            window_activities.append(
                Activity(
                    activity_id=f"win-{index}",
                    activity_name="Run",
                    start_time=datetime(2026, 6, 1 + index, 8, tzinfo=timezone.utc),
                    duration=3000,
                    distance=8000,
                    activity_type_id=self.running.id,
                )
            )
        self.db.add_all(window_activities)
        self.db.add_all(
            [
                AthleteFeedback(
                    activity_id=f"win-{index}",
                    recorded_at=datetime(2026, 6, 1 + index, 12, tzinfo=timezone.utc),
                    rpe=4,
                )
                for index in range(12)
            ]
        )
        self.db.add(
            RecommendationExecution(
                recommendation_id=tips[0].id,
                activity_id="win-0",
                execution_status="followed",
                planned_type="easy_run",
                actual_type="easy_run",
                linked_at=datetime(2026, 6, 1, 9, tzinfo=timezone.utc),
            )
        )
        self.db.commit()

        loaded_activities = {"n": 0}

        def count_activity(_target, _context):
            loaded_activities["n"] += 1

        event.listen(Activity, "load", count_activity)
        counts = _selects(self.engine)
        try:
            rows = CanonicalProspectiveObservationService(self.db).resolve(
                start=date(2026, 6, 1),
                end=date(2026, 6, 20),
                today=date(2026, 7, 1),
            )
        finally:
            event.remove(Activity, "load", count_activity)

        self.assertGreaterEqual(len(rows), 1)
        self.assertLess(counts["recommendation_records"], 8)
        self.assertLessEqual(counts["from activities"], 2)
        self.assertEqual(counts["athlete_feedback"], 1)
        self.assertLessEqual(counts["recommendation_executions"], 2)
        self.assertLess(loaded_activities["n"], 100)
        self.assertTrue(all(row["schema"] == SCHEMA for row in rows))
        self.assertNotIn("old-0", {row["activity_id"] for row in rows})


class ExplicitCoverageTests(unittest.TestCase):
    def test_low_recent_explicit_share_is_a_warning_not_a_weight_change(self):
        end = date(2026, 6, 30)
        observations = []
        for index in range(6):
            observations.append(
                {
                    "as_of_date": (end - timedelta(days=index)).isoformat(),
                    "match_source": "legacy_heuristic" if index else "explicit_execution",
                    "execution_status": "followed",
                    "match_reason": "legacy same-calendar-day running activity; no RecommendationExecution",
                    "evidence_weight": 0.35 if index else 1.0,
                }
            )
        report = explicit_execution_coverage(observations, end=end, window_days=90)
        self.assertEqual(report["status"], "EXPLICIT_EXECUTION_COVERAGE_LOW")
        self.assertEqual(report["last_30_days"]["closed_without_explicit"], 5)
        self.assertLess(report["last_30_days"]["explicit_share"], 0.5)
        self.assertEqual(report["historical"]["scope"], "selected_window")
        self.assertEqual(observations[1]["evidence_weight"], 0.35)
        self.assertTrue(report["last_30_days"]["missing_reasons"])

    def test_small_closed_sample_stays_insufficient(self):
        report = explicit_execution_coverage(
            [
                {
                    "as_of_date": "2026-06-01",
                    "match_source": "legacy_heuristic",
                    "execution_status": "skipped",
                    "match_reason": "execution window closed with no RecommendationExecution and no running activity",
                }
            ],
            end=date(2026, 6, 30),
            window_days=30,
        )
        self.assertEqual(report["status"], "INSUFFICIENT_DATA")
        self.assertFalse(report["last_90_days"]["complete"])
