"""Tester for batch-commit under aktivitetssynk."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.services.sync_service import ACTIVITY_SYNC_COMMIT_BATCH_SIZE, SyncService


class ActivitySyncBatchCommitTests(unittest.TestCase):
    def test_batch_size_is_100(self):
        self.assertEqual(ACTIVITY_SYNC_COMMIT_BATCH_SIZE, 100)

    def test_commit_activity_batch_flushes_parquet_then_db(self):
        service = SyncService.__new__(SyncService)
        service.db = MagicMock()
        service.storage = MagicMock()
        from app.services.sync_modules.activity_sync_service import ActivitySyncService

        service.activity_sync = ActivitySyncService(service)
        buffered = [{"activity_id": 1}, {"activity_id": 2}]
        refreshed = [1]

        service._commit_activity_batch(
            buffered_parquet_records=buffered,
            refreshed_parquet_activity_ids=refreshed,
        )

        service.storage.save_activity_details.assert_called_once_with(
            [{"activity_id": 1}, {"activity_id": 2}],
            replace_activity_ids=[1],
        )
        service.db.commit.assert_called_once()
        self.assertEqual(buffered, [])
        self.assertEqual(refreshed, [])

    def test_commit_activity_batch_without_parquet(self):
        service = SyncService.__new__(SyncService)
        service.db = MagicMock()
        service.storage = MagicMock()
        from app.services.sync_modules.activity_sync_service import ActivitySyncService

        service.activity_sync = ActivitySyncService(service)

        service._commit_activity_batch()

        service.storage.save_activity_details.assert_not_called()
        service.db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
