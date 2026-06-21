#!/usr/bin/env python3
"""
Synkroniser aktivitetsliste fra Garmin måned for måned (uten FIT-nedlasting).

Garmin activitylist-API returnerer begrenset antall treff per spørring,
så vi chunker per måned.

Eksempler:
  python scripts/sync_activities_list.py --start 2024-01-01 --end 2026-05-25
  python scripts/sync_activities_list.py --start 2024-01-01 --end 2026-05-25 --ignore-sync-state
"""
from __future__ import annotations

import argparse
import asyncio
import calendar
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.services.garmin_client import GarminClient  # noqa: E402
from app.services.sync_service import SyncService  # noqa: E402
from app.storage import DataStorage  # noqa: E402


def month_ranges(start: date, end: date):
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        last_day = calendar.monthrange(y, m)[1]
        chunk_start = max(start, date(y, m, 1))
        chunk_end = min(end, date(y, m, last_day))
        yield chunk_start, chunk_end
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


async def run(start: date, end: date, ignore_sync_state: bool) -> None:
    db = SessionLocal()
    storage = DataStorage(settings.DATA_DIR)
    garmin = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR,
    )
    sync = SyncService(garmin, storage, db)
    total_added = 0
    try:
        for chunk_start, chunk_end in month_ranges(start, end):
            start_dt = datetime.combine(chunk_start, datetime.min.time(), tzinfo=timezone.utc)
            end_dt = datetime.combine(chunk_end, datetime.max.time(), tzinfo=timezone.utc)
            print(f"=== {chunk_start} -> {chunk_end} ===", flush=True)
            result = await sync.sync_activities(
                start_dt,
                end_dt,
                ignore_sync_state=ignore_sync_state,
                skip_fit_download=True,
            )
            added = int(result.get("total_fetched") or 0)
            total_added += added
            print(f"  status={result.get('status')} lagt_til={added}", flush=True)
    finally:
        db.close()
    print(f"\nFerdig. Totalt {total_added} nye aktiviteter lagt til.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Synk aktivitetsliste fra Garmin (måned for måned)")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--ignore-sync-state",
        action="store_true",
        default=True,
        help="Ignorer SyncState og bruk eksakt periode (default: på)",
    )
    parser.add_argument(
        "--respect-sync-state",
        action="store_true",
        help="Bruk SyncState for inkrementell synk (overstyrer default)",
    )
    args = parser.parse_args()
    ignore = args.ignore_sync_state and not args.respect_sync_state
    asyncio.run(run(args.start, args.end, ignore))


if __name__ == "__main__":
    main()
