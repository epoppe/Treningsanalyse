"""Canonical coaching enums — application layer validation; DB may store VARCHAR."""

from __future__ import annotations

from enum import Enum


class DecisionStatus(str, Enum):
    RECOMMEND = "recommend"
    WEAK_PREFERENCE = "weak_preference"
    ABSTAIN = "abstain"


class ExecutionStatus(str, Enum):
    FOLLOWED = "followed"
    MODIFIED = "modified"
    SKIPPED = "skipped"
    REPLACED = "replaced"
    UNPLANNED = "unplanned"


class ModelHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    INSUFFICIENT_DATA = "insufficient_data"


class PlanStatus(str, Enum):
    KEEP = "keep"
    MODIFY = "modify"
    RECOVERY_OVERRIDE = "recovery_override"


class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    STOPPED = "stopped"
    COMPLETED = "completed"


class EvidenceStrengthBand(str, Enum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class ModelRegistryStatus(str, Enum):
    EXPERIMENTAL = "experimental"
    SHADOW = "shadow"
    ELIGIBLE = "eligible"
    ACTIVE = "active"
    RETIRED = "retired"


class DeloadNeed(str, Enum):
    NOT_NEEDED = "not_needed"
    CONSIDER = "consider"
    RECOMMENDED = "recommended"


class DetailLevel(str, Enum):
    CONCISE = "concise"
    STANDARD = "standard"
    DIAGNOSTIC = "diagnostic"


def coerce_enum(enum_cls: type[Enum], value: object, default: Enum | None = None) -> Enum | None:
    if value is None:
        return default
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(str(value))
    except ValueError:
        return default
