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


if __name__ == "__main__":
    unittest.main()
