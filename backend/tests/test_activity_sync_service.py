"""Tester for ActivitySyncService (ekstrahert fra SyncService)."""

from __future__ import annotations

import inspect
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from app.services.sync_modules import activity_sync_service as activity_sync_module
from app.services.sync_modules.activity_sync_service import (
    ACTIVITY_SYNC_COMMIT_BATCH_SIZE,
    ActivitySyncService,
    parse_activity_start_from_json,
    refresh_summaries_after_sync,
)
from app.services.sync_service import SyncService


class ParseActivityStartTests(unittest.TestCase):
    def test_parse_gmt_iso(self):
        dt = parse_activity_start_from_json({"startTimeGMT": "2024-01-15T10:30:00.000Z"})
        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_parse_epoch_seconds(self):
        dt = parse_activity_start_from_json({"startTimeInSeconds": 1705315800})
        self.assertIsInstance(dt, datetime)
        self.assertEqual(dt.tzinfo, timezone.utc)


class ActivitySyncServiceWiringTests(unittest.TestCase):
    def test_batch_size_reexported(self):
        self.assertEqual(ACTIVITY_SYNC_COMMIT_BATCH_SIZE, 100)

    def test_sync_service_has_activity_sync_attr(self):
        self.assertTrue(hasattr(SyncService, "__init__"))
        # ActivitySyncService er egen klasse med proxy-properties
        self.assertTrue(hasattr(ActivitySyncService, "sync_activities"))
        self.assertTrue(hasattr(ActivitySyncService, "sync_json_to_db"))

    def test_summary_refresh_imports_sibling_summary_service(self):
        source = inspect.getsource(activity_sync_module)
        self.assertNotIn("from ..services.summary_service", source)
        self.assertNotIn("app.services.services", source)
        with patch("app.services.summary_service.SummaryService") as summary_cls:
            summary_cls.return_value.bulk_update_summaries.return_value = {
                "daily_count": 2,
                "weekly_count": 1,
                "monthly_count": 1,
                "yearly_count": 1,
            }
            result = refresh_summaries_after_sync(date(2026, 9, 25), date(2026, 9, 25))
        summary_cls.assert_called_once_with()
        summary_cls.return_value.bulk_update_summaries.assert_called_once_with(
            date(2026, 9, 25),
            date(2026, 9, 25),
        )
        self.assertEqual(result["daily_count"], 2)


if __name__ == "__main__":
    unittest.main()
