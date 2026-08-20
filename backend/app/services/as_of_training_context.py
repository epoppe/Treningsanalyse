"""Fold-isolated training context — no reads after train_end when building fold models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional, Set


class FutureLeakageError(ValueError):
    """Raised when a fold model attempts to read history beyond train_end."""


@dataclass(frozen=True)
class ModelTrainingContext:
    """Explicit history window for calibrating / fitting personal models."""

    history_start: date
    history_end: date
    model_key: str = "default"

    def __post_init__(self) -> None:
        if self.history_end < self.history_start:
            raise ValueError("history_end must be >= history_start")

    def contains(self, day: date) -> bool:
        return self.history_start <= day <= self.history_end

    def clamp_end(self, day: Optional[date]) -> date:
        if day is None:
            return self.history_end
        if day > self.history_end:
            raise FutureLeakageError(
                f"Requested end {day.isoformat()} exceeds train_end {self.history_end.isoformat()}"
            )
        return day


@dataclass
class AsOfTrainingContext:
    """
    Canonical fold context.

    - train_*: history used to fit/calibrate models (strict isolation)
    - prediction_date: day the recommendation is scored for
    """

    train_start: date
    train_end: date
    prediction_date: date
    enforce_isolation: bool = True
    _history_reads: Set[date] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if self.train_end < self.train_start:
            raise ValueError("train_end must be >= train_start")
        if self.prediction_date <= self.train_end:
            # Expanding window: prediction is typically day after train_end.
            pass

    def training_context(self, model_key: str = "default") -> ModelTrainingContext:
        return ModelTrainingContext(
            history_start=self.train_start,
            history_end=self.train_end,
            model_key=model_key,
        )

    def assert_history_day(self, day: date, *, purpose: str = "history") -> date:
        """Allow reads only through train_end when isolation is enforced."""
        if self.enforce_isolation and day > self.train_end:
            raise FutureLeakageError(
                f"{purpose}: day {day.isoformat()} is after train_end {self.train_end.isoformat()}"
            )
        self._history_reads.add(day)
        return day

    def history_end_for(self, requested_end: Optional[date] = None) -> date:
        end = requested_end or self.train_end
        return self.assert_history_day(end, purpose="history_end")

    def allow_prediction_features(self, day: date) -> date:
        """Prediction-day features may use as-of prediction_date, never beyond it."""
        if day > self.prediction_date:
            raise FutureLeakageError(
                f"prediction feature day {day.isoformat()} after prediction_date "
                f"{self.prediction_date.isoformat()}"
            )
        return day

    def to_dict(self) -> Dict[str, Any]:
        return {
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "prediction_date": self.prediction_date.isoformat(),
            "enforce_isolation": self.enforce_isolation,
            "history_read_count": len(self._history_reads),
        }


def resolve_history_end(
    end_date: Optional[date],
    *,
    training_context: Optional[AsOfTrainingContext | ModelTrainingContext] = None,
    default: Optional[date] = None,
) -> date:
    """Shared helper for services that accept optional fold isolation."""
    from datetime import date as date_cls

    if isinstance(training_context, AsOfTrainingContext):
        return training_context.history_end_for(end_date)
    if isinstance(training_context, ModelTrainingContext):
        return training_context.clamp_end(end_date)
    return end_date or default or date_cls.today()
