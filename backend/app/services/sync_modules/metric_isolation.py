"""Isoler metrikk-beregning per aktivitet slik at en hengende Garmin-økt ikke stopper synken.

Hver aktivitet kjører i en egen prosess med tidsfrist. Ved timeout drepes prosessen
(SQLite-låsen slippes), grunnsynken som allerede er committet beholdes, og
sammendrag/råd fortsetter på grunndata med tydelig lavere confidence.
"""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

STATE_KEY = "activity_derived_metrics"
# Tydelig lavere enn vanlige freshness-straff (5–25 %). 0.55 = 45 % kutt.
DERIVED_METRICS_INCOMPLETE_FACTOR = 0.55
DEFAULT_METRIC_TIMEOUT_SECONDS = 60.0
DEFAULT_SNAPSHOT_TIMEOUT_SECONDS = 180.0

_RESULT_FLAGS = (
    "tss_calculated",
    "power_calculated",
    "running_economy_calculated",
    "negative_split_calculated",
    "decoupling_calculated",
    "grade_adjusted_speed_calculated",
    "efficiency_calculated",
    "fatigue_resistance_calculated",
    "performance_snapshots_updated",
    "hrv_calculated",
)


def metric_timeout_seconds() -> float:
    raw = os.environ.get("METRIC_CALC_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_METRIC_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_METRIC_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_METRIC_TIMEOUT_SECONDS


def default_snapshot_timeout_seconds() -> float:
    raw = os.environ.get("METRIC_SNAPSHOT_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_SNAPSHOT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_SNAPSHOT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_SNAPSHOT_TIMEOUT_SECONDS


def failure_result(
    activity_id: str,
    *,
    timed_out: bool = False,
    error: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
) -> dict:
    """Resultat når beregningen ikke ble ferdig. Alle flagg er false, så aggregering er trygg."""
    errors: list[str] = []
    if timed_out:
        seconds = timeout_seconds if timeout_seconds is not None else metric_timeout_seconds()
        errors.append(f"Metric-beregning timet ut etter {seconds:.0f}s")
    if error:
        errors.append(error)
    result: dict[str, Any] = {
        "activity_id": str(activity_id),
        "errors": errors,
        "skip_reasons": [],
        "timed_out": timed_out,
        "isolated_failure": True,
        "skipped": True,
    }
    for flag in _RESULT_FLAGS:
        result[flag] = False
    return result


def _json_safe(payload: dict) -> dict:
    return json.loads(json.dumps(payload, default=str))


def _isolation_test_worker(task: dict, conn) -> None:
    """Test-hook: aktivitet 'hang' sover, alt annet returnerer med en gang."""
    import time

    activity_id = str(task.get("activity_id"))
    if activity_id == "hang":
        time.sleep(30)
    conn.send(
        {
            "activity_id": activity_id,
            "timed_out": False,
            "isolated_failure": False,
            "skipped": False,
            "errors": [],
            "tss_calculated": True,
            "power_calculated": False,
            "running_economy_calculated": False,
            "negative_split_calculated": False,
            "decoupling_calculated": False,
            "hrv_calculated": False,
        }
    )
    conn.close()


def _activity_process_entry(task: dict, conn) -> None:
    """Barneprosess: egen DB-sesjon, uten performance-snapshot (den kjøres én gang etter batch)."""
    activity_id = str(task.get("activity_id"))
    try:
        from types import SimpleNamespace

        from ...config import settings
        from ...database.session import SessionLocal
        from ...storage import DataStorage
        from ..analysis_service import AnalysisService
        from .metrics_service import SyncMetricsService

        db = SessionLocal()
        try:
            storage = DataStorage(settings.DATA_DIR)
            sync = SimpleNamespace(
                db=db,
                storage=storage,
                analysis_service=AnalysisService(storage),
            )
            metrics = SyncMetricsService(sync)
            result = metrics.calculate_metrics_for_new_activity(
                activity_id,
                skip_snapshot_recalc=True,
            )
            result["timed_out"] = False
            result["isolated_failure"] = False
            result["skipped"] = False
            conn.send(_json_safe(result))
        finally:
            db.close()
    except Exception as exc:
        try:
            conn.send(failure_result(activity_id, error=str(exc)))
        except Exception:
            logger.debug("Kunne ikke sende metrikk-feil for %s", activity_id, exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _snapshot_process_entry(conn) -> None:
    try:
        from types import SimpleNamespace

        from ...config import settings
        from ...database.session import SessionLocal
        from ...storage import DataStorage
        from ..analysis_service import AnalysisService
        from .metrics_service import SyncMetricsService

        db = SessionLocal()
        try:
            storage = DataStorage(settings.DATA_DIR)
            sync = SimpleNamespace(
                db=db,
                storage=storage,
                analysis_service=AnalysisService(storage),
            )
            ok = bool(SyncMetricsService(sync)._recalculate_performance_snapshots_once())
            conn.send({
                "ok": ok,
                "timed_out": False,
                "isolated_failure": not ok,
                "error": None if ok else "performance snapshot ble ikke oppdatert",
            })
        finally:
            db.close()
    except Exception as exc:
        try:
            conn.send({"ok": False, "timed_out": False, "isolated_failure": True, "error": str(exc)})
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def merge_pending_metric_ids(db, activity_ids: list[str]) -> list[str]:
    """Ta med aktiviteter som timet ut tidligere, selv om metadata ikke endret seg."""
    ordered = [str(activity_id) for activity_id in activity_ids if activity_id]
    try:
        pending = [str(item) for item in (_read_meta(db).get("skipped_activity_ids") or [])]
    except Exception:
        logger.warning("Kunne ikke lese aktiviteter som venter på metrikk-retry", exc_info=True)
        return list(dict.fromkeys(ordered))
    merged = list(dict.fromkeys([*ordered, *pending]))
    extra = [activity_id for activity_id in merged if activity_id not in set(ordered)]
    if extra:
        logger.info(
            "Tar med %s tidligere hoppede aktiviteter i metrikk-kjøringen: %s",
            len(extra),
            ", ".join(extra[:12]),
        )
    return merged


def _invalidate_parent_cache(result: dict) -> None:
    """Workerens cache er et annet minne. Foreldreprosessen må invalideres også."""
    activity_id = result.get("activity_id")
    cache_types = result.get("cache_invalidated")
    if not activity_id or not cache_types:
        return
    try:
        from ...cache.cache_manager import get_cache_manager

        get_cache_manager().invalidate_activity(str(activity_id), cache_types=cache_types)
    except Exception:
        logger.debug(
            "Kunne ikke invalidere parent-cache for aktivitet %s",
            activity_id,
            exc_info=True,
        )


def _read_meta(db) -> dict:
    from ...database.models.sync_state import SyncState

    state = db.query(SyncState).filter_by(key=STATE_KEY).first()
    if state is None or not isinstance(state.meta, dict):
        return {}
    return dict(state.meta)


def update_derived_metrics_state(
    db,
    *,
    succeeded: Optional[list[str]] = None,
    skipped: Optional[list[str]] = None,
    timed_out: Optional[list[str]] = None,
    snapshot_timed_out: Optional[bool] = None,
) -> dict:
    """Hold en varig liste over aktiviteter der avledede metrikker ikke ble ferdige."""
    from ...database.models.sync_state import SyncState

    state = db.query(SyncState).filter_by(key=STATE_KEY).first()
    if state is None:
        state = SyncState(key=STATE_KEY, meta={})
        db.add(state)
        meta: dict[str, Any] = {}
    else:
        meta = dict(state.meta or {})

    skipped_set = {str(item) for item in (meta.get("skipped_activity_ids") or [])}
    timed_set = {str(item) for item in (meta.get("timed_out_activity_ids") or [])}
    for activity_id in succeeded or []:
        skipped_set.discard(str(activity_id))
        timed_set.discard(str(activity_id))
    for activity_id in skipped or []:
        skipped_set.add(str(activity_id))
    for activity_id in timed_out or []:
        timed_set.add(str(activity_id))
        skipped_set.add(str(activity_id))
    if snapshot_timed_out is not None:
        meta["snapshot_timed_out"] = bool(snapshot_timed_out)

    meta["skipped_activity_ids"] = sorted(skipped_set)
    meta["timed_out_activity_ids"] = sorted(timed_set)
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    state.meta = meta
    db.commit()
    return meta


def _mark_provenance(db, activity_id: str, quality_status: str) -> None:
    from ..metric_provenance_service import upsert_metric_provenance

    upsert_metric_provenance(
        db,
        entity_type="activity",
        entity_id=str(activity_id),
        metric_key="derived_metrics",
        algorithm_version="isolated-v1",
        quality_status=quality_status,
    )


def derived_metrics_freshness(db) -> dict:
    """Freshness-oppføring coaching bruker for å senke confidence, ikke for å tvinge hvile."""
    meta = _read_meta(db)
    skipped = [str(item) for item in (meta.get("skipped_activity_ids") or [])]
    timed_out = [str(item) for item in (meta.get("timed_out_activity_ids") or [])]
    snapshot_timed_out = bool(meta.get("snapshot_timed_out"))
    incomplete = bool(skipped or snapshot_timed_out)
    note = None
    if incomplete:
        note = (
            "Avledede metrikker ble hoppet over. Sammendrag og råd bruker "
            "ferske grunndata med lavere confidence."
        )
    return {
        "metric": "derived_activity_metrics",
        "status": "incomplete" if incomplete else "fresh",
        "freshness": "incomplete" if incomplete else "fresh",
        "skipped_activity_ids": skipped,
        "timed_out_activity_ids": timed_out,
        "snapshot_timed_out": snapshot_timed_out,
        "confidence_factor": DERIVED_METRICS_INCOMPLETE_FACTOR if incomplete else 1.0,
        "source_type": "OBSERVED",
        "high_confidence_primary": not incomplete,
        "note": note,
    }


def confidence_payload(db, *, activity_id: Optional[str] = None) -> dict:
    """Confidence for sammendrag (globalt) eller én økt (aktivitet + snapshot)."""
    fresh = derived_metrics_freshness(db)
    if activity_id is None:
        incomplete = fresh["status"] == "incomplete"
        skipped_ids = list(fresh["skipped_activity_ids"])
    else:
        skipped_ids = [str(activity_id)] if str(activity_id) in set(fresh["skipped_activity_ids"]) else []
        incomplete = bool(skipped_ids or fresh["snapshot_timed_out"])
    factor = DERIVED_METRICS_INCOMPLETE_FACTOR if incomplete else 1.0
    return {
        "metrics_confidence": "reduced" if incomplete else "normal",
        "confidence_factor": factor,
        "data_basis": "base_activity_fields",
        "metrics_note": fresh["note"] if incomplete else None,
        "skipped_activity_ids": skipped_ids if activity_id is not None else list(fresh["skipped_activity_ids"]),
    }


def summarize_metric_results(results: list[dict]) -> dict:
    def _count(flag: str) -> int:
        return sum(1 for row in results if row.get(flag))

    skipped = [
        str(row.get("activity_id"))
        for row in results
        if row.get("timed_out") or row.get("isolated_failure")
    ]
    timed_out = [str(row.get("activity_id")) for row in results if row.get("timed_out")]
    incomplete = bool(skipped)
    return {
        "tss": _count("tss_calculated"),
        "power": _count("power_calculated"),
        "running_economy": _count("running_economy_calculated"),
        "negative_split": _count("negative_split_calculated"),
        "decoupling": _count("decoupling_calculated"),
        "hrv_available": _count("hrv_calculated"),
        "total_activities": len(results),
        "skipped_activities": len(skipped),
        "skipped_activity_ids": skipped,
        "timed_out_activity_ids": timed_out,
        "metrics_confidence": "reduced" if incomplete else "normal",
        "confidence_factor": DERIVED_METRICS_INCOMPLETE_FACTOR if incomplete else 1.0,
    }


class IsolatedMetricCalculator:
    """Kjør metrikk-steg i en barneprosess. Hengende steg drepes og neste aktivitet fortsetter."""

    def __init__(
        self,
        db,
        *,
        timeout_seconds: Optional[float] = None,
        snapshot_timeout_seconds: Optional[float] = None,
        activity_target=None,
        snapshot_target=None,
    ):
        self.db = db
        self.timeout = timeout_seconds if timeout_seconds is not None else metric_timeout_seconds()
        self.snapshot_timeout = (
            snapshot_timeout_seconds
            if snapshot_timeout_seconds is not None
            else default_snapshot_timeout_seconds()
        )
        self._activity_target = activity_target or _activity_process_entry
        self._snapshot_target = snapshot_target or _snapshot_process_entry
        self._ctx = multiprocessing.get_context("spawn")
        self._proc: Optional[multiprocessing.Process] = None

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is not None and proc.is_alive():
            proc.kill()
            proc.join(5)

    def _release_parent_transaction(self) -> None:
        if self.db is None:
            return
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()

    def _run(self, target, args: tuple, timeout: float) -> Optional[dict]:
        parent_conn, child_conn = self._ctx.Pipe(duplex=False)
        proc = self._ctx.Process(target=target, args=(*args, child_conn), daemon=True)
        self._proc = proc
        proc.start()
        child_conn.close()
        proc.join(timeout)
        if proc.is_alive():
            logger.error(
                "Dreper hengende metrikk-prosess etter %.0fs (pid=%s)",
                timeout,
                proc.pid,
            )
            proc.kill()
            proc.join(5)
            parent_conn.close()
            self._proc = None
            return None
        payload = None
        try:
            if parent_conn.poll(2):
                payload = parent_conn.recv()
        except (EOFError, OSError):
            payload = None
        finally:
            parent_conn.close()
            self._proc = None
        if payload is None:
            return {
                "isolated_failure": True,
                "ok": False,
                "error": f"prosess avsluttet uten resultat (exit={proc.exitcode})",
            }
        return payload

    def _persist_activity_result(self, result: dict) -> None:
        if self.db is None:
            return
        activity_id = str(result.get("activity_id") or "")
        if not activity_id:
            return
        try:
            try:
                self.db.expire_all()
            except Exception:
                logger.debug("Kunne ikke expire parent-session etter metrikk", exc_info=True)
            incomplete = bool(result.get("timed_out") or result.get("isolated_failure"))
            if incomplete:
                quality = "timeout" if result.get("timed_out") else "isolated_error"
                _mark_provenance(self.db, activity_id, quality)
                update_derived_metrics_state(
                    self.db,
                    skipped=[activity_id],
                    timed_out=[activity_id] if result.get("timed_out") else [],
                )
            else:
                _mark_provenance(self.db, activity_id, "ok")
                update_derived_metrics_state(self.db, succeeded=[activity_id])
        except Exception:
            logger.warning(
                "Kunne ikke lagre metrikk-status for aktivitet %s",
                activity_id,
                exc_info=True,
            )
            try:
                self.db.rollback()
            except Exception:
                pass

    def calculate(self, activity_id: str) -> dict:
        activity_id = str(activity_id)
        self._release_parent_transaction()
        payload = self._run(self._activity_target, ({"activity_id": activity_id},), self.timeout)
        if payload is None:
            result = failure_result(
                activity_id,
                timed_out=True,
                timeout_seconds=self.timeout,
            )
            logger.error(
                "Metric-beregning hengte for aktivitet %s (timeout %.0fs). "
                "Hopper over aktiviteten og fortsetter synken med grunndata.",
                activity_id,
                self.timeout,
            )
        elif payload.get("isolated_failure") and not payload.get("activity_id"):
            result = failure_result(
                activity_id,
                error=str(payload.get("error") or "isolert prosessfeil"),
            )
            logger.error(
                "Metric-beregning feilet isolert for aktivitet %s: %s. Fortsetter synken.",
                activity_id,
                result["errors"],
            )
        else:
            result = dict(payload)
            result.setdefault("activity_id", activity_id)
            result.setdefault("timed_out", False)
            result.setdefault("isolated_failure", False)
            result.setdefault("skipped", bool(result.get("timed_out") or result.get("isolated_failure")))
            for flag in _RESULT_FLAGS:
                result.setdefault(flag, False)
            if result.get("isolated_failure"):
                logger.error(
                    "Metric-beregning feilet isolert for aktivitet %s: %s. Fortsetter synken.",
                    activity_id,
                    result.get("errors"),
                )
        self._persist_activity_result(result)
        _invalidate_parent_cache(result)
        return result

    def recalculate_snapshots(self) -> dict:
        self._release_parent_transaction()
        payload = self._run(self._snapshot_target, (), self.snapshot_timeout)
        if payload is None:
            result = {
                "ok": False,
                "timed_out": True,
                "error": f"snapshot timet ut etter {self.snapshot_timeout:.0f}s",
            }
            logger.error(
                "Performance-snapshot hangte etter %.0fs. "
                "Grunnsynken beholdes og råd bruker lavere confidence.",
                self.snapshot_timeout,
            )
        elif not payload.get("ok", False) or payload.get("isolated_failure"):
            result = {
                "ok": False,
                "timed_out": False,
                "isolated_failure": True,
                "error": payload.get("error"),
            }
            logger.error("Performance-snapshot feilet isolert: %s", result.get("error"))
        else:
            result = {"ok": True, "timed_out": False}
        if self.db is not None:
            try:
                update_derived_metrics_state(
                    self.db,
                    snapshot_timed_out=not result.get("ok", False),
                )
            except Exception:
                logger.warning("Kunne ikke lagre snapshot-status", exc_info=True)
                try:
                    self.db.rollback()
                except Exception:
                    pass
        return result


def run_metric_batch(db, activity_ids: list[str], *, calculator: Optional[IsolatedMetricCalculator] = None) -> dict:
    """Beregn metrikker for hver aktivitet. En hang hopper over den aktiviteten og fortsetter."""
    own = calculator is None
    calc = calculator if calculator is not None else IsolatedMetricCalculator(db)
    results: list[dict] = []
    snapshot: dict[str, Any] = {"ok": True, "skipped": True}
    try:
        if not activity_ids:
            summary = summarize_metric_results(results)
            return {"results": results, "summary": summary, "snapshot": snapshot}
        for activity_id in activity_ids:
            results.append(calc.calculate(str(activity_id)))
        snapshot = calc.recalculate_snapshots()
        summary = summarize_metric_results(results)
        if not snapshot.get("ok"):
            summary["snapshot_timed_out"] = True
            summary["metrics_confidence"] = "reduced"
            summary["confidence_factor"] = DERIVED_METRICS_INCOMPLETE_FACTOR
            logger.error(
                "Performance-snapshot ble ikke ferdig. Grunnsynken beholdes "
                "og sammendrag/råd bruker lavere confidence."
            )
        elif summary["metrics_confidence"] == "reduced":
            logger.error(
                "Hoppet over metrikk for %s aktivitet(er): %s. Synken fortsetter med grunndata.",
                len(summary["skipped_activity_ids"]),
                ", ".join(summary["skipped_activity_ids"][:12]),
            )
        return {"results": results, "summary": summary, "snapshot": snapshot}
    finally:
        if own:
            calc.close()
