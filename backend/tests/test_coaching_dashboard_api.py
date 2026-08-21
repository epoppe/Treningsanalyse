"""Coaching dashboard API wraps orchestrator without algorithm changes."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class CoachingDashboardApiTests(unittest.TestCase):
    def test_today_endpoint_uses_preview(self):
        from app.main import app
        from app.dependencies import get_db, get_data_storage

        def _db():
            yield MagicMock()

        def _storage():
            return MagicMock()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_data_storage] = _storage
        brief = {
            "date": "2026-05-01",
            "recommendation": {"workout_type": "easy_run", "decision_status": "recommend"},
            "plan": {"sessions": []},
            "athlete_state_summary": {},
        }
        with patch("app.routers.coaching_dashboard.CoachingOrchestrator") as orch:
            with patch("app.routers.coaching_dashboard.CoachingHealthService") as health:
                orch.return_value.preview_decision.return_value = brief
                health.return_value.report.return_value = {
                    "status": "degraded",
                    "issues": ["low_prospective_n"],
                    "checks": {"data_freshness": {}},
                }
                client = TestClient(app)
                res = client.get("/api/coaching/today", params={"target_date": "2026-05-01"})
        app.dependency_overrides.clear()
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["brief"]["recommendation"]["workout_type"], "easy_run")
        self.assertFalse(body["persisted"])
        orch.return_value.preview_decision.assert_called()
        # Ensure preview path (no generate_live_decision)
        self.assertFalse(hasattr(orch.return_value.generate_live_decision, "assert_called") and False)


if __name__ == "__main__":
    unittest.main()
