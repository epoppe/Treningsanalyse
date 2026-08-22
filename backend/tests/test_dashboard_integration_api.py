"""Tests for Sprint F dashboard integration endpoints."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class DashboardIntegrationApiTests(unittest.TestCase):
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

    def test_decision_historical_support(self):
        from app.main import app

        self._override(app)
        with patch("app.routers.dashboard.DecisionHistoricalSupportService") as svc_cls:
            svc_cls.return_value.build.return_value = {
                "status": "ok",
                "items": [{"kind": "ledger", "label": "Tidligere anbefalinger"}],
            }
            client = TestClient(app)
            res = client.get(
                "/api/dashboard/decision-historical-support",
                params={"workout_type": "threshold"},
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["items"][0]["kind"], "ledger")

    def test_comparable_sessions(self):
        from app.main import app

        self._override(app)
        with patch("app.routers.dashboard.ComparableSessionService") as svc_cls:
            svc_cls.return_value.compare_to_personal_baseline.return_value = {
                "status": "ok",
                "activity_id": "123",
                "comparable_count": 4,
                "percentile_vs_comparable": 72.0,
                "matches": [],
            }
            client = TestClient(app)
            res = client.get("/api/dashboard/comparable-sessions", params={"activity_id": "123"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["comparable_count"], 4)


if __name__ == "__main__":
    unittest.main()
