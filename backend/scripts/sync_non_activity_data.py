#!/usr/bin/env python3
"""
Synk alt fra Garmin unntatt aktiviteter, deretter beregn cache/MCP-verdier.

Eksempler:
  python scripts/sync_non_activity_data.py --start 2024-01-01 --end 2026-06-20
  python scripts/sync_non_activity_data.py --start 2024-01-01 --end 2026-06-20 --skip-training-effect
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
from app.database.models.activity import Activity  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.services.cache_calculation_service import CacheCalculationService  # noqa: E402
from app.services.garmin_client import GarminClient  # noqa: E402
from app.services.hrv_service import HRVService  # noqa: E402
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


def _dt_range(chunk_start: date, chunk_end: date):
    start_dt = datetime.combine(chunk_start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(chunk_end, datetime.max.time(), tzinfo=timezone.utc)
    return start_dt, end_dt


async def run(
    start: date,
    end: date,
    *,
    skip_training_effect: bool = False,
    skip_backfill: bool = False,
) -> None:
    db = SessionLocal()
    storage = DataStorage(settings.DATA_DIR)
    garmin = GarminClient(
        email=settings.GARMIN_EMAIL,
        password=settings.GARMIN_PASSWORD,
        token_dir=settings.TOKEN_DIR,
    )
    sync = SyncService(garmin, storage, db)
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)

    print(f"=== 1/6 Helsedata (måned for måned) {start} -> {end} ===", flush=True)
    for chunk_start, chunk_end in month_ranges(start, end):
        s, e = _dt_range(chunk_start, chunk_end)
        print(f"  helse {chunk_start} -> {chunk_end}", flush=True)
        await sync.sync_health_data(s, e, force_refresh_recent=False)

    print(f"=== 2/6 Garmin performance metrics {start} -> {end} ===", flush=True)
    for chunk_start, chunk_end in month_ranges(start, end):
        s, e = _dt_range(chunk_start, chunk_end)
        print(f"  performance {chunk_start} -> {chunk_end}", flush=True)
        result = await sync.sync_garmin_performance_metrics(
            s, e, force_refresh_recent=False, ignore_sync_state=True
        )
        print(f"    {result.get('status')} updated={result.get('updated_count', 0)}", flush=True)

    print(f"=== 3/6 HRV til database {start} -> {end} ===", flush=True)
    hrv = HRVService(storage)
    hrv_result = hrv.sync_hrv_data_to_database(
        db, start.isoformat(), end.isoformat()
    )
    print(f"  {hrv_result}", flush=True)

    if not skip_training_effect:
        print(f"=== 4/6 Training Effect {start} -> {end} ===", flush=True)
        te_result = await sync.sync_training_effect_data(
            start_dt, end_dt, force_refresh_recent=False, ignore_sync_state=True
        )
        print(f"  {te_result}", flush=True)
    else:
        print("=== 4/6 Training Effect hoppet over ===", flush=True)

    print(f"=== 5/6 Aktivitetsberegninger (cache) fra {start} ===", flush=True)
    cache = CacheCalculationService(db, storage)
    activities = (
        db.query(Activity)
        .filter(Activity.start_time >= start_dt, Activity.start_time <= end_dt)
        .order_by(Activity.start_time.asc())
        .all()
    )
    stats = {"processed": 0, "success": 0, "errors": 0}
    for i, activity in enumerate(activities, 1):
        try:
            result = cache.calculate_and_cache_activity(activity.activity_id, force_recalculate=False)
            stats["processed"] += 1
            if result.get("status") == "success":
                stats["success"] += 1
            elif result.get("status") == "error":
                stats["errors"] += 1
            if i % 50 == 0:
                print(f"  cache {i}/{len(activities)}", flush=True)
        except Exception as exc:
            stats["errors"] += 1
            print(f"  feil {activity.activity_id}: {exc}", flush=True)
    print(f"  cache ferdig: {stats}", flush=True)

    print("=== 6/6 Performance snapshots ===", flush=True)
    perf = PerformanceMetricsService(db, storage)
    snapshots = perf.recalculate_performance_snapshots()
    cs = snapshots.get("critical_speed", {}).get("outdoor", {})
    print(f"  critical_speed_mps={cs.get('critical_speed_mps')}", flush=True)

    db.close()

    if skip_backfill:
        return

    py = sys.executable
    scripts = [
        [py, "scripts/backfill_health_fields.py"],
        [py, "scripts/backfill_summary_fields.py"],
        [py, "scripts/backfill_derived_metrics.py", "--eligible-only"],
    ]
    for cmd in scripts:
        print(f"=== backfill: {' '.join(cmd[1:])} ===", flush=True)
        proc = subprocess.run(cmd, cwd=BACKEND, capture_output=True, text=True)
        if proc.stdout:
            print(proc.stdout[-2000:], flush=True)
        if proc.returncode != 0:
            print(f"  exit {proc.returncode}: {proc.stderr[-1000:]}", flush=True)

    print("=== MCP export ===", flush=True)
    proc = subprocess.run(
        [py, "scripts/generate_mcp_fresh_export.py"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    print(proc.stdout or proc.stderr, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Synk non-activity Garmin-data og beregn MCP-verdier")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--skip-training-effect", action="store_true")
    parser.add_argument("--skip-backfill", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        run(
            args.start,
            args.end,
            skip_training_effect=args.skip_training_effect,
            skip_backfill=args.skip_backfill,
        )
    )


if __name__ == "__main__":
    main()
