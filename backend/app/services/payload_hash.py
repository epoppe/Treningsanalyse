"""Canonical payload hashing for idempotency (not Git SHA)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def payload_hash(payload: Any, *, length: int = 16) -> str:
    encoded = canonical_json(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def decision_payload_hash(
    *,
    workout_type: str,
    decision_status: Optional[str],
    evidence_strength: Optional[float],
    decision_confidence: Optional[float],
    prescription: Optional[Dict[str, Any]],
    context_summary: Optional[Dict[str, Any]],
) -> str:
    return payload_hash(
        {
            "workout_type": workout_type,
            "decision_status": decision_status,
            "evidence_strength": evidence_strength,
            "decision_confidence": decision_confidence,
            "prescription": prescription or {},
            "context_summary": context_summary or {},
        }
    )


def plan_payload_hash(sessions: Any, week_objective: Optional[str] = None) -> str:
    compact = []
    for session in sessions or []:
        if not isinstance(session, dict):
            continue
        compact.append(
            {
                "day_offset": session.get("day_offset"),
                "type": session.get("type"),
                "duration_min": session.get("duration_min"),
            }
        )
    return payload_hash({"week_objective": week_objective, "sessions": compact})
