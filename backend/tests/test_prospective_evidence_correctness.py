"""Regression tests for the prospective evidence correctness pass."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models.activity import Activity, ActivityType
from app.database.models.base import Base
from app.database.models.coaching_v5 import RecommendationExecution, RecommendationRecord
from app.services.canonical_prospective_observation import CanonicalProspectiveObservationService
from app.services.coaching_operational_monitors import (
    DecisionConfidenceMonitor,
    ModelChangeImpactService,
    impact_verdict,
    summarize_calibration,
)
from app.services.prospective_evidence_report_service import ProspectiveEvidenceReportService
from app.services.prospective_outcome_lookup import ProspectiveOutcomeLookup
from app.services.recommendation_outcome_service import RecommendationOutcomeService
from app.services.recommendation_utility_evaluator import (
    RecommendationUtilityEvaluator,
    expected_recovery_cost_value,
    hrv_component_score,
    quality_session_type,
    session_quality_component,
)
from app.services.sample_sufficiency_policy import DOMAIN_FLOORS, SampleSufficiencyPolicy


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
        generated_at=datetime(2026, 1, 10, 8, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return RecommendationRecord(**defaults)


def _evaluator(**markers) -> RecommendationUtilityEvaluator:
    ppap = MagicMock()
    ppap.get_hrv_delta_pct.return_value = markers.get("hrv")
    ppap.get_rhr_delta_bpm.return_value = markers.get("rhr")
    ppap.get_tsb.return_value = markers.get("tsb")
    ppap.get_ctl.return_value = markers.get("ctl")
    return RecommendationUtilityEvaluator(db=None, ppap=ppap)


class HrvUtilityDirectionTests(unittest.TestCase):
    def test_component_is_monotonic_and_bounded(self):
        scores = [hrv_component_score(delta) for delta in (-20, -10, 0, 10, 20)]
        self.assertEqual(scores, [0.0, 0.25, 0.5, 0.75, 1.0])
        self.assertTrue(all(0.0 <= score <= 1.0 for score in scores))

    def test_missing_hrv_is_not_a_score(self):
        self.assertIsNone(hrv_component_score(None))

    def test_evaluator_does_not_reward_hrv_drop(self):
        as_of = date(2026, 1, 1)
        today = date(2026, 1, 10)
        scored = {}
        for delta in (-20, -10, 0, 10, 20):
            result = _evaluator(hrv=float(delta)).evaluate(
                recommended_type="easy_run",
                actual_type="easy_run",
                as_of=as_of,
                today=today,
            )
            scored[delta] = result["short_term_utility"]
            self.assertGreaterEqual(scored[delta], 0.0)
            self.assertLessEqual(scored[delta], 1.0)
        self.assertLess(scored[-20], scored[-10])
        self.assertLess(scored[-10], scored[0])
        self.assertLess(scored[0], scored[10])
        self.assertLess(scored[10], scored[20])

    def test_missing_hrv_does_not_lower_utility_when_rhr_is_neutral(self):
        result = _evaluator(hrv=None, rhr=0.0).evaluate(
            recommended_type="easy_run",
            actual_type="easy_run",
            as_of=date(2026, 1, 1),
            today=date(2026, 1, 10),
        )
        self.assertEqual(result["short_term_utility"], 0.5)

    def test_immature_hrv_drop_is_pending_not_a_low_score(self):
        as_of = date(2026, 5, 1)
        evaluator = _evaluator(hrv=-20.0)
        pending = evaluator.evaluate(
            recommended_type="easy_run",
            actual_type=None,
            as_of=as_of,
            today=as_of,
        )
        day_later = evaluator.evaluate(
            recommended_type="easy_run",
            actual_type=None,
            as_of=as_of,
            today=as_of + timedelta(days=1),
        )
        self.assertIsNone(pending["short_term_utility"])
        self.assertEqual(pending["short_term_maturity"], "pending")
        self.assertIsNone(day_later["short_term_utility"])
        self.assertEqual(day_later["short_term_maturity"], "pending")

    def test_medium_term_before_window_is_pending(self):
        as_of = date(2026, 5, 1)
        early = _evaluator(tsb=-30.0, ctl=40.0).evaluate(
            recommended_type="threshold",
            actual_type="threshold",
            as_of=as_of,
            today=as_of + timedelta(days=10),
        )
        self.assertIsNone(early["medium_term_utility"])
        self.assertEqual(early["medium_term_maturity"], "pending")


class RecoveryCostSplitTests(unittest.TestCase):
    def test_expected_cost_follows_recommendation_not_actual_session(self):
        evaluator = _evaluator(hrv=-10.0)
        as_of = date(2026, 1, 1)
        today = date(2026, 1, 10)
        easy = evaluator.evaluate(
            recommended_type="easy_run",
            actual_type="vo2_intervals",
            as_of=as_of,
            today=today,
            actual_load=95.0,
        )
        vo2 = evaluator.evaluate(
            recommended_type="vo2_intervals",
            actual_type="vo2_intervals",
            as_of=as_of,
            today=today,
            actual_load=95.0,
        )
        self.assertEqual(easy["expected_recovery_cost"]["value"], expected_recovery_cost_value("easy_run"))
        self.assertEqual(vo2["expected_recovery_cost"]["value"], expected_recovery_cost_value("vo2_intervals"))
        self.assertNotEqual(
            easy["expected_recovery_cost"]["value"],
            vo2["expected_recovery_cost"]["value"],
        )
        self.assertEqual(easy["observed_recovery_response"]["value"], vo2["observed_recovery_response"]["value"])
        self.assertEqual(easy["observed_recovery_response"]["actual_type"], "vo2_intervals")
        self.assertEqual(easy["observed_recovery_response"]["evaluation_kind"], "observational_outcome")
        self.assertEqual(easy["recovery_cost"], easy["observed_recovery_response"]["value"])

    def test_lower_hrv_raises_observed_stress_not_expected_cost(self):
        as_of = date(2026, 1, 1)
        today = date(2026, 1, 10)

        def _observed(delta: float) -> dict:
            return _evaluator(hrv=delta).evaluate(
                recommended_type="easy_run",
                actual_type="vo2_intervals",
                as_of=as_of,
                today=today,
            )

        low = _observed(-10.0)
        high = _observed(10.0)
        self.assertGreater(low["observed_recovery_response"]["value"], high["observed_recovery_response"]["value"])
        self.assertEqual(low["expected_recovery_cost"]["value"], high["expected_recovery_cost"]["value"])

    def test_missing_markers_do_not_invent_observed_cost(self):
        result = _evaluator().evaluate(
            recommended_type="threshold",
            actual_type="threshold",
            as_of=date(2026, 1, 1),
            today=date(2026, 1, 10),
        )
        self.assertIsNone(result["observed_recovery_response"]["value"])
        self.assertIsNone(result["recovery_cost"])
        self.assertIsNotNone(result["expected_recovery_cost"]["value"])


class CanonicalObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'canon.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.running = ActivityType(type_key="running", type_name="Running")
        self.db.add(self.running)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_supersede_chain_is_one_observation_and_shadow_is_excluded(self):
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
            is_active=False,
            config_hash="b",
            generated_at=datetime(2026, 3, 1, 8, tzinfo=timezone.utc),
        )
        third = _rec(
            as_of_date=day,
            recommended_workout_type="easy_run",
            is_active=True,
            config_hash="c",
            generated_at=datetime(2026, 3, 1, 9, tzinfo=timezone.utc),
        )
        shadow = _rec(
            as_of_date=day,
            recommended_workout_type="vo2_intervals",
            is_shadow=True,
            is_active=False,
            config_hash="shadow",
            generated_at=datetime(2026, 3, 1, 10, tzinfo=timezone.utc),
        )
        self.db.add_all([first, second, third, shadow])
        self.db.flush()
        first.superseded_by_id = second.id
        second.superseded_by_id = third.id
        self.db.commit()

        rows = CanonicalProspectiveObservationService(self.db).resolve(today=date(2026, 4, 1))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["recommendation_id"], third.id)
        self.assertTrue(rows[0]["canonical"])
        self.assertEqual(rows[0]["supersede_chain_length"], 3)
        self.assertEqual(set(rows[0]["chain_member_ids"]), {first.id, second.id, third.id})
        self.assertNotIn(shadow.id, rows[0]["chain_member_ids"])

        report = ProspectiveEvidenceReportService(self.db).report(
            start=day, end=day, window_days=1
        )
        self.assertEqual(report["recommendations"]["sample_count"], 1)
        self.assertEqual(report["sample_counts"]["canonical_observations"], 1)
        self.assertGreaterEqual(report["sample_counts"]["excluded_shadow_rows"], 1)
        self.assertGreaterEqual(report["sample_counts"]["excluded_superseded_or_duplicate"], 2)

    def test_same_day_tips_are_deterministic(self):
        day = date(2026, 3, 2)
        earlier = _rec(
            as_of_date=day,
            is_active=True,
            config_hash="early",
            recommended_workout_type="easy_run",
            generated_at=datetime(2026, 3, 2, 6, tzinfo=timezone.utc),
        )
        later = _rec(
            as_of_date=day,
            is_active=True,
            config_hash="late",
            recommended_workout_type="threshold",
            generated_at=datetime(2026, 3, 2, 18, tzinfo=timezone.utc),
        )
        self.db.add_all([earlier, later])
        self.db.commit()
        first = CanonicalProspectiveObservationService(self.db).resolve(today=date(2026, 4, 1))
        second = CanonicalProspectiveObservationService(self.db).resolve(today=date(2026, 4, 1))
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["recommendation_id"], later.id)
        self.assertEqual(first[0]["recommendation_id"], second[0]["recommendation_id"])
        self.assertIn("multiple_unlinked_same_day", first[0]["ledger_quality"])

    def test_broken_supersede_pointer_is_explicit(self):
        row = _rec(config_hash="dangling", is_active=True)
        self.db.add(row)
        self.db.flush()
        row.superseded_by_id = 99999
        self.db.commit()
        resolved = CanonicalProspectiveObservationService(self.db).resolve(today=date(2026, 4, 1))
        self.assertEqual(len(resolved), 1)
        self.assertIn("incomplete_supersede_graph", resolved[0]["ledger_quality"])

    def test_cycle_does_not_hang_and_is_one_observation(self):
        left = _rec(config_hash="left", is_active=False, recommended_workout_type="easy_run")
        right = _rec(
            config_hash="right",
            is_active=True,
            recommended_workout_type="threshold",
            generated_at=datetime(2026, 1, 10, 12, tzinfo=timezone.utc),
        )
        self.db.add_all([left, right])
        self.db.flush()
        left.superseded_by_id = right.id
        right.superseded_by_id = left.id
        self.db.commit()
        resolved = CanonicalProspectiveObservationService(self.db).resolve(today=date(2026, 4, 1))
        self.assertEqual(len(resolved), 1)
        self.assertIn("incomplete_supersede_graph", resolved[0]["ledger_quality"])
        self.assertEqual(resolved[0]["supersede_chain_length"], 2)

    def test_explicit_execution_beats_heuristic_activity(self):
        day = date(2026, 3, 5)
        record = _rec(as_of_date=day, recommended_workout_type="easy_run", config_hash="link")
        self.db.add(record)
        self.db.flush()
        heuristic = Activity(
            activity_id="heuristic-run",
            activity_name="Morning",
            start_time=datetime(2026, 3, 5, 7, tzinfo=timezone.utc),
            duration=3000,
            distance=8000,
            activity_type_id=self.running.id,
        )
        explicit = Activity(
            activity_id="explicit-run",
            activity_name="Intervals",
            start_time=datetime(2026, 3, 5, 18, tzinfo=timezone.utc),
            duration=2400,
            distance=6000,
            training_stress_score=88,
            activity_type_id=self.running.id,
        )
        self.db.add_all([heuristic, explicit])
        self.db.add(
            RecommendationExecution(
                recommendation_id=record.id,
                activity_id="explicit-run",
                execution_status="replaced",
                planned_type="easy_run",
                actual_type="vo2_intervals",
                linked_at=datetime(2026, 3, 5, 19, tzinfo=timezone.utc),
            )
        )
        self.db.commit()
        observation = CanonicalProspectiveObservationService(self.db).resolve(today=date(2026, 4, 1))[0]
        self.assertEqual(observation["activity_id"], "explicit-run")
        self.assertEqual(observation["actual_type"], "vo2_intervals")
        self.assertEqual(observation["match_source"], "explicit_execution")
        self.assertEqual(observation["match_confidence"], 1.0)
        self.assertEqual(observation["execution_status"], "replaced")

        outcome = RecommendationOutcomeService(self.db, None).evaluate_recorded_recommendation(
            record.id, today=date(2026, 4, 1)
        )
        self.assertEqual(outcome["activity_id"], "explicit-run")
        self.assertEqual(outcome["actual"], "vo2_intervals")
        self.assertEqual(outcome["match_source"], "explicit_execution")
        self.assertNotEqual(outcome["activity_id"], "heuristic-run")

    def test_legacy_fallback_is_labeled_and_lower_confidence(self):
        day = date(2026, 3, 6)
        record = _rec(as_of_date=day, config_hash="legacy")
        self.db.add(record)
        self.db.add(
            Activity(
                activity_id="only-run",
                activity_name="Easy",
                start_time=datetime(2026, 3, 6, 8, tzinfo=timezone.utc),
                duration=3000,
                distance=8000,
                activity_type_id=self.running.id,
            )
        )
        self.db.commit()
        observation = CanonicalProspectiveObservationService(self.db).resolve(today=date(2026, 4, 1))[0]
        self.assertEqual(observation["match_source"], "legacy_heuristic")
        self.assertLess(observation["match_confidence"], 1.0)
        self.assertIn("legacy", observation["match_reason"])
        self.assertEqual(observation["evidence_weight"], 0.35)

    def test_same_day_recommendation_before_session_is_pending(self):
        today = date(2026, 6, 1)
        self.db.add(_rec(as_of_date=today, config_hash="today", generated_at=datetime(2026, 6, 1, 8, tzinfo=timezone.utc)))
        self.db.commit()
        observation = CanonicalProspectiveObservationService(self.db).resolve(today=today)[0]
        self.assertEqual(observation["execution_status"], "pending")
        self.assertNotEqual(observation["execution_status"], "skipped")
        self.assertEqual(observation["observation_status"], "pending")
        self.assertEqual(observation["evidence_weight"], 0.0)

    def test_pending_does_not_inflate_short_term_denominator(self):
        today = date(2026, 6, 2)
        self.db.add(_rec(as_of_date=today, config_hash="open"))
        self.db.commit()
        report = ProspectiveEvidenceReportService(self.db).report(start=today, end=today)
        self.assertEqual(report["sample_counts"]["canonical_observations"], 1)
        self.assertEqual(report["sample_counts"]["short_term_recovery_outcomes"], 0)
        self.assertEqual(report["sample_counts"]["pending_short_term"], 1)
        self.assertEqual(report["recommendations"]["pending"], 1)
        self.assertEqual(report["recommendations"]["skipped"], 0)
        self.assertIsNone(report["outcomes"]["short_term_utility"])
        self.assertEqual(report["sample_counts"]["session_quality_outcomes"], 0)


class SessionQualityUtilityTests(unittest.TestCase):
    def test_component_maps_score_and_keeps_missing_empty(self):
        self.assertEqual(session_quality_component(80), 0.8)
        self.assertEqual(session_quality_component(0), 0.0)
        self.assertEqual(session_quality_component(140), 1.0)
        self.assertIsNone(session_quality_component(None))
        self.assertEqual(quality_session_type("easy_run"), "easy_aerobic")
        self.assertIsNone(quality_session_type("running"))
        self.assertIsNone(quality_session_type(None))

    def test_mature_quality_alone_is_the_short_term_score(self):
        result = _evaluator().evaluate(
            recommended_type="easy_run",
            actual_type="easy_aerobic",
            as_of=date(2026, 1, 1),
            today=date(2026, 1, 10),
            session_quality=80,
        )
        self.assertEqual(result["short_term_utility"], 0.8)
        self.assertEqual(result["short_term_maturity"], "evaluated")
        self.assertTrue(result["session_quality_included"])
        self.assertEqual(result["session_quality_component"], 0.8)

    def test_mature_quality_is_averaged_with_neutral_hrv(self):
        result = _evaluator(hrv=0.0).evaluate(
            recommended_type="easy_run",
            actual_type="easy_aerobic",
            as_of=date(2026, 1, 1),
            today=date(2026, 1, 10),
            session_quality=40,
        )
        self.assertEqual(result["short_term_utility"], 0.45)

    def test_pending_window_ignores_a_low_quality_score(self):
        as_of = date(2026, 5, 1)
        result = _evaluator().evaluate(
            recommended_type="easy_run",
            actual_type="easy_aerobic",
            as_of=as_of,
            today=as_of + timedelta(days=1),
            session_quality=10,
        )
        self.assertIsNone(result["short_term_utility"])
        self.assertEqual(result["short_term_maturity"], "pending")
        self.assertFalse(result["session_quality_included"])
        self.assertIsNone(result["session_quality_component"])

    def test_missing_quality_does_not_lower_neutral_hrv(self):
        result = _evaluator(hrv=0.0).evaluate(
            recommended_type="easy_run",
            actual_type="easy_aerobic",
            as_of=date(2026, 1, 1),
            today=date(2026, 1, 10),
            session_quality=None,
        )
        self.assertEqual(result["short_term_utility"], 0.5)
        self.assertFalse(result["session_quality_included"])

    def test_quality_does_not_change_expected_recovery_cost(self):
        kwargs = dict(
            recommended_type="threshold",
            actual_type="easy_aerobic",
            as_of=date(2026, 1, 1),
            today=date(2026, 1, 10),
        )
        without = _evaluator(hrv=0.0).evaluate(**kwargs)
        with_quality = _evaluator(hrv=0.0).evaluate(**kwargs, session_quality=20)
        self.assertEqual(
            without["expected_recovery_cost"]["value"],
            with_quality["expected_recovery_cost"]["value"],
        )
        self.assertEqual(without["expected_recovery_cost"]["value"], expected_recovery_cost_value("threshold"))
        self.assertNotEqual(without["short_term_utility"], with_quality["short_term_utility"])

    def test_score_lookup_skips_classifier_and_empty_components(self):
        evaluator = _evaluator()
        evaluator.db = MagicMock()
        self.assertIsNone(evaluator.session_quality_score(None, "easy_run"))
        self.assertIsNone(evaluator.session_quality_score("act-1", None))
        self.assertIsNone(evaluator.session_quality_score("act-1", "running"))
        evaluator.db.query.assert_not_called()

        activity = MagicMock()
        evaluator.db.query.return_value.filter.return_value.one_or_none.return_value = activity
        fake_quality = MagicMock()
        fake_quality.evaluate.return_value = {"quality_score": 80.0, "components": {"hr_drift": 90.0}}
        evaluator._quality = fake_quality
        self.assertEqual(evaluator.session_quality_score("act-1", "easy_run"), 80.0)
        fake_quality.evaluate.assert_called_once_with(activity, session_type="easy_aerobic")

        fake_quality.evaluate.return_value = {"quality_score": 70.0, "components": {}}
        self.assertIsNone(evaluator.session_quality_score("act-1", "long_run"))

    def test_report_counts_mature_quality_and_not_pending(self):
        tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(tmpdir.name) / 'quality.db'}")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        try:
            mature = date(2026, 1, 5)
            pending = date(2026, 4, 1)
            db.add(_rec(as_of_date=mature, config_hash="mature", recommended_workout_type="easy_run"))
            db.add(_rec(as_of_date=pending, config_hash="pending", recommended_workout_type="easy_run"))
            db.commit()
            report_service = ProspectiveEvidenceReportService(db)

            def _score(activity_id, session_type=None):
                return 80.0 if activity_id else None

            with patch.object(report_service._utility, "session_quality_score", side_effect=_score):
                with patch.object(report_service._utility._ppap, "get_hrv_delta_pct", return_value=None):
                    with patch.object(report_service._utility._ppap, "get_rhr_delta_bpm", return_value=None):
                        with patch.object(report_service._utility._ppap, "get_tsb", return_value=None):
                            with patch.object(report_service._utility._ppap, "get_ctl", return_value=None):
                                report = report_service.report(start=mature, end=pending)
            # No linked activity, so the patched score stays unused and pending
            # quality cannot enter the denominator.
            self.assertEqual(report["sample_counts"]["session_quality_outcomes"], 0)
            self.assertEqual(report["sample_counts"]["pending_short_term"], 1)
            self.assertIsNone(report["outcomes"]["short_term_utility"])

            def _linked(activity_id, session_type=None):
                return 80.0

            with patch.object(report_service._utility, "session_quality_score", side_effect=_linked):
                with patch.object(report_service._utility._ppap, "get_hrv_delta_pct", return_value=None):
                    with patch.object(report_service._utility._ppap, "get_rhr_delta_bpm", return_value=None):
                        with patch.object(report_service._utility._ppap, "get_tsb", return_value=None):
                            with patch.object(report_service._utility._ppap, "get_ctl", return_value=None):
                                linked = report_service.report(start=mature, end=pending)
            self.assertEqual(linked["sample_counts"]["session_quality_outcomes"], 1)
            self.assertEqual(linked["outcomes"]["session_quality_sample_count"], 1)
            self.assertEqual(linked["sample_counts"]["short_term_recovery_outcomes"], 1)
            self.assertEqual(linked["outcomes"]["short_term_utility"], 0.8)
            self.assertEqual(linked["sample_counts"]["pending_short_term"], 1)
        finally:
            db.close()
            tmpdir.cleanup()


class SampleSufficiencyAndLookupTests(unittest.TestCase):
    def test_policy_is_the_floor_source(self):
        self.assertEqual(DOMAIN_FLOORS["workout_effectiveness"]["emerging"], 10)
        assessed = SampleSufficiencyPolicy().assess(domain="workout_effectiveness", sample_count=8)
        self.assertEqual(assessed["level"], "INSUFFICIENT")
        weighted = SampleSufficiencyPolicy().assess_weighted(
            domain="execution_patterns",
            observation_dates=[date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
            evidence_weights=[0.35, 0.35, 0.35],
            as_of=date(2026, 2, 1),
        )
        full = SampleSufficiencyPolicy().assess_weighted(
            domain="execution_patterns",
            observation_dates=[date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
            evidence_weights=[1.0, 1.0, 1.0],
            as_of=date(2026, 2, 1),
        )
        self.assertLess(weighted["effective_sample_count"], full["effective_sample_count"])
        self.assertEqual(weighted["sample_count"], 3)

    def test_lookup_does_not_treat_adherence_as_effectiveness(self):
        tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(tmpdir.name) / 'lookup.db'}")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        try:
            record = _rec(
                as_of_date=date(2026, 1, 5),
                recommended_workout_type="easy_run",
                config_hash="followed",
            )
            db.add(record)
            db.flush()
            db.add(
                RecommendationExecution(
                    recommendation_id=record.id,
                    activity_id=None,
                    execution_status="followed",
                    planned_type="easy_run",
                    actual_type="easy_run",
                    overall_adherence=1.0,
                    linked_at=datetime(2026, 1, 5, 18, tzinfo=timezone.utc),
                )
            )
            db.commit()
            lookup = ProspectiveOutcomeLookup(db)
            with patch.object(lookup._utility._ppap, "get_hrv_delta_pct", return_value=None):
                with patch.object(lookup._utility._ppap, "get_rhr_delta_bpm", return_value=None):
                    with patch.object(lookup._utility._ppap, "get_tsb", return_value=None):
                        with patch.object(lookup._utility._ppap, "get_ctl", return_value=None):
                            result = lookup.historical_by_type(as_of=date(2026, 4, 1))
            row = result["easy_run"]
            self.assertGreater(row["feasibility"]["sample_count"], 0)
            self.assertEqual(row["effectiveness"]["sample_count"], 0)
            self.assertFalse(row["usable"])
            self.assertIsNone(row["value"])
            self.assertIn("level", row["feasibility"])
            self.assertIn("effective_sample_count", row["feasibility"])
        finally:
            db.close()
            tmpdir.cleanup()


class CalibrationAndImpactTests(unittest.TestCase):
    def test_small_sample_is_insufficient(self):
        report = summarize_calibration([(0.9, False)] * 5, considered=5, abstentions=0)
        self.assertEqual(report["status"], "INSUFFICIENT_DATA")
        self.assertLess(report["sample_count"], DOMAIN_FLOORS["confidence_calibration"]["emerging"])

    def test_perfect_calibration_is_recognized(self):
        pairs = [(0.8, True)] * 16 + [(0.8, False)] * 4 + [(0.2, True)] * 4 + [(0.2, False)] * 16
        report = summarize_calibration(pairs, considered=40, abstentions=0)
        self.assertEqual(report["status"], "well_calibrated")
        self.assertLess(report["expected_calibration_error"], 0.02)
        self.assertAlmostEqual(report["brier_score"], 0.16, places=2)

    def test_overconfidence_and_underconfidence(self):
        over = summarize_calibration([(0.9, False)] * 24 + [(0.9, True)] * 6, considered=30, abstentions=0)
        under = summarize_calibration([(0.2, True)] * 27 + [(0.2, False)] * 3, considered=30, abstentions=0)
        self.assertEqual(over["status"], "overconfident")
        self.assertEqual(under["status"], "underconfident")

    def test_monitor_empty_is_insufficient(self):
        tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(tmpdir.name) / 'cal.db'}")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        try:
            result = DecisionConfidenceMonitor(db).assess(start=date(2026, 1, 1), end=date(2026, 2, 1))
            self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        finally:
            db.close()
            tmpdir.cleanup()

    def test_distribution_change_without_outcomes_is_not_improvement(self):
        self.assertEqual(
            impact_verdict(
                before_n=12,
                after_n=12,
                unexpected_shift=True,
                abstention_status="APPROPRIATE",
                before_favorable_rate=None,
                after_favorable_rate=None,
                before_outcome_n=0,
                after_outcome_n=0,
            ),
            "possible_regression",
        )
        self.assertEqual(
            impact_verdict(
                before_n=12,
                after_n=12,
                unexpected_shift=False,
                abstention_status="APPROPRIATE",
                before_favorable_rate=None,
                after_favorable_rate=None,
                before_outcome_n=0,
                after_outcome_n=0,
            ),
            "no_material_change",
        )
        self.assertEqual(
            impact_verdict(
                before_n=12,
                after_n=12,
                unexpected_shift=False,
                abstention_status="APPROPRIATE",
                before_favorable_rate=0.2,
                after_favorable_rate=0.45,
                before_outcome_n=12,
                after_outcome_n=12,
            ),
            "consistent_with_improvement",
        )

    def test_compare_requires_outcome_evidence_for_improvement(self):
        tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(tmpdir.name) / 'impact.db'}")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        try:
            for offset in range(12):
                db.add(
                    _rec(
                        as_of_date=date(2026, 1, 1) + timedelta(days=offset),
                        config_hash=f"before-{offset}",
                        recommended_workout_type="easy_run",
                        decision_status="recommend",
                    )
                )
                db.add(
                    _rec(
                        as_of_date=date(2026, 2, 1) + timedelta(days=offset),
                        config_hash=f"after-{offset}",
                        recommended_workout_type="vo2_intervals",
                        decision_status="recommend",
                    )
                )
            db.commit()
            plain = ModelChangeImpactService().compare(
                db,
                before_start=date(2026, 1, 1),
                before_end=date(2026, 1, 20),
                after_start=date(2026, 2, 1),
                after_end=date(2026, 2, 20),
            )
            self.assertNotEqual(plain["verdict"], "consistent_with_improvement")
            self.assertIn(plain["verdict"], {"no_material_change", "possible_regression", "insufficient_evidence"})

            def _utility(self, as_of, *, today, session_quality=None):
                if as_of < date(2026, 2, 1):
                    return 0.2, "evaluated"
                return 0.9, "evaluated"

            with patch.object(RecommendationUtilityEvaluator, "_short_term_utility", _utility):
                improved = ModelChangeImpactService().compare(
                    db,
                    before_start=date(2026, 1, 1),
                    before_end=date(2026, 1, 20),
                    after_start=date(2026, 2, 1),
                    after_end=date(2026, 3, 1),
                )
            self.assertEqual(improved["verdict"], "consistent_with_improvement")
            self.assertGreaterEqual(improved["outcome_before"]["sample_count"], 10)
            self.assertGreater(improved["outcome_after"]["favorable_rate"], improved["outcome_before"]["favorable_rate"])
        finally:
            db.close()
            tmpdir.cleanup()


if __name__ == "__main__":
    unittest.main()
