"""Integrasjonstester for GarminClient sin databruk mot garminconnect-transporten.

Fokus: at daglig-sync-metodene (1) bruker autentisert session, (2) feiler
kontrollert (propagerer) ved re-auth, og (3) er tolerante for 404/manglende data.
"""

import tempfile
import unittest
from datetime import datetime, timezone

from app.services.garmin_client import GarminClient
from app.services.garmin_auth import (
    GarminNotFoundError,
    GarminRateLimitError,
    GarminReauthRequiredError,
)


class FakeAuth:
    """Minimal erstatning for GarminAuthManager i GarminClient-tester."""

    def __init__(self):
        self.is_authenticated = True
        self.display_name = "fake-user"
        self.connectapi_hook = None
        self.download_hook = None

    def connectapi(self, path, **kwargs):
        return self.connectapi_hook(path, **kwargs)

    def download(self, path, **kwargs):
        return self.download_hook(path, **kwargs)


class GarminClientSyncTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.client = GarminClient("user@example.com", "secret", self._tmp.name)
        self.auth = FakeAuth()
        self.client.auth = self.auth  # injiser fake transport/auth

    def tearDown(self):
        self._tmp.cleanup()

    async def test_get_activities_returns_list(self):
        self.auth.connectapi_hook = lambda path, **kw: [{"activityId": 1}]
        result = await self.client.get_activities(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(result, [{"activityId": 1}])

    async def test_get_activities_propagates_reauth(self):
        def hook(path, **kw):
            raise GarminReauthRequiredError("401")

        self.auth.connectapi_hook = hook
        with self.assertRaises(GarminReauthRequiredError):
            await self.client.get_activities(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            )

    async def test_get_activities_tolerates_rate_limit(self):
        def hook(path, **kw):
            raise GarminRateLimitError("429")

        self.auth.connectapi_hook = hook
        result = await self.client.get_activities(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(result, [])

    async def test_get_activity_details_returns_bytes(self):
        self.auth.download_hook = lambda path, **kw: b"fit"
        result = await self.client.get_activity_details("123")
        self.assertEqual(result, b"fit")

    async def test_get_activity_details_not_found_returns_none(self):
        def hook(path, **kw):
            raise GarminNotFoundError("404")

        self.auth.download_hook = hook
        result = await self.client.get_activity_details("123")
        self.assertIsNone(result)

    async def test_get_activity_details_propagates_reauth(self):
        def hook(path, **kw):
            raise GarminReauthRequiredError("401")

        self.auth.download_hook = hook
        with self.assertRaises(GarminReauthRequiredError):
            await self.client.get_activity_details("123")

    async def test_get_sleep_data_not_found_returns_none(self):
        def hook(path, **kw):
            raise GarminNotFoundError("404")

        self.auth.connectapi_hook = hook
        result = await self.client.get_sleep_data(datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertIsNone(result)

    async def test_get_sleep_data_propagates_reauth(self):
        def hook(path, **kw):
            raise GarminReauthRequiredError("401")

        self.auth.connectapi_hook = hook
        with self.assertRaises(GarminReauthRequiredError):
            await self.client.get_sleep_data(datetime(2026, 1, 1, tzinfo=timezone.utc))

    async def test_daily_performance_metrics_propagates_reauth(self):
        def hook(path, **kw):
            raise GarminReauthRequiredError("401")

        self.auth.connectapi_hook = hook
        with self.assertRaises(GarminReauthRequiredError):
            await self.client.get_daily_garmin_performance_metrics("2026-01-01")

    async def test_not_authenticated_returns_empty(self):
        self.auth.is_authenticated = False
        result = await self.client.get_activities(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(result, [])

    # ---- HRV: /hrv-service/hrv/{date} med camelCase hrvSummary ----
    async def test_fetch_hrv_live_parses_camelcase_summary(self):
        def hook(path, **kw):
            assert path == "/hrv-service/hrv/2026-06-30", path
            return {
                "hrvSummary": {
                    "lastNightAvg": 31,
                    "lastNight5MinHigh": 44,
                    "weeklyAvg": 36,
                    "status": "BALANCED",
                    "baseline": {"lowUpper": 30, "balancedLow": 32, "balancedUpper": 41},
                }
            }

        self.auth.connectapi_hook = hook
        res = await self.client.fetch_hrv_live(datetime(2026, 6, 30, tzinfo=timezone.utc))
        self.assertEqual(res.live_status, "ok")
        self.assertIsNotNone(res.data)
        self.assertEqual(res.data["hrv_summary"]["last_night_avg"], 31)
        self.assertEqual(res.data["hrv_summary"]["weekly_avg"], 36)
        self.assertEqual(res.data["hrv_summary"]["baseline_balanced_upper"], 41)

    async def test_fetch_hrv_live_not_found(self):
        def hook(path, **kw):
            raise GarminNotFoundError("404")

        self.auth.connectapi_hook = hook
        res = await self.client.fetch_hrv_live(datetime(2026, 6, 30, tzinfo=timezone.utc))
        self.assertEqual(res.live_status, "not_found")
        self.assertIsNone(res.data)

    # ---- Body Battery: /wellness-service/wellness/bodyBattery/reports/daily ----
    async def test_get_body_battery_reports_daily(self):
        def hook(path, **kw):
            assert "bodyBattery/reports/daily" in path, path
            return [{
                "date": "2026-07-01",
                "charged": 41,
                "drained": 61,
                "bodyBatteryValuesArray": [
                    [1782856800000, 45],
                    [1782881640000, 82],
                    [1782936540000, 21],
                ],
            }]

        self.auth.connectapi_hook = hook
        res = await self.client.get_body_battery_data(datetime(2026, 7, 1, tzinfo=timezone.utc))
        self.assertIsNotNone(res)
        self.assertEqual(res["body_battery_charged"], 41)
        self.assertEqual(res["body_battery_drained"], 61)
        self.assertEqual(res["max_body_battery"], 82)
        self.assertEqual(res["min_body_battery"], 21)
        self.assertEqual(res["net_charge"], -20)
        # Verdi-array normalisert til [ts, status, value, x]
        self.assertEqual(res["body_battery_values_array"][0][2], 45)

    # ---- Stress: /wellness-service/wellness/dailyStress/{date} med bucket-beregning ----
    async def test_get_stress_data_computes_buckets(self):
        base = 1_782_770_400_000
        interval = 180_000  # 3 min
        values = []
        # 10 hvile (10), 5 lav (40), 2 middels (60), 1 høy (90), 1 ikke målt (-1)
        levels = [10] * 10 + [40] * 5 + [60] * 2 + [90] * 1 + [-1] * 1
        for i, lvl in enumerate(levels):
            values.append([base + i * interval, lvl])

        def hook(path, **kw):
            assert "dailyStress" in path, path
            return {
                "calendarDate": "2026-06-30",
                "avgStressLevel": 28,
                "maxStressLevel": 90,
                "stressValuesArray": values,
            }

        self.auth.connectapi_hook = hook
        res = await self.client.get_stress_data(datetime(2026, 6, 30, tzinfo=timezone.utc))
        self.assertIsNotNone(res)
        self.assertEqual(res["stress_level"], 28)
        self.assertEqual(res["rest_time"], 30)     # 10 * 3
        self.assertEqual(res["low_stress_time"], 15)   # 5 * 3
        self.assertEqual(res["medium_stress_time"], 6)  # 2 * 3
        self.assertEqual(res["high_stress_time"], 3)    # 1 * 3
        self.assertEqual(res["stress_time"], 24)    # low+medium+high
        self.assertEqual(res["total_time"], 54)     # rest + stress

    async def test_get_stress_data_no_values_returns_none(self):
        self.auth.connectapi_hook = lambda path, **kw: {"calendarDate": "2026-06-30"}
        res = await self.client.get_stress_data(datetime(2026, 6, 30, tzinfo=timezone.utc))
        self.assertIsNone(res)


class GarminParserUnitTests(unittest.TestCase):
    def test_map_hrv_summary_snake_and_camel(self):
        out = GarminClient._map_hrv_summary({
            "lastNightAvg": 40, "weeklyAvg": 42, "status": "BALANCED",
            "baseline": {"lowUpper": 30, "balancedLow": 35, "balancedUpper": 48},
        })
        s = out["hrv_summary"]
        self.assertEqual(s["last_night_avg"], 40)
        self.assertEqual(s["baseline_balanced_lower"], 35)
        self.assertEqual(s["baseline_low_upper"], 30)

    def test_map_hrv_summary_missing_last_night(self):
        self.assertIsNone(GarminClient._map_hrv_summary({"weeklyAvg": 42}))
        self.assertIsNone(GarminClient._map_hrv_summary(None))

    def test_compute_stress_buckets_interval_from_timestamps(self):
        base = 1_000_000_000_000
        vals = [[base, 10], [base + 60_000, 40], [base + 120_000, 90]]  # 1-min intervaller
        out = GarminClient._compute_stress_buckets("2026-06-30", {
            "avgStressLevel": 33, "stressValuesArray": vals,
        })
        self.assertEqual(out["rest_time"], 1)
        self.assertEqual(out["low_stress_time"], 1)
        self.assertEqual(out["high_stress_time"], 1)
        self.assertEqual(out["stress_time"], 2)
        self.assertEqual(out["total_time"], 3)


if __name__ == "__main__":
    unittest.main()
