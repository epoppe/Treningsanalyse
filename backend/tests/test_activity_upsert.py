"""Tester for insert/update/unchanged av aktiviteter."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.activity_upsert import apply_activity_field_updates, is_richer_value


class RicherValueTests(unittest.TestCase):
    def test_fills_none(self):
        self.assertTrue(is_richer_value(None, 48.5))
        self.assertFalse(is_richer_value(48.5, None))

    def test_detects_changed_float(self):
        self.assertTrue(is_richer_value(48.0, 48.5))
        self.assertFalse(is_richer_value(48.5, 48.5))


class ApplyActivityFieldUpdatesTests(unittest.TestCase):
    def _activity(self, **kwargs):
        defaults = {
            "vo2_max": None,
            "vo2_max_precise": None,
            "average_heart_rate": None,
            "max_heart_rate": None,
            "temperature": None,
            "weather_condition": None,
            "total_training_effect": None,
            "epoc": None,
            "running_economy": 1.23,  # derived — skal ikke røres
            "detailed_metrics": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_fills_missing_rich_fields(self):
        activity = self._activity()
        changed, fields = apply_activity_field_updates(
            activity,
            {
                "vo2_max": 50.0,
                "vo2_max_precise": 50.4,
                "average_heart_rate": 145,
                "temperature": 12.0,
                "weather_condition": "garmin_list",
                "total_training_effect": 3.2,
            },
            overwrite=False,
        )
        self.assertTrue(changed)
        self.assertIn("vo2_max", fields)
        self.assertEqual(activity.vo2_max, 50.0)
        self.assertEqual(activity.vo2_max_precise, 50.4)
        self.assertEqual(activity.average_heart_rate, 145)
        self.assertEqual(activity.temperature, 12.0)
        self.assertEqual(activity.total_training_effect, 3.2)
        self.assertEqual(activity.running_economy, 1.23)

    def test_unchanged_when_same_data(self):
        activity = self._activity(vo2_max=50.0, average_heart_rate=140)
        changed, fields = apply_activity_field_updates(
            activity,
            {"vo2_max": 50.0, "average_heart_rate": 140},
            overwrite=False,
        )
        self.assertFalse(changed)
        self.assertEqual(fields, [])

    def test_updates_when_garmin_value_differs(self):
        activity = self._activity(vo2_max=48.0, epoc=None)
        changed, fields = apply_activity_field_updates(
            activity,
            {"vo2_max": 51.0, "epoc": 120.0},
            overwrite=False,
        )
        self.assertTrue(changed)
        self.assertEqual(activity.vo2_max, 51.0)
        self.assertEqual(activity.epoc, 120.0)
        self.assertIn("vo2_max", fields)
        self.assertIn("epoc", fields)

    def test_overwrite_updates_existing_but_skips_none(self):
        activity = self._activity(vo2_max=48.0, temperature=10.0)
        changed, _ = apply_activity_field_updates(
            activity,
            {"vo2_max": 52.0, "temperature": None},
            overwrite=True,
        )
        self.assertTrue(changed)
        self.assertEqual(activity.vo2_max, 52.0)
        self.assertEqual(activity.temperature, 10.0)

    def test_detailed_metrics_filled_when_missing(self):
        activity = self._activity(detailed_metrics=None)
        details = {"records": [{"hr": 120}]}
        changed, fields = apply_activity_field_updates(
            activity,
            {"detailed_metrics": details},
            overwrite=False,
        )
        self.assertTrue(changed)
        self.assertIn("detailed_metrics", fields)
        self.assertEqual(activity.detailed_metrics, details)


if __name__ == "__main__":
    unittest.main()
