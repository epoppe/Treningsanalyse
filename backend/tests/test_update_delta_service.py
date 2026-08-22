"""Tests for UpdateDeltaService."""

from __future__ import annotations

import unittest

from app.services.update_delta_service import UpdateDeltaService


class UpdateDeltaServiceTests(unittest.TestCase):
    def test_detects_recommendation_change(self):
        before = {
            "recommended_workout_type": "easy_run",
            "input_context": {"context_summary": {"readiness": 70, "hrv_delta_pct": 2.0}},
            "decision_trace": [{"factor": "hard_session_spacing", "effect": "supports_quality"}],
        }
        after = {
            "recommended_workout_type": "threshold",
            "input_context": {"context_summary": {"readiness": 72, "hrv_delta_pct": 6.0}},
            "decision_trace": [{"factor": "quality_session_due", "effect": "supports_quality"}],
        }
        delta = UpdateDeltaService().compute(before, after)
        self.assertTrue(delta["recommendation_changed"])
        self.assertEqual(delta["before_recommendation"], "easy_run")
        self.assertEqual(delta["after_recommendation"], "threshold")
        metrics = {c["metric"] for c in delta["material_changes"]}
        self.assertIn("hrv_delta_pct", metrics)

    def test_no_material_change_when_stable(self):
        rec = {
            "recommended_workout_type": "easy_run",
            "input_context": {"context_summary": {"readiness": 70, "hrv_delta_pct": 1.0}},
            "decision_trace": [],
        }
        delta = UpdateDeltaService().compute(rec, rec)
        self.assertFalse(delta["recommendation_changed"])
        self.assertEqual(delta["material_changes"], [])


if __name__ == "__main__":
    unittest.main()
