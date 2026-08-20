"""Coaching schema package."""

from .enums import (
    DecisionStatus,
    DeloadNeed,
    DetailLevel,
    EvidenceStrengthBand,
    ExecutionStatus,
    ExperimentStatus,
    ModelHealthStatus,
    ModelRegistryStatus,
    PlanStatus,
    coerce_enum,
)
from .snapshots import (
    AthleteStateSnapshotV1,
    DecisionTraceV1,
    ExecutionAnalysisV1,
    ModelProvenanceV1,
    RecommendationSnapshotV1,
    WeeklyPlanSnapshotV1,
    WorkoutPrescriptionV1,
    dump_validated,
    validate_snapshot,
    wrap_schema,
)

__all__ = [
    "DecisionStatus",
    "DeloadNeed",
    "DetailLevel",
    "EvidenceStrengthBand",
    "ExecutionStatus",
    "ExperimentStatus",
    "ModelHealthStatus",
    "ModelRegistryStatus",
    "PlanStatus",
    "coerce_enum",
    "AthleteStateSnapshotV1",
    "DecisionTraceV1",
    "ExecutionAnalysisV1",
    "ModelProvenanceV1",
    "RecommendationSnapshotV1",
    "WeeklyPlanSnapshotV1",
    "WorkoutPrescriptionV1",
    "dump_validated",
    "validate_snapshot",
    "wrap_schema",
]
