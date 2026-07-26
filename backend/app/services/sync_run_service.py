"""SyncRun — opprett/oppdater statistikk for synk-kjøringer."""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..database.models.sync_run import SyncRun
from ..database.session import SessionLocal

logger = logging.getLogger(__name__)

_code_version_cache: Optional[str] = None


def resolve_code_version() -> str:
    """Hent code_version fra miljø eller git SHA (kort)."""
    global _code_version_cache
    if _code_version_cache is not None:
        return _code_version_cache

    env_version = os.getenv("CODE_VERSION") or os.getenv("GIT_SHA")
    if env_version:
        _code_version_cache = env_version[:64]
        return _code_version_cache

    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        ).strip()
        if sha:
            _code_version_cache = sha
            return sha
    except Exception:
        pass

    _code_version_cache = "unknown"
    return _code_version_cache


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_sync_run(
    db: Session,
    *,
    job_type: str,
    job_id: Optional[str] = None,
    status: str = "queued",
    code_version: Optional[str] = None,
) -> SyncRun:
    run = SyncRun(
        job_id=job_id,
        job_type=job_type,
        status=status,
        code_version=code_version or resolve_code_version(),
        inserted=0,
        updated=0,
        skipped=0,
        failed=0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def mark_sync_run_started(db: Session, run_id: int) -> Optional[SyncRun]:
    run = db.query(SyncRun).filter_by(id=run_id).first()
    if run is None:
        return None
    run.status = "processing"
    run.started_at = _utcnow()
    db.commit()
    db.refresh(run)
    return run


def update_sync_run_stats(
    db: Session,
    run_id: int,
    *,
    inserted: Optional[int] = None,
    updated: Optional[int] = None,
    skipped: Optional[int] = None,
    failed: Optional[int] = None,
    last_error: Optional[str] = None,
    status: Optional[str] = None,
) -> Optional[SyncRun]:
    run = db.query(SyncRun).filter_by(id=run_id).first()
    if run is None:
        return None
    if inserted is not None:
        run.inserted = inserted
    if updated is not None:
        run.updated = updated
    if skipped is not None:
        run.skipped = skipped
    if failed is not None:
        run.failed = failed
    if last_error is not None:
        run.last_error = last_error
    if status is not None:
        run.status = status
    db.commit()
    db.refresh(run)
    return run


def complete_sync_run(
    db: Session,
    run_id: int,
    *,
    status: str = "completed",
    inserted: Optional[int] = None,
    updated: Optional[int] = None,
    skipped: Optional[int] = None,
    failed: Optional[int] = None,
    last_error: Optional[str] = None,
) -> Optional[SyncRun]:
    run = db.query(SyncRun).filter_by(id=run_id).first()
    if run is None:
        return None
    run.status = status
    run.completed_at = _utcnow()
    if inserted is not None:
        run.inserted = inserted
    if updated is not None:
        run.updated = updated
    if skipped is not None:
        run.skipped = skipped
    if failed is not None:
        run.failed = failed
    if last_error is not None:
        run.last_error = last_error
    db.commit()
    db.refresh(run)
    return run


def extract_stats_from_result(result: Any) -> Dict[str, int]:
    """Hent inserted/updated/skipped/failed fra typiske SyncService-resultater."""
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}
    if not isinstance(result, dict):
        return stats

    # Direkte nøkler
    for src, dst in (
        ("inserted", "inserted"),
        ("added_count", "inserted"),
        ("added", "inserted"),
        ("updated", "updated"),
        ("updated_count", "updated"),
        ("skipped", "skipped"),
        ("skipped_count", "skipped"),
        ("failed", "failed"),
        ("failed_count", "failed"),
        ("errors", "failed"),
    ):
        if src in result and result[src] is not None:
            try:
                stats[dst] = int(result[src])
            except (TypeError, ValueError):
                pass

    # Nestede summaries (vanlig i full_sync-resultater)
    for key in ("activities", "health", "fit", "summary", "stats"):
        nested = result.get(key)
        if isinstance(nested, dict):
            nested_stats = extract_stats_from_result(nested)
            for field in stats:
                if nested_stats[field] and not stats[field]:
                    stats[field] = nested_stats[field]
                elif nested_stats[field]:
                    stats[field] += nested_stats[field]

    return stats


def start_run_for_job(job_id: str, job_type: str) -> Optional[int]:
    """Opprett SyncRun i queued og marker processing. Returnerer run_id."""
    db = SessionLocal()
    try:
        run = create_sync_run(db, job_type=job_type, job_id=job_id, status="queued")
        mark_sync_run_started(db, run.id)
        return run.id
    except Exception as exc:
        logger.warning("Kunne ikke opprette SyncRun for jobb %s: %s", job_id, exc)
        return None
    finally:
        db.close()


def finish_run_for_job(
    run_id: Optional[int],
    *,
    status: str,
    result: Any = None,
    error: Optional[str] = None,
) -> None:
    """Avslutt SyncRun med statistikk fra result/error."""
    if run_id is None:
        return
    db = SessionLocal()
    try:
        stats = extract_stats_from_result(result)
        complete_sync_run(
            db,
            run_id,
            status=status,
            inserted=stats["inserted"],
            updated=stats["updated"],
            skipped=stats["skipped"],
            failed=stats["failed"],
            last_error=error,
        )
    except Exception as exc:
        logger.warning("Kunne ikke avslutte SyncRun %s: %s", run_id, exc)
    finally:
        db.close()
