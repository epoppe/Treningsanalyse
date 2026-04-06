#!/usr/bin/env python3
import asyncio
from datetime import datetime, timezone, timedelta
from app.config import settings
from app.database.session import SessionLocal
from app.services.garmin_client import GarminClient
from app.storage import DataStorage
from app.services.sync_service import SyncService

CHUNK_DAYS = 180
START = datetime(2023, 1, 1, tzinfo=timezone.utc)
END = datetime.now(timezone.utc)

async def main():
    db = SessionLocal()
    try:
        gc = GarminClient(settings.GARMIN_EMAIL, settings.GARMIN_PASSWORD, settings.TOKEN_DIR)
        ok = await gc.initialize()
        print('garmin_init', ok)
        if not ok:
            return 2
        storage = DataStorage(settings.DATA_DIR)
        sync = SyncService(gc, storage, db)
        current = START
        i = 1
        while current <= END:
            chunk_end = min(current + timedelta(days=CHUNK_DAYS - 1), END)
            print(f'chunk {i}: {current.date()} -> {chunk_end.date()}')
            result = await sync.sync_activities_with_fit_data(
                current,
                chunk_end,
                force_refresh_recent=True,
                fit_data_limit=1000,
                ignore_sync_state=True,
                fit_download_mode='chunked'
            )
            print('result', result)
            current = chunk_end + timedelta(days=1)
            i += 1
        return 0
    finally:
        db.close()

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
