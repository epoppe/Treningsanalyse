"""Regression tests for MCP derived metric calculation bugs."""

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.services.mcp_derived_metrics_service import McpDerivedMetricsService


class CardioDriftScoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.storage = MagicMock()
        self.service = McpDerivedMetricsService(self.db, self.storage)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_fallback_drift_does_not_shadow_median_function(self):
        """Tidligere: median=5.0 overskrev statistics.median → TypeError."""
        coaching_payload = {
            "thresholds": {
                "drift": {"recent_median_hr_drift_pct": 8.0},
            },
        }
        with patch.object(self.service, "_coaching", return_value=coaching_payload):
            score = self.service._cardio_drift_score(date(2026, 5, 31))
        self.assertEqual(score, 80.0)  # 100 - 8*2.5


class PredictedRaceTimeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.storage = MagicMock()
        self.service = McpDerivedMetricsService(self.db, self.storage)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    @patch.object(McpDerivedMetricsService, "_critical_speed")
    def test_predicted_5k_uses_critical_speed(self, mock_cs):
        mock_cs.return_value = {"critical_speed_mps": 4.0, "d_prime": 200.0}
        # (5000 - 200) / 4 = 1200 s
        result = self.service._predicted_race_time("predicted_5k_time", date.today())
        self.assertEqual(result, 1200.0)

    def test_running_activities_filter_uses_time_import(self):
        from app.services.performance_metrics_service import PerformanceMetricsService

        svc = PerformanceMetricsService(self.db, self.storage)
        # Skal ikke kaste NameError: name 'time' is not defined
        activities = svc._running_activities(days=30, end_date=date(2026, 5, 31))
        self.assertIsInstance(activities, list)


if __name__ == "__main__":
    unittest.main()
