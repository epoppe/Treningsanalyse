"""Tests for Today dashboard HTTP wrapper."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class DashboardApiTests(unittest.TestCase):
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

    def test_today_composes_cockpit_payload(self):
        from app.main import app

        self._override(app)
        brief = {
            "status": "ok",
            "date": "2026-08-22",
            "persisted": False,
            "athlete_state_summary": {
                "fitness": {"value": 42, "trend": "improving"},
                "recovery": {"value": 72, "trend": "stable"},
                "fatigue": {"value": 48, "trend": "stable"},
            },
            "recommendation": {
                "workout_type": "threshold",
                "decision_status": "recommend",
                "duration_min": 58,
                "target_hr": [158, 164],
                "target_pace": [335, 345],
                "decision_confidence": 0.74,
                "evidence_strength": 0.68,
                "data_quality": 0.82,
            },
            "workout_prescription": {
                "title": "3 x 10 min controlled threshold",
                "total_duration_min": 58,
                "main_set": {
                    "repetitions": 3,
                    "work_duration_min": 10,
                    "recovery_duration_min": 2,
                },
            },
            "decision_explanation": {
                "decision": "threshold",
                "top_reasons": [{"code": "QUALITY_SESSION_DUE", "doc": "Spacing supports quality"}],
                "evidence_strength": 0.68,
                "decision_confidence": 0.74,
            },
            "plan": {
                "week_objective": "Build threshold",
                "sessions": [
                    {"day_offset": 0, "type": "threshold", "duration_min": 58},
                    {"day_offset": 1, "type": "easy_run", "duration_min": 50},
                ],
            },
            "goal": {"target_event": "half_marathon"},
            "training_phase": {"phase": "build"},
            "warnings": [],
            "system_health": "healthy",
            "data_freshness": {"lt2": {"status": "aging", "age_days": 46}},
        }
        with patch("app.routers.dashboard.CoachingOrchestrator") as orch:
            orch.return_value.training_decision_brief.return_value = brief
            client = TestClient(app)
            res = client.get("/api/dashboard/today")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["as_of"], "2026-08-22")
        self.assertEqual(body["recommendation"]["workout_type"], "threshold")
        self.assertEqual(body["recommendation"]["prescription"]["total_duration_min"], 58)
        self.assertTrue(body["athlete_state"]["dimensions"])
        self.assertEqual(body["weekly_plan"]["sessions"][0]["type"], "threshold")
        self.assertIn("decision_explanation", body)

    def test_what_changed_wraps_delta_service(self):
        from app.main import app

        self._override(app)
        before = {"id": 1, "recommended_workout_type": "easy_run", "input_context": {}}
        after = {"id": 2, "recommended_workout_type": "threshold", "input_context": {}}
        with patch("app.routers.dashboard.RecommendationLedgerService") as ledger_cls:
            ledger = ledger_cls.return_value
            ledger.get_latest_active_recommendation.side_effect = [before, after]
            with patch("app.routers.dashboard.CoachingOrchestrator") as orch:
                orch.return_value.generate_live_decision.return_value = {"status": "ok"}
                client = TestClient(app)
                res = client.get("/api/dashboard/what-changed", params={"refresh": "true"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["recommendation_changed"])


if __name__ == "__main__":
    unittest.main()
