"""Isolert metrikk-beregning: timeout hopper over aktiviteten og senker confidence."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.services.coaching_health_service import CoachingHealthService
from app.services.evidence_quality_propagation import apply_data_quality_to_evidence
from app.services.sync_modules.activity_sync_service import ActivitySyncService
from app.desktop_backend import main as desktop_main
from app.services.sync_modules.metrics_service import SyncMetricsService
from app.services.sync_modules.metric_isolation import (
    DERIVED_METRICS_INCOMPLETE_FACTOR,
    IsolatedMetricCalculator,
    _isolation_test_worker,
    confidence_payload,
    derived_metrics_freshness,
    failure_result,
    merge_pending_metric_ids,
    run_metric_batch,
    update_derived_metrics_state,
)


class _FakeCalculator:
    def __init__(self, *, snapshot_ok: bool = True):
        self.ids: list[str] = []
        self.snapshot_ok = snapshot_ok
        self.closed = False

    def calculate(self, activity_id: str) -> dict:
        self.ids.append(str(activity_id))
        if activity_id == "hang":
            return failure_result("hang", timed_out=True, timeout_seconds=1)
        return {
            "activity_id": str(activity_id),
            "timed_out": False,
            "isolated_failure": False,
            "skipped": False,
            "errors": [],
            "tss_calculated": True,
            "power_calculated": False,
            "running_economy_calculated": False,
            "negative_split_calculated": False,
            "decoupling_calculated": False,
            "hrv_calculated": False,
        }

    def recalculate_snapshots(self) -> dict:
        return {"ok": self.snapshot_ok, "timed_out": not self.snapshot_ok}

    def close(self) -> None:
        self.closed = True


class MetricBatchContinuationTests(unittest.TestCase):
    def test_timeout_skips_one_activity_and_continues(self):
        calc = _FakeCalculator()
        batch = run_metric_batch(None, ["a", "hang", "b"], calculator=calc)

        self.assertEqual(calc.ids, ["a", "hang", "b"])
        self.assertEqual(batch["summary"]["skipped_activity_ids"], ["hang"])
        self.assertEqual(batch["summary"]["metrics_confidence"], "reduced")
        self.assertEqual(batch["summary"]["confidence_factor"], DERIVED_METRICS_INCOMPLETE_FACTOR)
        self.assertEqual(batch["summary"]["tss"], 2)
        self.assertFalse(calc.closed)

    def test_snapshot_timeout_lowers_confidence_after_successful_activities(self):
        calc = _FakeCalculator(snapshot_ok=False)
        batch = run_metric_batch(None, ["a"], calculator=calc)
        self.assertEqual(batch["summary"]["metrics_confidence"], "reduced")
        self.assertTrue(batch["summary"]["snapshot_timed_out"])

    def test_sync_keeps_base_commit_outside_metric_failure(self):
        source = inspect.getsource(ActivitySyncService.sync_activities)
        batch_source = inspect.getsource(ActivitySyncService._run_isolated_metric_batch)
        self.assertIn("base_sync_committed", source)
        self.assertIn("run_metric_batch", batch_source)
        self.assertEqual(source.count("merge_pending_metric_ids"), 2)
        self.assertLess(
            source.index("base_sync_committed = True"),
            source.index("_run_isolated_metric_batch"),
        )


class DerivedMetricsConfidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_success_clears_previous_skip(self):
        update_derived_metrics_state(self.db, skipped=["1", "2"], timed_out=["1"])
        update_derived_metrics_state(self.db, succeeded=["1"])
        fresh = derived_metrics_freshness(self.db)
        self.assertEqual(fresh["skipped_activity_ids"], ["2"])
        self.assertEqual(fresh["status"], "incomplete")
        self.assertEqual(fresh["confidence_factor"], DERIVED_METRICS_INCOMPLETE_FACTOR)

        payload = confidence_payload(self.db, activity_id="2")
        self.assertEqual(payload["metrics_confidence"], "reduced")
        other = confidence_payload(self.db, activity_id="9")
        self.assertEqual(other["metrics_confidence"], "normal")

    def test_pending_skipped_ids_join_the_next_batch(self):
        update_derived_metrics_state(self.db, timed_out=["old"])
        self.assertEqual(merge_pending_metric_ids(self.db, ["new"]), ["new", "old"])
        self.assertEqual(merge_pending_metric_ids(self.db, []), ["old"])

    def test_advice_confidence_drops_without_changing_decision(self):
        update_derived_metrics_state(self.db, timed_out=["42"])
        fresh = derived_metrics_freshness(self.db)
        adj = apply_data_quality_to_evidence(
            0.8,
            0.8,
            {
                "lt2": {"status": "fresh"},
                "hrv_baseline": {"status": "fresh"},
                "critical_speed": {"status": "fresh"},
                "derived_activity_metrics": fresh,
            },
        )
        self.assertEqual(adj["decision_confidence"], round(0.8 * DERIVED_METRICS_INCOMPLETE_FACTOR, 3))
        self.assertEqual(adj["evidence_strength"], round(0.8 * DERIVED_METRICS_INCOMPLETE_FACTOR, 3))
        self.assertIn("derived_metrics_incomplete", adj["quality_factors"])
        self.assertFalse(adj["decision_changed"])
        self.assertTrue(adj["confidence_reduced"])

    def test_health_freshness_marks_incomplete(self):
        ppap = MagicMock()
        ppap.storage = None
        service = CoachingHealthService(self.db, ppap)
        before = service._resolve_freshness(date.today())
        self.assertEqual(before["derived_activity_metrics"]["status"], "fresh")

        update_derived_metrics_state(self.db, timed_out=["7"])
        after = service._resolve_freshness(date.today())
        self.assertEqual(after["derived_activity_metrics"]["status"], "incomplete")
        self.assertIn("derived_metrics_incomplete", [
            finding["code"]
            for finding in service.report(date.today())["findings"]
            if finding["code"] == "derived_metrics_incomplete"
        ])


class ReviewFollowUpTests(unittest.TestCase):
    def test_desktop_entry_freezes_before_parsing_args(self):
        source = inspect.getsource(desktop_main)
        self.assertLess(source.index("freeze_support"), source.index("parse_args"))

    def test_snapshot_failure_is_not_reported_as_success(self):
        metrics = SyncMetricsService(MagicMock())
        with patch(
            "app.services.performance_metrics_service.PerformanceMetricsService",
            side_effect=RuntimeError("snapshot"),
        ):
            self.assertFalse(metrics._recalculate_performance_snapshots_once())

    def test_parent_cache_is_invalidated_from_worker_result(self):
        calc = IsolatedMetricCalculator(None)
        payload = {
            "activity_id": "55",
            "timed_out": False,
            "isolated_failure": False,
            "cache_invalidated": ["tss"],
            "tss_calculated": True,
        }
        with patch.object(calc, "_run", return_value=payload):
            with patch("app.cache.cache_manager.get_cache_manager") as get_cache:
                result = calc.calculate("55")
        get_cache.return_value.invalidate_activity.assert_called_once_with(
            "55",
            cache_types=["tss"],
        )
        self.assertFalse(result["timed_out"])


class ProcessIsolationTests(unittest.TestCase):
    def test_hanging_activity_is_killed_and_next_activity_runs(self):
        calc = IsolatedMetricCalculator(
            None,
            timeout_seconds=5,
            activity_target=_isolation_test_worker,
        )
        try:
            hung = calc.calculate("hang")
            nxt = calc.calculate("2")
        finally:
            calc.close()

        self.assertTrue(hung["timed_out"])
        self.assertTrue(hung["skipped"])
        self.assertFalse(nxt["timed_out"])
        self.assertTrue(nxt["tss_calculated"])
        self.assertEqual(nxt["activity_id"], "2")


if __name__ == "__main__":
    unittest.main()
