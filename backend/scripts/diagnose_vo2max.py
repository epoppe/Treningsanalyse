#!/usr/bin/env python3
"""Diagnostiser VO2 max-data i lokal database."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import func  # noqa: E402

from app.database.models.activity import Activity, GarminPerformanceMetric  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        total = db.query(func.count(Activity.activity_id)).scalar() or 0
        with_vo2 = (
            db.query(func.count(Activity.activity_id))
            .filter(Activity.vo2_max.isnot(None), Activity.vo2_max > 0)
            .scalar()
            or 0
        )
        with_precise = (
            db.query(func.count(Activity.activity_id))
            .filter(Activity.vo2_max_precise.isnot(None), Activity.vo2_max_precise > 0)
            .scalar()
            or 0
        )
        gpm_precise = (
            db.query(func.count(GarminPerformanceMetric.date))
            .filter(GarminPerformanceMetric.vo2_max_precise.isnot(None))
            .scalar()
            or 0
        )
        fractional = (
            db.query(func.count(Activity.activity_id))
            .filter(
                Activity.vo2_max_precise.isnot(None),
                Activity.vo2_max_precise != func.round(Activity.vo2_max_precise),
            )
            .scalar()
            or 0
        )

        print("=== VO2 max diagnose ===")
        print(f"Aktiviteter totalt:              {total}")
        print(f"Med vo2_max:                     {with_vo2}")
        print(f"Med vo2_max_precise:             {with_precise}")
        print(f"Med desimal (ikke heltall):      {fractional}")
        print(f"Daglige performance med presis:  {gpm_precise}")

        samples = (
            db.query(
                Activity.activity_id,
                Activity.start_time,
                Activity.vo2_max,
                Activity.vo2_max_precise,
            )
            .filter(Activity.vo2_max.isnot(None), Activity.vo2_max > 0)
            .order_by(Activity.start_time.desc())
            .limit(5)
            .all()
        )
        if samples:
            print("\nSiste 5 aktiviteter med VO2 max:")
            for row in samples:
                day = row.start_time.date().isoformat() if row.start_time else "?"
                print(
                    f"  {day}  id={row.activity_id}  "
                    f"vo2_max={row.vo2_max}  vo2_max_precise={row.vo2_max_precise}"
                )
        else:
            print("\nIngen aktiviteter med VO2 max funnet.")

        if with_precise == 0 and gpm_precise == 0:
            print(
                "\nAnbefaling: Kjør først Garmin performance-synk, deretter backfill:\n"
                "  npm run sync:garmin-performance\n"
                "  npm run backfill:vo2-precise"
            )
        elif with_precise == 0 and gpm_precise > 0:
            print("\nAnbefaling: Performance-data finnes, men er ikke kopiert til aktiviteter:")
            print("  npm run backfill:vo2-precise")
    finally:
        db.close()


if __name__ == "__main__":
    main()
