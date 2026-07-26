"""Tester for PerformanceSyncService (ekstrahert fra SyncService)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.sync_modules.performance_sync_service import PerformanceSyncService
from app.services.sync_service import SyncService


class PerformanceSyncWiringTests(unittest.TestCase):
    def test_public_methods_exist(self):
        self.assertTrue(hasattr(PerformanceSyncService, "sync_garmin_performance_metrics"))
        self.assertTrue(hasattr(PerformanceSyncService, "sync_training_effect_data"))
        self.assertTrue(hasattr(PerformanceSyncService, "sync_training_effect_for_missing"))

    def test_sync_service_delegates(self):
        self.assertTrue(hasattr(SyncService, "sync_garmin_performance_metrics"))
        self.assertTrue(hasattr(SyncService, "sync_training_effect_data"))


class FillGradeAdjustedSpeedTests(unittest.TestCase):
    def test_skips_when_already_set(self):
        sync = MagicMock()
        service = PerformanceSyncService(sync)
        activity = SimpleNamespace(avg_grade_adjusted_speed=3.5, activity_id="1")
        self.assertFalse(service._fill_grade_adjusted_speed_from_fit(activity))
        sync.analysis_service.calculate_grade_adjusted_speed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
