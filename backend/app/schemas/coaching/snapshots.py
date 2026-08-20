"""Typed persisted coaching JSON snapshots with schema_version wrappers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SnapshotBase(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: int = 1


class ModelProvenanceV1(SnapshotBase):
    engine: str
    application_version: str
    decision_engine_version: str
    calibration_version: str
    ranker_version: Optional[str] = None
    prescription_version: Optional[str] = None
    plan_optimizer_version: Optional[str] = None
    config_hash: str
    thresholds: Dict[str, Any] = Field(default_factory=dict)


class AthleteStateSnapshotV1(SnapshotBase):
    date: Optional[str] = None
    fitness: Optional[Dict[str, Any]] = None
    recovery: Optional[Dict[str, Any]] = None
    fatigue: Optional[Dict[str, Any]] = None
    aerobic_efficiency: Optional[Dict[str, Any]] = None
    durability: Optional[Dict[str, Any]] = None


class DecisionTraceItemV1(BaseModel):
    model_config = ConfigDict(extra="allow")
    factor: Optional[str] = None
    value: Any = None
    effect: Optional[str] = None
    threshold: Any = None
    threshold_source: Optional[str] = None


class DecisionTraceV1(SnapshotBase):
    items: List[DecisionTraceItemV1] = Field(default_factory=list)


class WorkoutPrescriptionV1(SnapshotBase):
    workout_type: Optional[str] = None
    total_duration_min: Optional[Union[int, float]] = None
    main_set: Optional[Dict[str, Any]] = None
    stimulus: Optional[str] = None
    structure: Optional[str] = None


class WeeklyPlanSnapshotV1(SnapshotBase):
    week_start: Optional[str] = None
    week_objective: Optional[str] = None
    sessions: List[Dict[str, Any]] = Field(default_factory=list)
    target_volume_min: Optional[List[Any]] = None
    hard_sessions: Optional[int] = None
    scores: Optional[Dict[str, Any]] = None
    simulation: Optional[Dict[str, Any]] = None


class ExecutionAnalysisV1(SnapshotBase):
    completion_pct: Optional[float] = None
    target_intensity_pct: Optional[float] = None
    interval_consistency: Optional[float] = None
    planned_vs_actual_load: Optional[Dict[str, Any]] = None
    execution_quality: Optional[float] = None
    deviations: List[str] = Field(default_factory=list)


class RecommendationSnapshotV1(SnapshotBase):
    workout_type: str
    decision_status: Optional[str] = None
    evidence_strength: Optional[float] = None
    decision_confidence: Optional[float] = None
    recommendation_confidence: Optional[float] = None  # compatibility alias
    data_quality: Optional[float] = None
    goal: Optional[Dict[str, Any]] = None
    training_phase: Optional[Dict[str, Any]] = None
    race_capability: Optional[Dict[str, Any]] = None
    context_summary: Optional[Dict[str, Any]] = None
    candidate_workouts: Optional[List[Dict[str, Any]]] = None
    workout_prescription: Optional[Dict[str, Any]] = None
    decision_trace: Optional[List[Dict[str, Any]]] = None
    safe_alternatives: Optional[List[Dict[str, Any]]] = None


def wrap_schema(payload: Optional[Dict[str, Any]], schema_version: int = 1) -> Dict[str, Any]:
    data = dict(payload or {})
    data.setdefault("schema_version", schema_version)
    return data


def validate_snapshot(model_cls: type[BaseModel], payload: Any) -> Dict[str, Any]:
    """Validate on write/read. Invalid legacy → degraded payload, never crash."""
    if payload is None:
        return {"schema_version": 1, "status": "empty", "degraded": True}
    try:
        if isinstance(payload, list) and model_cls is DecisionTraceV1:
            return DecisionTraceV1(items=payload).model_dump()
        raw = payload if isinstance(payload, dict) else {"value": payload}
        raw = wrap_schema(raw)
        return model_cls.model_validate(raw).model_dump()
    except ValidationError as exc:
        return {
            "schema_version": 1,
            "status": "degraded",
            "degraded": True,
            "validation_error": str(exc.errors()[:3]),
            "raw": payload if isinstance(payload, (dict, list)) else {"value": payload},
        }


def dump_validated(model_cls: type[BaseModel], payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    validated = validate_snapshot(model_cls, wrap_schema(payload or {}))
    if validated.get("degraded"):
        # Still persist a versioned wrapper for recoverability.
        return {"schema_version": 1, "status": "degraded", "raw": payload or {}}
    return validated
