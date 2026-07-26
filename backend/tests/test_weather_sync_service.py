"""Tester for WeatherSyncService (ekstrahert fra SyncService)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.sync_modules.weather_sync_service import WeatherSyncService


class AggregateWeatherSnapshotsTests(unittest.TestCase):
    def test_empty(self):
        self.assertIsNone(WeatherSyncService.aggregate_weather_snapshots([]))

    def test_averages_numeric_fields(self):
        result = WeatherSyncService.aggregate_weather_snapshots(
            [
                {
                    "temperature": 10.0,
                    "wind_speed": 2.0,
                    "humidity": 40.0,
                    "wind_direction": 0.0,
                    "weather_condition": "clear",
                },
                {
                    "temperature": 20.0,
                    "wind_speed": 4.0,
                    "humidity": 60.0,
                    "wind_direction": 90.0,
                    "weather_condition": "clear",
                },
            ]
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["temperature"], 15.0)
        self.assertAlmostEqual(result["wind_speed"], 3.0)
        self.assertAlmostEqual(result["humidity"], 50.0)
        self.assertEqual(result["weather_condition"], "clear")
        # Vindretning 0° og 90° → ~45°
        self.assertAlmostEqual(result["wind_direction"], 45.0, places=1)


class WeatherAltitudeTests(unittest.TestCase):
    def test_average_elevation(self):
        sync = MagicMock()
        service = WeatherSyncService(sync)
        activity = SimpleNamespace(min_elevation=100.0, max_elevation=200.0)
        self.assertEqual(service.activity_weather_altitude(activity), 150.0)

    def test_missing_elevation(self):
        sync = MagicMock()
        service = WeatherSyncService(sync)
        activity = SimpleNamespace(min_elevation=None, max_elevation=None)
        self.assertIsNone(service.activity_weather_altitude(activity))


class BuildSamplePointsFallbackTests(unittest.TestCase):
    def test_route_fingerprint_fallback(self):
        sync = MagicMock()
        sync.storage.get_activity_details.return_value = None
        service = WeatherSyncService(sync)
        route = SimpleNamespace(
            start_latitude=59.9,
            start_longitude=10.7,
            centroid_latitude=None,
            centroid_longitude=None,
        )
        service.activity_route_fingerprint = MagicMock(return_value=route)
        activity = SimpleNamespace(
            activity_id="1",
            start_time=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        )
        points = service.build_weather_sample_points(activity)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["latitude"], 59.9)
        self.assertEqual(points[0]["longitude"], 10.7)


if __name__ == "__main__":
    unittest.main()
