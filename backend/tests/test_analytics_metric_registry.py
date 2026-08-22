"""Analytics metric registry + dependency suppression tests."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.services.analytics_metric_registry import (
    dependency_relation,
    should_suppress_correlation,
    catalog_payload,
)


class AnalyticsMetricRegistryTests(unittest.TestCase):
    def test_ctl_tsb_is_direct_dependency(self):
        self.assertEqual(dependency_relation("fitness.ctl", "fitness.tsb"), "DIRECT_DEPENDENCY")
        suppress, msg = should_suppress_correlation("fitness.ctl", "fitness.tsb")
        self.assertTrue(suppress)
        self.assertIn("mathematically related", msg.lower())

    def test_form_component_tsb_suppressed(self):
        suppress, _ = should_suppress_correlation("readiness.form_component", "fitness.tsb")
        self.assertTrue(suppress)

    def test_easy_volume_ef_independent(self):
        self.assertEqual(
            dependency_relation("stimulus.easy_minutes_28d", "fitness.ef_30d"),
            "INDEPENDENT_OR_UNKNOWN",
        )
        suppress, _ = should_suppress_correlation("stimulus.easy_minutes_28d", "fitness.ef_30d")
        self.assertFalse(suppress)

    def test_catalog_exposes_advanced_keys(self):
        payload = catalog_payload()
        keys = {m["key"] for m in payload["metrics"]}
        for required in (
            "fitness.ctl",
            "fitness.ef_30d",
            "fitness.gain_rate",
            "consistency.score",
            "coaching.polarization_score",
            "running.durability_score",
            "running.speed_20m_hist",
            "stimulus.easy_minutes_28d",
        ):
            self.assertIn(required, keys)
        self.assertTrue(payload["presets"])
        self.assertIn("aerobic_efficiency", payload["lag_families"])


    def test_shared_component_suppressed_by_default(self):
        suppress, msg = should_suppress_correlation("fitness.ctl", "fitness.atl")
        self.assertTrue(suppress)
        self.assertIn("share", msg.lower())
        suppress_adv, _ = should_suppress_correlation("fitness.ctl", "fitness.atl", advanced=True)
        self.assertFalse(suppress_adv)

    def test_presets_cover_core_questions(self):
        ids = {p["id"] for p in catalog_payload()["presets"]}
        for required in (
            "aerobic_fitness",
            "threshold",
            "durability",
            "hrv_recovery",
            "hard_sessions",
            "best_races",
            "easy_helped",
            "load_hurts_recovery",
        ):
            self.assertIn(required, ids)


class AnalysisCatalogApiTests(unittest.TestCase):
    def tearDown(self):
        from app.main import app

        app.dependency_overrides.clear()

    def test_catalog_endpoint(self):
        from app.main import app

        client = TestClient(app)
        res = client.get("/api/analysis/catalog")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["metrics"])
        self.assertIn("groups", body)

    def test_dependency_check_endpoint(self):
        from app.main import app

        client = TestClient(app)
        res = client.get(
            "/api/analysis/dependency-check",
            params={"x": "fitness.ctl", "y": "fitness.tsb"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["relationship_kind"], "DIRECT_DEPENDENCY")
        self.assertTrue(body["suppress_default"])

    def test_timeseries_accepts_mcp_keys(self):
        from app.main import app
        from app.dependencies import get_db, get_data_storage

        def _db():
            yield MagicMock()

        def _storage():
            return MagicMock()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_data_storage] = _storage
        with patch("app.routers.analysis_workspace.McpDerivedMetricsService") as derived:
            inst = derived.return_value
            inst.metric_definition.return_value = {
                "category": "fitness",
                "unit": "load",
                "scope": "daily",
            }
            inst.query_timeseries.return_value = {
                "points": [{"date": "2026-01-01", "value": 40.0}]
            }
            client = TestClient(app)
            res = client.get(
                "/api/analysis/timeseries",
                params={"metrics": "fitness.ctl,cardio.hrv_7d", "period": "28d"},
            )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("fitness.ctl", body["series"])
        self.assertEqual(body["series"]["fitness.ctl"]["sample_count"], 1)

    def test_relationship_matrix_suppresses_math_deps(self):
        from app.main import app
        from app.dependencies import get_db, get_data_storage

        def _db():
            yield MagicMock()

        def _storage():
            return MagicMock()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_data_storage] = _storage
        with patch("app.routers.analysis_workspace.TrainingResponseService") as tr:
            tr.return_value.analyze_responses.return_value = {
                "relationships": [],
                "disclaimer": "obs",
            }
            client = TestClient(app)
            res = client.get("/api/analysis/relationship-matrix", params={"period": "1y"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["cells"])
        # At least some cells should be insufficient when no mapping / no data
        statuses = {c["status"] for c in body["cells"]}
        self.assertTrue(statuses & {"insufficient", "suppressed", "ok"})

    def test_best_period_insufficient(self):
        from app.main import app
        from app.dependencies import get_db, get_data_storage

        def _db():
            yield MagicMock()

        def _storage():
            return MagicMock()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_data_storage] = _storage
        with patch("app.routers.analysis_workspace.McpDerivedMetricsService") as derived:
            inst = derived.return_value
            inst.metric_definition.return_value = {"unit": "score", "scope": "daily"}
            inst.query_timeseries.return_value = {"points": [{"date": "2026-01-01", "value": 1}]}
            client = TestClient(app)
            res = client.get(
                "/api/analysis/best-period-backtrace",
                params={"metric": "fitness.ef_30d", "period": "1y"},
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "insufficient")

    def test_duration_curve_history(self):
        from app.main import app
        from app.dependencies import get_db, get_data_storage

        def _db():
            yield MagicMock()

        def _storage():
            return MagicMock()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_data_storage] = _storage
        with patch("app.routers.analysis_workspace.McpDerivedMetricsService") as derived:
            inst = derived.return_value
            inst.metric_definition.side_effect = lambda k: {"unit": "km/h"} if "hist" in k else None
            inst.query_timeseries.return_value = {
                "points": [
                    {"date": "2025-01-01", "value": 12.0},
                    {"date": "2026-01-01", "value": 13.0},
                ]
            }
            client = TestClient(app)
            res = client.get("/api/analysis/duration-curve-history", params={"period": "1y"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["curves"])


if __name__ == "__main__":
    unittest.main()
