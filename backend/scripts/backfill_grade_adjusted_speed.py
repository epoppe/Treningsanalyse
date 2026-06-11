#!/usr/bin/env python3
"""
Kontrollert backfill av avg_grade_adjusted_speed fra eksisterende FIT/parquet.

Beregner grade-adjusted speed (Minetti) lokalt når fart, distanse og høyde finnes.
Ingen Garmin-nedlasting.

Eksempler:
  python scripts/backfill_grade_adjusted_speed.py --dry-run
  python scripts/backfill_grade_adjusted_speed.py --limit 100
  python scripts/backfill_grade_adjusted_speed.py --activity-id 22379210303
  python scripts/backfill_grade_adjusted_speed.py --diagnose --limit 20
  python scripts/backfill_grade_adjusted_speed.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.database.models.activity import Activity  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.services.analysis_service import AnalysisService  # noqa: E402
from app.storage import DataStorage  # noqa: E402
from app.utils.activity_filters import is_running_activity  # noqa: E402
from app.utils.grade_adjusted_pace import compute_avg_grade_adjusted_speed_mps  # noqa: E402
from app.utils.speed_pace import mps_to_pace_sec_per_km, pace_sec_to_display  # noqa: E402


def _fill_stats(db) -> Dict[str, int]:
    total = db.query(Activity).count()
    filled = db.query(Activity).filter(Activity.avg_grade_adjusted_speed.isnot(None)).count()
    return {"total": total, "filled": filled}


def _fit_activity_ids(storage: DataStorage) -> set[int]:
    df = storage.activity_details_df
    if df is None or df.empty:
        return set()
    return set(int(x) for x in df["activity_id"].unique())


def _candidate_activities(
    db,
    storage: DataStorage,
    *,
    activity_id: Optional[str],
    limit: Optional[int],
) -> List[Activity]:
    if activity_id:
        activity = db.query(Activity).filter(Activity.activity_id == activity_id).first()
        return [activity] if activity else []

    fit_ids = _fit_activity_ids(storage)
    if not fit_ids:
        return []

    query = (
        db.query(Activity)
        .filter(Activity.avg_grade_adjusted_speed.is_(None))
        .order_by(Activity.start_time.desc())
    )
    candidates: List[Activity] = []
    for activity in query.yield_per(200):
        if not is_running_activity(activity, include_treadmill=True):
            continue
        try:
            aid = int(activity.activity_id)
        except (TypeError, ValueError):
            continue
        if aid not in fit_ids:
            continue
        candidates.append(activity)
        if limit is not None and len(candidates) >= limit:
            break
    return candidates


def _preview_result(
    analysis: AnalysisService,
    activity: Activity,
) -> Tuple[Optional[float], Optional[str], Optional[int]]:
    try:
        aid = int(activity.activity_id)
    except (TypeError, ValueError):
        return None, "invalid_activity_id", None

    details_df = analysis._get_fit_details_for_activity(aid, activity)
    if details_df is None or details_df.empty:
        return None, "no_fit_details", None

    ref_speed = None
    if activity.average_moving_speed and activity.average_moving_speed > 0:
        ref_speed = float(activity.average_moving_speed)
    elif activity.average_speed and activity.average_speed > 0:
        ref_speed = float(activity.average_speed)

    result = compute_avg_grade_adjusted_speed_mps(
        details_df,
        reference_speed_mps=ref_speed,
    )
    if result is None:
        return None, "insufficient_samples", None
    return result.speed_mps, None, result.sample_count


def run_diagnose(
    *,
    limit: Optional[int],
    activity_id: Optional[str],
) -> Dict[str, Any]:
    storage = DataStorage(settings.DATA_DIR)
    db = SessionLocal()
    analysis = AnalysisService(storage)
    try:
        candidates = _candidate_activities(db, storage, activity_id=activity_id, limit=limit)
        by_reason: Dict[str, int] = {}
        items: List[Dict[str, Any]] = []
        eligible = 0
        for activity in candidates:
            speed_mps, reason, samples = _preview_result(analysis, activity)
            if speed_mps is not None:
                reason_key = "eligible"
                eligible += 1
            else:
                reason_key = reason or "unknown"
            by_reason[reason_key] = by_reason.get(reason_key, 0) + 1
            if len(items) < 20:
                pace_sec = mps_to_pace_sec_per_km(speed_mps) if speed_mps else None
                items.append(
                    {
                        "activity_id": activity.activity_id,
                        "start_time": activity.start_time.isoformat() if activity.start_time else None,
                        "eligible": speed_mps is not None,
                        "skip_reason": reason_key if speed_mps is None else None,
                        "speed_mps": speed_mps,
                        "pace_display": pace_sec_to_display(pace_sec),
                        "sample_count": samples,
                    }
                )
        return {
            "candidates": len(candidates),
            "eligible": eligible,
            "by_reason": by_reason,
            "items": items,
            "before": _fill_stats(db),
        }
    finally:
        db.close()


def run_backfill(
    *,
    limit: Optional[int],
    activity_id: Optional[str],
    dry_run: bool,
    progress_every: int,
) -> Dict[str, Any]:
    storage = DataStorage(settings.DATA_DIR)
    db = SessionLocal()
    analysis = AnalysisService(storage)
    summary: Dict[str, Any] = {
        "candidates": 0,
        "processed": 0,
        "calculated": 0,
        "skipped": 0,
        "errors": 0,
        "examples": [],
    }

    try:
        summary["before"] = _fill_stats(db)
        candidates = _candidate_activities(db, storage, activity_id=activity_id, limit=limit)
        summary["candidates"] = len(candidates)

        if dry_run:
            for activity in candidates:
                speed_mps, reason, samples = _preview_result(analysis, activity)
                summary["processed"] += 1
                if speed_mps is not None:
                    summary["calculated"] += 1
                    if len(summary["examples"]) < 5:
                        pace_sec = mps_to_pace_sec_per_km(speed_mps)
                        summary["examples"].append(
                            {
                                "activity_id": activity.activity_id,
                                "speed_mps": speed_mps,
                                "pace_display": pace_sec_to_display(pace_sec),
                                "sample_count": samples,
                            }
                        )
                else:
                    summary["skipped"] += 1
                    summary.setdefault("skip_reasons", {})
                    key = reason or "unknown"
                    summary["skip_reasons"][key] = summary["skip_reasons"].get(key, 0) + 1
            summary["after"] = summary["before"]
            return summary

        for index, activity in enumerate(candidates, start=1):
            summary["processed"] += 1
            try:
                result = analysis.calculate_grade_adjusted_speed(
                    int(activity.activity_id),
                    db,
                )
            except Exception:
                summary["errors"] += 1
                continue

            if result and result.get("calculation_method") not in {None, "stored"}:
                summary["calculated"] += 1
                if len(summary["examples"]) < 5:
                    pace_sec = result.get("grade_adjusted_pace_sec_per_km")
                    summary["examples"].append(
                        {
                            "activity_id": activity.activity_id,
                            "speed_mps": result.get("avg_grade_adjusted_speed"),
                            "pace_display": pace_sec_to_display(pace_sec),
                            "sample_count": result.get("sample_count"),
                            "method": result.get("calculation_method"),
                        }
                    )
            else:
                summary["skipped"] += 1

            if progress_every > 0 and (
                index == 1 or index == len(candidates) or index % progress_every == 0
            ):
                print(
                    f"  [{index}/{len(candidates)}] calculated={summary['calculated']} "
                    f"skipped={summary['skipped']} errors={summary['errors']}",
                    flush=True,
                )

        db.expire_all()
        summary["after"] = _fill_stats(db)
        return summary
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill avg_grade_adjusted_speed fra eksisterende FIT/parquet"
    )
    parser.add_argument("--limit", type=int, default=None, help="Maks kandidater")
    parser.add_argument("--activity-id", type=str, default=None, help="Kun én aktivitet")
    parser.add_argument("--dry-run", action="store_true", help="Forhåndsvis uten DB-skriving")
    parser.add_argument("--diagnose", action="store_true", help="Klassifiser kandidater")
    parser.add_argument("--json", action="store_true", help="Skriv JSON-sammendrag")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=50,
        help="Logg fremdrift hvert N-te aktivitet (0=av)",
    )
    args = parser.parse_args()

    if args.diagnose:
        summary = run_diagnose(limit=args.limit, activity_id=args.activity_id)
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return
        print("=== DIAGNOSE: grade-adjusted speed ===")
        print(f"Kandidater: {summary['candidates']}, eligible: {summary['eligible']}")
        print(f"DB fylt: {summary['before']['filled']}/{summary['before']['total']}")
        if summary.get("by_reason"):
            print("\nFordeling:")
            for reason, count in sorted(summary["by_reason"].items()):
                print(f"  {reason}: {count}")
        if summary.get("items"):
            print("\nEksempler:")
            for item in summary["items"][:10]:
                print(
                    f"  {item['activity_id']} eligible={item['eligible']} "
                    f"speed={item.get('speed_mps')} pace={item.get('pace_display')} "
                    f"samples={item.get('sample_count')} {item.get('skip_reason') or ''}"
                )
        return

    summary = run_backfill(
        limit=args.limit,
        activity_id=args.activity_id,
        dry_run=args.dry_run,
        progress_every=args.progress_every,
    )

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    mode = "DRY-RUN" if args.dry_run else "BACKFILL"
    print(f"=== {mode}: grade-adjusted speed ===")
    before = summary["before"]
    after = summary.get("after", before)
    print(f"DB før:  {before['filled']}/{before['total']}")
    print(f"Kandidater: {summary['candidates']}")
    print(f"Prosessert: {summary['processed']}")
    print(f"Beregnet:   {summary['calculated']}")
    print(f"Hoppet over:{summary['skipped']}")
    if not args.dry_run:
        print(f"Feil:       {summary['errors']}")
        print(f"DB etter: {after['filled']}/{after['total']} (+{after['filled'] - before['filled']})")
    if summary.get("examples"):
        print("\nEksempler:")
        for item in summary["examples"]:
            print(
                f"  {item['activity_id']} {item['speed_mps']} m/s "
                f"→ {item['pace_display']} ({item.get('sample_count')} samples)"
            )
    if summary.get("skip_reasons"):
        print("\nDry-run hoppet over:")
        for reason, count in sorted(summary["skip_reasons"].items()):
            print(f"  {reason}: {count}")


if __name__ == "__main__":
    main()
