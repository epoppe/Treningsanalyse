"""Standardisert metadata for infererte coaching-verdier med evidens og usikkerhet."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union

SourceType = Literal["measured", "garmin", "derived", "estimated", "heuristic", "model"]


@dataclass
class MetricEvidence:
    """Wrapper for en coaching-verdi med provenance og konfidens."""

    value: Any
    source_type: SourceType
    confidence: float
    sample_count: int = 0
    freshness_days: Optional[int] = None
    method: str = ""
    limitations: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["confidence"] = round(self.confidence, 3)
        return payload

    @classmethod
    def wrap(
        cls,
        value: Any,
        *,
        source_type: SourceType,
        confidence: float,
        sample_count: int = 0,
        freshness_days: Optional[int] = None,
        method: str = "",
        limitations: Optional[List[str]] = None,
    ) -> "MetricEvidence":
        return cls(
            value=value,
            source_type=source_type,
            confidence=confidence,
            sample_count=sample_count,
            freshness_days=freshness_days,
            method=method,
            limitations=limitations or [],
        )


def attach_evidence(
    payload: Dict[str, Any],
    key: str,
    evidence: MetricEvidence,
    *,
    evidence_field: str = "evidence",
) -> Dict[str, Any]:
    """Legg til evidence-metadata uten å endre eksisterende value-felt."""
    if key not in payload:
        payload[key] = evidence.value
    payload[evidence_field] = evidence.to_dict()
    return payload


def merge_with_value(
    value: Any,
    evidence: MetricEvidence,
) -> Dict[str, Any]:
    """Returner dict med value + evidence for nye API-felter."""
    return {
        "value": value,
        **{k: v for k, v in evidence.to_dict().items() if k != "value"},
    }


def confidence_from_sample_count(
    sample_count: int,
    *,
    min_samples: int = 3,
    target_samples: int = 14,
) -> float:
    """Enkel konfidens basert på antall datapunkter."""
    if sample_count <= 0:
        return 0.0
    if sample_count < min_samples:
        return round(0.2 + 0.3 * (sample_count / min_samples), 2)
    if sample_count >= target_samples:
        return 1.0
    span = target_samples - min_samples
    return round(0.5 + 0.5 * ((sample_count - min_samples) / span), 2)
