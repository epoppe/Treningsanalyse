#!/usr/bin/env python3
"""Synkroniser Garmin performance metrics (VO2max, treningsstatus, load m.m.)."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.services.garmin_client import GarminClient  # noqa: E402
from app.services.sync_service import SyncService  # noqa: E402
from app.storage import DataStorage  # noqa: E402


async def run(start: date, end: date, force_refresh_recent: bool, ignore_sync_state: bool) -> dict:
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)

    db = SessionLocal()
    try:
        storage = DataStorage(settings.DATA_DIR)
        garmin = GarminClient(
            email=settings.GARMIN_EMAIL,
            password=settings.GARMIN_PASSWORD,
            token_dir=settings.TOKEN_DIR,
        )
        sync = SyncService(garmin, storage, db)
        return await sync.sync_garmin_performance_metrics(
            start_dt,
            end_dt,
            force_refresh_recent=force_refresh_recent,
            ignore_sync_state=ignore_sync_state,
        )
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Synk Garmin performance metrics")
    parser.add_argument("--days", type=int, default=90, help="Antall dager tilbake fra i dag")
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument(
        "--force-recent",
        action="store_true",
        default=True,
        help="Oppdater eksisterende rader for siste 7 dager (default: på)",
    )
    parser.add_argument(
        "--no-force-recent",
        action="store_false",
        dest="force_recent",
        help="Hopp over re-henting av eksisterende rader",
    )
    parser.add_argument(
        "--ignore-sync-state",
        action="store_true",
        default=True,
        help="Ignorer SyncState og synk hele perioden (default: på)",
    )
    args = parser.parse_args()

    end = args.end or date.today()
    start = args.start or (end - timedelta(days=args.days))

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(f"Synkroniserer Garmin performance metrics {start} -> {end} ...", flush=True)
    result = asyncio.run(
        run(start, end, args.force_recent, args.ignore_sync_state)
    )
    print(result, flush=True)
    if result.get("status") == "Feil":
        sys.exit(1)


if __name__ == "__main__":
    main()
