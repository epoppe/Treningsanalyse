"""Shared status semantics — absence of evidence ≠ evidence of normality."""

from __future__ import annotations

from enum import Enum


class DriftStatus(str, Enum):
    STABLE = "stable"
    POSSIBLE_DRIFT = "possible_drift"
    CONFIRMED_DRIFT = "confirmed_drift"
    INSUFFICIENT_DATA = "insufficient_data"


class IntegritySeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    ATTENTION_REQUIRED = "attention_required"
    CRITICAL = "critical"


class IntegrityOverall(str, Enum):
    HEALTHY = "healthy"
    WARNINGS = "warnings"
    ATTENTION_REQUIRED = "attention_required"
    CRITICAL = "critical"


class SourceType(str, Enum):
    OBSERVED = "OBSERVED"
    DERIVED_FROM_OBSERVED = "DERIVED_FROM_OBSERVED"
    CONFIG = "CONFIG"
    MISSING = "MISSING"


# Guidance: never map insufficient/missing → stable/healthy/good recovery.
ABSENCE_IS_NOT_NORMALITY = (
    "Insufficient or missing evidence must be reported as insufficient_data / missing — "
    "never as stable, healthy, or physiologically good."
)
