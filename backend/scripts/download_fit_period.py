#!/usr/bin/env python3
"""
Last ned manglende FIT-data måned for måned, deretter backfill og MCP-export.

Eksempler:
  python scripts/download_fit_period.py --start 2024-01-01 --end 2026-06-20
"""
from __future__ import annotations

import argparse
import asyncio
import calendar
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.services.garmin_client import GarminClient  # noqa: E402
from app.services.performance_metrics_service import PerformanceMetricsService  # noqa: E402
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


async def run(start: date, end: date) -> None:
    db = SessionLocal()
    storage = DataStorage(settings.DATA_DIR)
    garmin = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR,
    )
    sync = SyncService(garmin, storage, db)
    total_ok = 0
    total_missing = 0

    print(f"=== FIT-nedlasting {start} -> {end} (måned for måned) ===", flush=True)
    for chunk_start, chunk_end in month_ranges(start, end):
        start_dt = datetime.combine(chunk_start, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(chunk_end, datetime.max.time(), tzinfo=timezone.utc)
        print(f"--- {chunk_start} -> {chunk_end} ---", flush=True)
        result = await sync.download_fit_data_for_period(start_dt, end_dt)
        ok = int(result.get("success_count") or 0)
        total = int(result.get("total_count") or 0)
        total_ok += ok
        total_missing += total
        print(f"  {result.get('status')}: {ok}/{total} lastet ned", flush=True)

    print(f"\nFIT totalt: {total_ok}/{total_missing} lastet ned", flush=True)

    perf = PerformanceMetricsService(db, storage)
    perf.recalculate_performance_snapshots()
    print("Performance snapshots oppdatert", flush=True)
    db.close()

    py = sys.executable
    for script_args in (
        ["scripts/backfill_derived_metrics.py", "--eligible-only"],
        ["scripts/backfill_grade_adjusted_speed.py"],
        ["scripts/generate_mcp_fresh_export.py"],
    ):
        print(f"=== {' '.join(script_args)} ===", flush=True)
        proc = subprocess.run([py, *script_args], cwd=BACKEND, capture_output=True, text=True)
        out = (proc.stdout or proc.stderr or "").strip()
        if out:
            # Unngå Windows cp1252-feil ved utskrift av spesialtegn
            safe = out.encode("ascii", errors="replace").decode("ascii")
            print(safe[-2500:], flush=True)
        if proc.returncode != 0:
            print(f"  exit code {proc.returncode}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Last ned manglende FIT og backfill MCP")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    asyncio.run(run(args.start, args.end))


if __name__ == "__main__":
    main()
