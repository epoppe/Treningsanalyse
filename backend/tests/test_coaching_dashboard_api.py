"""Coaching dashboard API wraps orchestrator without algorithm changes."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class CoachingDashboardApiTests(unittest.TestCase):
    def tearDown(self):
        from app.main import app

        app.dependency_overrides.clear()

    def _override(self, app):
        from app.dependencies import get_db, get_data_storage

        def _db():
            yield MagicMock()

        def _storage():
            return MagicMock()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_data_storage] = _storage

    def test_today_endpoint_uses_preview(self):
        from app.main import app

        self._override(app)
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
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["brief"]["recommendation"]["workout_type"], "easy_run")
        self.assertFalse(body["persisted"])
        orch.return_value.preview_decision.assert_called()

    def test_plan_endpoint_normalizes_training_phase(self):
        from app.main import app

        self._override(app)
        brief = {
            "plan": {"sessions": [{"day_offset": 0, "type": "easy_run", "duration_min": [45, 60]}]},
            "plan_stability": "insufficient_data",
            "goal": {"goal_type": "general_fitness"},
            "training_phase": {
                "phase": "peak",
                "confidence": 0.55,
                "primary_objectives": ["sharpen race pace"],
            },
        }
        with patch("app.routers.coaching_dashboard.CoachingOrchestrator") as orch:
            orch.return_value.preview_decision.return_value = brief
            client = TestClient(app)
            res = client.get("/api/coaching/plan", params={"target_date": "2026-05-01"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["training_phase"], "peak")
        self.assertIsInstance(body["training_phase"], str)
        self.assertEqual(body["training_phase_detail"]["phase"], "peak")


if __name__ == "__main__":
    unittest.main()
