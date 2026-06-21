#!/usr/bin/env python3
"""
Kontrollert backfill av lokale avledede aktivitetsmetrikker fra eksisterende FIT-data.

Beregner negative split, decoupling/EF og løpsøkonomi via SyncMetricsService — uten
Garmin-nedlasting eller FIT-sync.

Eksempler:
  python scripts/backfill_derived_metrics.py --dry-run
  python scripts/backfill_derived_metrics.py --limit 200
  python scripts/backfill_derived_metrics.py --activity-id 12345678
  python scripts/backfill_derived_metrics.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.database.models.activity import Activity  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.services.data_coverage_service import DataCoverageService  # noqa: E402
from app.services.sync_service import SyncService  # noqa: E402
from app.storage import DataStorage  # noqa: E402


class _OfflineGarminClient:
    """Minimal stub — ingen API-kall under lokal FIT-backfill."""

    async def initialize(self) -> bool:
        return True


def _count_derived_fields(db, activity_ids: List[str]) -> Dict[str, int]:
    if not activity_ids:
        return {
            "negative_split_percent": 0,
            "decoupling_percent": 0,
            "running_economy": 0,
            "all_three": 0,
        }
    rows = db.query(Activity).filter(Activity.activity_id.in_(activity_ids)).all()
    counts = {
        "negative_split_percent": 0,
        "decoupling_percent": 0,
        "running_economy": 0,
        "all_three": 0,
    }
    for activity in rows:
        if activity.negative_split_percent is not None:
            counts["negative_split_percent"] += 1
        if activity.decoupling_percent is not None:
            counts["decoupling_percent"] += 1
        if activity.running_economy is not None:
            counts["running_economy"] += 1
        if (
            activity.negative_split_percent is not None
            and activity.decoupling_percent is not None
            and activity.running_economy is not None
        ):
            counts["all_three"] += 1
    return counts


def _empty_summary() -> Dict[str, Any]:
    return {
        "candidates": 0,
        "processed": 0,
        "negative_split_calculated": 0,
        "decoupling_calculated": 0,
        "running_economy_calculated": 0,
        "data_validated": 0,
        "errors": 0,
        "still_missing_all_derived": 0,
        "skip_reasons": {},
    }


def run_diagnose(
    *,
    limit: int | None,
    activity_id: str | None,
    include_non_running: bool,
) -> Dict[str, Any]:
    storage = DataStorage(settings.DATA_DIR)
    db = SessionLocal()
    try:
        coverage = DataCoverageService(db, storage)
        if activity_id:
            activity = db.query(Activity).filter(Activity.activity_id == activity_id).first()
            if not activity:
                return {"total": 0, "by_reason": {}, "items": [], "error": "Aktivitet ikke funnet"}
            diagnostic = coverage.diagnose_derived_backfill_candidate(activity)
            payload = {
                "total": 1,
                "by_reason": {diagnostic.skip_reason.value: 1},
                "eligible": 1 if diagnostic.skip_reason.value == "eligible" else 0,
                "items": [
                    {
                        "activity_id": diagnostic.activity_id,
                        "type_key": diagnostic.type_key,
                        "skip_reason": diagnostic.skip_reason.value,
                        "detail": diagnostic.detail,
                        "fit_rows": diagnostic.fit_rows,
                        "speed_samples": diagnostic.speed_samples,
                        "heart_rate_coverage_pct": diagnostic.heart_rate_coverage_pct,
                    }
                ],
            }
            return payload
        return coverage.diagnose_derived_backfill_gaps(
            include_non_running=include_non_running,
            limit=limit,
        )
    finally:
        db.close()


def run_backfill(
    *,
    limit: int | None,
    activity_id: str | None,
    dry_run: bool,
    progress_every: int,
    eligible_only: bool,
    include_partial: bool,
) -> Dict[str, Any]:
    storage = DataStorage(settings.DATA_DIR)
    db = SessionLocal()
    summary = _empty_summary()

    try:
        coverage = DataCoverageService(db, storage)
        if activity_id:
            candidates = [activity_id]
        elif eligible_only:
            candidates = coverage.eligible_derived_backfill_activity_ids(
                limit=limit,
                include_non_running=False,
                include_partial=include_partial,
            )
        else:
            candidates = coverage.fit_missing_derived_activity_ids(
                limit=limit,
                include_non_running=False,
                include_partial=include_partial,
            )

        summary["candidates"] = len(candidates)
        if not candidates:
            summary["before"] = _count_derived_fields(db, [])
            summary["after"] = summary["before"]
            return summary

        summary["before"] = _count_derived_fields(db, candidates)

        if dry_run:
            summary["after"] = summary["before"]
            return summary

        sync = SyncService(_OfflineGarminClient(), storage, db)
        sync.metrics_service.begin_batch()

        for index, aid in enumerate(candidates, start=1):
            result = sync.metrics_service.calculate_metrics_for_new_activity(
                aid,
                skip_snapshot_recalc=True,
            )
            summary["processed"] += 1
            if result.get("negative_split_calculated"):
                summary["negative_split_calculated"] += 1
            if result.get("decoupling_calculated"):
                summary["decoupling_calculated"] += 1
            if result.get("running_economy_calculated"):
                summary["running_economy_calculated"] += 1
            if result.get("data_validated"):
                summary["data_validated"] += 1
            if result.get("errors"):
                summary["errors"] += 1
            for reason in result.get("skip_reasons") or []:
                summary["skip_reasons"][reason] = summary["skip_reasons"].get(reason, 0) + 1

            if progress_every > 0 and (
                index == 1 or index == len(candidates) or index % progress_every == 0
            ):
                print(
                    f"  [{index}/{len(candidates)}] {aid} "
                    f"ns={result.get('negative_split_calculated')} "
                    f"dec={result.get('decoupling_calculated')} "
                    f"eco={result.get('running_economy_calculated')}",
                    flush=True,
                )

        sync.metrics_service.end_batch()
        db.expire_all()
        summary["after"] = _count_derived_fields(db, candidates)
        summary["still_missing_all_derived"] = (
            summary["candidates"] - summary["after"]["all_three"]
        )
        return summary
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill lokale avledede metrikker fra eksisterende FIT-data"
    )
    parser.add_argument("--limit", type=int, default=None, help="Maks kandidater (default: alle eligible)")
    parser.add_argument("--activity-id", type=str, default=None, help="Kun én aktivitet")
    parser.add_argument("--dry-run", action="store_true", help="Vis kandidater uten å beregne")
    parser.add_argument(
        "--eligible-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Kun diagnose-eligible kandidater (default: på)",
    )
    parser.add_argument(
        "--include-partial",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Inkluder delvise hull, ikke bare mangler alle tre felt (default: på)",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Klassifiser kandidater uten beregning (tynn FIT vs feilsport vs eligible)",
    )
    parser.add_argument(
        "--include-non-running",
        action="store_true",
        help="Inkluder ikke-løp i kandidat/diagnose (default: kun løp/tredemølle)",
    )
    parser.add_argument("--json", action="store_true", help="Skriv JSON-sammendrag")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Logg fremdrift hvert N-te aktivitet (0=av)",
    )
    args = parser.parse_args()

    if args.diagnose:
        summary = run_diagnose(
            limit=args.limit,
            activity_id=args.activity_id,
            include_non_running=args.include_non_running,
        )
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return
        print("=== DIAGNOSE: avledede metrikker fra FIT ===")
        print(f"Kandidater analysert: {summary.get('total', 0)}")
        print(f"Eligible for backfill: {summary.get('eligible', 0)}")
        if summary.get("by_reason"):
            print("\nFordeling:")
            for reason, count in sorted(summary["by_reason"].items()):
                print(f"  {reason}: {count}")
        if summary.get("items"):
            print("\nDetaljer (maks 15):")
            for item in summary["items"][:15]:
                print(
                    f"  {item['activity_id']} [{item.get('type_key')}] "
                    f"{item['skip_reason']} rows={item.get('fit_rows')} "
                    f"speed={item.get('speed_samples')} hr%={item.get('heart_rate_coverage_pct')} "
                    f"{item.get('detail') or ''}"
                )
        return

    summary = run_backfill(
        limit=args.limit,
        activity_id=args.activity_id,
        dry_run=args.dry_run,
        progress_every=args.progress_every,
        eligible_only=args.eligible_only,
        include_partial=args.include_partial,
    )

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    mode = "DRY-RUN" if args.dry_run else "BACKFILL"
    print(f"=== {mode}: lokale avledede metrikker fra FIT ===")
    if not args.activity_id:
        scope = "eligible" if args.eligible_only else "rå"
        partial = "delvise+full" if args.include_partial else "kun alle tre mangler"
        print(f"Filter: {scope}, {partial}")
    print(f"Kandidater: {summary['candidates']}")
    if not args.dry_run:
        print(f"Prosessert: {summary['processed']}")
        print(f"  negative_split: +{summary['negative_split_calculated']}")
        print(f"  decoupling:     +{summary['decoupling_calculated']}")
        print(f"  running_economy:+{summary['running_economy_calculated']}")
        print(f"  feltvalidering: {summary['data_validated']}")
        print(f"  feil:           {summary['errors']}")
    if summary.get("before"):
        before = summary["before"]
        after = summary.get("after", before)
        print("\nFør/etter (blant kandidater):")
        print(
            f"  negative_split: {before['negative_split_percent']} -> {after['negative_split_percent']}"
        )
        print(
            f"  decoupling:     {before['decoupling_percent']} -> {after['decoupling_percent']}"
        )
        print(
            f"  running_economy:{before['running_economy']} -> {after['running_economy']}"
        )
        print(f"  alle tre felt:  {before['all_three']} → {after['all_three']}")
        if not args.dry_run:
            print(f"  fortsatt uten alle tre: {summary['still_missing_all_derived']}")
        if summary.get("skip_reasons"):
            print("\nHoppet over (årsak → antall):")
            for reason, count in sorted(summary["skip_reasons"].items()):
                print(f"  {reason}: {count}")


if __name__ == "__main__":
    main()
