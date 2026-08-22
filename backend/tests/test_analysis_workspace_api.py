"""Tests for analysis workspace HTTP wrappers (no algorithm changes)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class AnalysisWorkspaceApiTests(unittest.TestCase):
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

    def test_development_composes_domain_cards(self):
        from app.main import app

        self._override(app)
        trends = {
            "end_date": "2026-05-01",
            "windows_days": [28, 90, 365],
            "metrics": {
                "ctl": {
                    "90d": {
                        "metric": "ctl",
                        "current": 42.0,
                        "relative_change_pct": 4.2,
                        "direction": "improving",
                        "sample_count": 20,
                        "confidence": 0.7,
                        "change_point_detected": False,
                        "higher_is_better": True,
                    }
                },
                "hrv_rmssd": {
                    "90d": {
                        "metric": "hrv_rmssd",
                        "current": 55.0,
                        "relative_change_pct": -1.0,
                        "direction": "stable",
                        "sample_count": 18,
                        "confidence": 0.6,
                        "change_point_detected": False,
                        "higher_is_better": True,
                    }
                },
            },
        }
        with patch("app.routers.analysis_workspace.TrendAnalysisService") as trend:
            trend.return_value.analyze_all.return_value = trends
            client = TestClient(app)
            res = client.get("/api/analysis/development", params={"period": "90d"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["domains"])
        fitness = next(d for d in body["domains"] if d["domain"] == "fitness")
        self.assertEqual(fitness["direction"], "improving")
        self.assertEqual(fitness["evidence"], "supported")

    def test_timeseries_rejects_unknown_metric(self):
        from app.main import app

        self._override(app)
        client = TestClient(app)
        res = client.get(
            "/api/analysis/timeseries",
            params={"metrics": "not_a_metric", "period": "28d"},
        )
        self.assertEqual(res.status_code, 400)

    def test_relationships_uses_training_response(self):
        from app.main import app

        self._override(app)
        with patch("app.routers.analysis_workspace.TrainingResponseService") as svc:
            svc.return_value.analyze_responses.return_value = {
                "relationships": [
                    {
                        "stimulus": "easy_volume",
                        "outcome": "easy_efficiency",
                        "lag_days": 21,
                        "relationship": "positive",
                        "effect_size": 0.4,
                        "statistical_support": "moderate",
                        "sample_count": 16,
                    }
                ],
                "ranking_eligible_relationships": [],
                "multiple_testing": {},
                "disclaimer": "observational",
            }
            client = TestClient(app)
            res = client.get("/api/analysis/relationships", params={"period": "1y"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        card = next(c for c in body["cards"] if c["id"] == "easy_volume_efficiency")
        self.assertEqual(card["association"], "positive")
        self.assertEqual(card["lag_days"], 21)
        self.assertIn("ikke årsak", card["wording"])


if __name__ == "__main__":
    unittest.main()
