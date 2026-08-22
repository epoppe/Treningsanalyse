"""Tests for plan dashboard HTTP wrapper."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class PlanDashboardApiTests(unittest.TestCase):
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

    def test_plan_composes_cockpit_payload(self):
        from app.main import app

        self._override(app)
        weekly = {
            "plan_id": 12,
            "version": 2,
            "week_start": "2026-08-18",
            "week_objective": "Build threshold",
            "sessions": [
                {"day_offset": 0, "type": "threshold", "duration_min": 58},
                {"day_offset": 1, "type": "easy_run", "duration_min": 50},
            ],
        }
        meso = {
            "start": "2026-08-18",
            "weeks": 5,
            "selected_candidate": "balanced",
            "mesocycle": [{"week": 1, "phase": "build", "target_volume": [220, 320]}],
            "source": "personalized",
            "evidence_strength": 0.62,
            "note": "Weekly targets only",
        }
        adaptation = {
            "plan_status": "keep",
            "changes": [],
            "reason": ["no_quality_conflict"],
            "confidence": 0.7,
            "signals": {"hrv_delta_pct": 2.1},
            "note": "Does not change permanent athlete preferences.",
        }
        with patch("app.routers.dashboard.TrainingPlanStore") as store_cls:
            store = store_cls.return_value
            store.get_active_plan.return_value = weekly
            store.list_versions.return_value = [
                {
                    "version": 2,
                    "created_at": "2026-08-20T10:00:00+00:00",
                    "changes": [],
                    "reason": ["no_quality_conflict"],
                    "week_objective": "Build threshold",
                    "session_count": 2,
                }
            ]
            with patch("app.routers.dashboard.GoalContextService") as goal_cls:
                goal_cls.return_value.build.return_value = {"target_event": "half_marathon"}
                with patch("app.routers.dashboard.TrainingPhaseService") as phase_cls:
                    phase_cls.return_value.determine.return_value = {"phase": "build"}
                    with patch("app.routers.dashboard.WeeklyPlanService") as weekly_cls:
                        weekly_cls.return_value.build.return_value = weekly
                        with patch("app.routers.dashboard.PlanAdaptationService") as adapt_cls:
                            adapt_cls.return_value.assess.return_value = adaptation
                            with patch("app.routers.dashboard.MesocyclePlanner") as meso_cls:
                                meso_cls.return_value.plan.return_value = meso
                                with patch("app.routers.dashboard.PlanVsActualService") as pva_cls:
                                    pva_cls.return_value.compare.return_value = {
                                        "week_start": "2026-08-18",
                                        "days": [],
                                        "summary": {"planned_count": 2, "completed_count": 1},
                                    }
                                    with patch("app.routers.dashboard.PlanStabilityService") as stab_cls:
                                        stab_cls.return_value.from_history.return_value = {"status": "stable"}
                                        client = TestClient(app)
                                        res = client.get("/api/dashboard/plan")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["source"], "stored")
        self.assertEqual(body["weekly_plan"]["sessions"][0]["type"], "threshold")
        self.assertEqual(body["mesocycle"]["selected_candidate"], "balanced")
        self.assertEqual(body["plan_adaptation"]["plan_status"], "keep")
        self.assertEqual(len(body["version_history"]), 1)
        self.assertIn("vs_actual", body)


if __name__ == "__main__":
    unittest.main()
