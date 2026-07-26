"""Registrer og hent proveniens for beregnede metrikker."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from sqlalchemy.orm import Session

from ..database.models.metric_provenance import MetricProvenance

logger = logging.getLogger(__name__)

# Algoritmeversjoner — bump ved endring i beregningslogikk
ALGORITHM_VERSIONS = {
    "training_stress_score": "tss-epoc-v1",
    "average_power": "power-estimate-v1",
    "running_economy": "re-speed-hr-v1",
    "negative_split_percent": "neg-split-v1",
    "decoupling_percent": "decoupling-v1",
    "avg_efficiency_factor": "ef-v1",
    "avg_grade_adjusted_speed": "gap-v1",
    "fatigue_resistance_score": "fatigue-v1",
}

# Mapping fra SyncMetricsService result-flagg → metric_key
RESULT_FLAG_TO_METRIC = {
    "tss_calculated": "training_stress_score",
    "power_calculated": "average_power",
    "running_economy_calculated": "running_economy",
    "negative_split_calculated": "negative_split_percent",
    "decoupling_calculated": "decoupling_percent",
    "efficiency_calculated": "avg_efficiency_factor",
    "grade_adjusted_speed_calculated": "avg_grade_adjusted_speed",
    "fatigue_resistance_calculated": "fatigue_resistance_score",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_source_hash(payload: Dict[str, Any]) -> str:
    """Stabil SHA-256 over kildedata brukt i beregningen."""
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def activity_source_snapshot(activity: Any) -> Dict[str, Any]:
    """Minimal kilde-snapshot for aktivitetsmetrikker."""
    return {
        "activity_id": getattr(activity, "activity_id", None),
        "distance": getattr(activity, "distance", None),
        "duration": getattr(activity, "duration", None),
        "average_speed": getattr(activity, "average_speed", None),
        "average_heart_rate": getattr(activity, "average_heart_rate", None),
        "epoc": getattr(activity, "epoc", None),
        "vo2_max": getattr(activity, "vo2_max", None),
        "vo2_max_precise": getattr(activity, "vo2_max_precise", None),
        "start_time": getattr(activity, "start_time", None),
        "has_detailed_metrics": getattr(activity, "detailed_metrics", None) is not None,
    }


def upsert_metric_provenance(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    metric_key: str,
    algorithm_version: Optional[str] = None,
    source_hash: Optional[str] = None,
    source_updated_at: Optional[datetime] = None,
    quality_status: str = "ok",
    calculated_at: Optional[datetime] = None,
) -> MetricProvenance:
    version = algorithm_version or ALGORITHM_VERSIONS.get(metric_key, "unknown")
    calc_at = calculated_at or _utcnow()

    row = (
        db.query(MetricProvenance)
        .filter_by(entity_type=entity_type, entity_id=str(entity_id), metric_key=metric_key)
        .first()
    )
    if row is None:
        row = MetricProvenance(
            entity_type=entity_type,
            entity_id=str(entity_id),
            metric_key=metric_key,
            algorithm_version=version,
            calculated_at=calc_at,
            source_hash=source_hash,
            source_updated_at=source_updated_at,
            quality_status=quality_status,
        )
        db.add(row)
    else:
        row.algorithm_version = version
        row.calculated_at = calc_at
        row.source_hash = source_hash
        row.source_updated_at = source_updated_at
        row.quality_status = quality_status
    return row


def record_activity_metrics_from_results(
    db: Session,
    activity: Any,
    results: Dict[str, Any],
) -> list[str]:
    """Lagre proveniens for metrikker som nettopp ble beregnet (fra SyncMetricsService-resultat)."""
    recorded: list[str] = []
    snapshot = activity_source_snapshot(activity)
    source_hash = compute_source_hash(snapshot)
    source_updated_at = getattr(activity, "start_time", None)
    quality = "ok"
    if results.get("errors"):
        quality = "degraded"
    elif results.get("skip_reasons"):
        quality = "partial"

    for flag, metric_key in RESULT_FLAG_TO_METRIC.items():
        if not results.get(flag):
            continue
        try:
            upsert_metric_provenance(
                db,
                entity_type="activity",
                entity_id=str(activity.activity_id),
                metric_key=metric_key,
                source_hash=source_hash,
                source_updated_at=source_updated_at,
                quality_status=quality,
            )
            recorded.append(metric_key)
        except Exception as exc:
            logger.warning(
                "Kunne ikke lagre proveniens for %s/%s: %s",
                activity.activity_id,
                metric_key,
                exc,
            )
    return recorded


def get_activity_provenance(db: Session, activity_id: str) -> list[Dict[str, Any]]:
    rows = (
        db.query(MetricProvenance)
        .filter_by(entity_type="activity", entity_id=str(activity_id))
        .order_by(MetricProvenance.metric_key)
        .all()
    )
    return [
        {
            "metric_key": row.metric_key,
            "algorithm_version": row.algorithm_version,
            "calculated_at": row.calculated_at.isoformat() if row.calculated_at else None,
            "source_hash": row.source_hash,
            "source_updated_at": row.source_updated_at.isoformat() if row.source_updated_at else None,
            "quality_status": row.quality_status,
        }
        for row in rows
    ]
