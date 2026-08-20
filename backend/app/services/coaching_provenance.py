"""Eksplisitt modell-/kalibreringsproveniens for v5-anbefalinger.

Git SHA er ikke eneste versjon — engine, ranker, prescription og config_hash
må kunne sammenlignes på tvers av deploy.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

ENGINE = "adaptive_coaching_v5"
APPLICATION_VERSION = "5.0.0"
DECISION_ENGINE_VERSION = "5"
CALIBRATION_VERSION = "2"
RANKER_VERSION = "2"
PRESCRIPTION_VERSION = "2"
PLAN_OPTIMIZER_VERSION = "1"


def build_provenance(
    *,
    calibration: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    thresholds = {}
    if calibration:
        for name, item in calibration.items():
            if isinstance(item, dict):
                thresholds[name] = {
                    "value": item.get("value"),
                    "threshold_source": item.get("threshold_source"),
                    "use_personalized": item.get("use_personalized"),
                    "confidence": item.get("confidence"),
                    "sample_count": item.get("sample_count"),
                }
    payload = {
        "engine": ENGINE,
        "application_version": APPLICATION_VERSION,
        "decision_engine_version": DECISION_ENGINE_VERSION,
        "calibration_version": CALIBRATION_VERSION,
        "ranker_version": RANKER_VERSION,
        "prescription_version": PRESCRIPTION_VERSION,
        "plan_optimizer_version": PLAN_OPTIMIZER_VERSION,
        "thresholds": thresholds,
    }
    if extra:
        payload.update(extra)
    payload["config_hash"] = config_hash(payload)
    return payload


def config_hash(payload: Dict[str, Any]) -> str:
    canonical = {
        "engine": payload.get("engine"),
        "decision_engine_version": payload.get("decision_engine_version"),
        "calibration_version": payload.get("calibration_version"),
        "ranker_version": payload.get("ranker_version"),
        "prescription_version": payload.get("prescription_version"),
        "plan_optimizer_version": payload.get("plan_optimizer_version"),
        "thresholds": payload.get("thresholds") or {},
    }
    encoded = json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
