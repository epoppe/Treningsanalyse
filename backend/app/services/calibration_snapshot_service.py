"""Inkrementelle kalibrerings-snapshots med hysteresis — ikke full historikk-recompute som sannhet."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import CalibrationSnapshot
from .athlete_calibration_service import AthleteCalibrationService
from .coaching_tx import finalize_write

MAX_RELATIVE_STEP = 0.15
HYSTERESIS_RELATIVE = 0.08
MIN_SAMPLES = 12


class CalibrationSnapshotService:
    def __init__(self, db: Session, calibration: Optional[AthleteCalibrationService] = None):
        self.db = db
        self._calibration = calibration or AthleteCalibrationService(db)

    def update_from_calibration(
        self,
        *,
        as_of_date: Optional[date] = None,
        calibration: Optional[Dict[str, Any]] = None,
        prefer_defaults: bool = False,
        commit: bool = True,
    ) -> Dict[str, Any]:
        as_of_date = as_of_date or date.today()
        calibration = calibration or self._calibration.calibrate_all(end_date=as_of_date)
        snapshots = []
        for item in calibration.get("parameters") or []:
            snapshots.append(self._update_one(item, as_of_date, prefer_defaults=prefer_defaults))
        finalize_write(self.db, commit=commit)
        return {
            "as_of_date": as_of_date.isoformat(),
            "snapshots": snapshots,
            "note": "Snapshots damp change; one week of new data cannot swing a threshold fully.",
        }

    def latest(self, parameter: str) -> Optional[Dict[str, Any]]:
        row = (
            self.db.query(CalibrationSnapshot)
            .filter(CalibrationSnapshot.parameter == parameter)
            .order_by(CalibrationSnapshot.calculated_at.desc(), CalibrationSnapshot.id.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def effective_parameters(self, *, as_of_date: Optional[date] = None) -> Dict[str, Dict[str, Any]]:
        resolved = self._calibration.resolve_parameters(end_date=as_of_date)
        for name, item in resolved.items():
            snap = self.latest(name)
            if snap and snap.get("effective_value") is not None:
                item = dict(item)
                item["value"] = snap["effective_value"]
                item["snapshot_confidence"] = snap.get("confidence")
                item["threshold_source"] = snap.get("threshold_source") or item.get("threshold_source")
                resolved[name] = item
        return resolved

    def _update_one(self, item: Dict[str, Any], as_of_date: date, *, prefer_defaults: bool) -> Dict[str, Any]:
        name = item["parameter"]
        default = item.get("default_value")
        personalized = item.get("personalized_value")
        sample_count = int(item.get("sample_count") or 0)
        confidence = float(item.get("confidence") or 0)
        previous = self.latest(name)
        proposed = personalized if item.get("use_personalized") and personalized is not None else default
        if prefer_defaults:
            proposed = default
        if sample_count < MIN_SAMPLES or confidence < 0.55:
            proposed = default if previous is None else previous.get("effective_value", default)
        effective = self._dampen(name, proposed, default, previous)
        row = CalibrationSnapshot(
            parameter=name,
            effective_value_json=effective,
            default_value_json=default,
            personalized_value_json=personalized,
            use_personalized=bool(item.get("use_personalized")) and not prefer_defaults and proposed == personalized,
            sample_count=sample_count,
            confidence=confidence,
            calculated_at=datetime.now(timezone.utc),
            as_of_date=as_of_date,
            history_window_days=item.get("history_window_days") or 90,
            method=item.get("method"),
            threshold_source="default" if prefer_defaults or proposed == default else item.get("threshold_source"),
        )
        self.db.add(row)
        self.db.flush()
        return self._to_dict(row)

    @staticmethod
    def _dampen(name: str, proposed: Any, default: Any, previous: Optional[Dict[str, Any]]) -> Any:
        if isinstance(proposed, list) and isinstance(default, list):
            prev_val = previous.get("effective_value") if previous else default
            return [
                CalibrationSnapshotService._dampen_scalar(name, p, d, pv)
                for p, d, pv in zip(proposed, default, prev_val if isinstance(prev_val, list) else default)
            ]
        prev_scalar = previous.get("effective_value") if previous else default
        return CalibrationSnapshotService._dampen_scalar(name, proposed, default, prev_scalar)

    @staticmethod
    def _dampen_scalar(name: str, proposed: Any, default: Any, previous: Any) -> Any:
        if proposed is None:
            return previous if previous is not None else default
        try:
            proposed_f = float(proposed)
            default_f = float(default) if default is not None else proposed_f
            previous_f = float(previous) if previous is not None else default_f
        except (TypeError, ValueError):
            return proposed
        scale = max(abs(default_f), 1.0)
        max_step = scale * MAX_RELATIVE_STEP
        hysteresis = scale * HYSTERESIS_RELATIVE
        delta = proposed_f - previous_f
        if abs(delta) < hysteresis:
            return round(previous_f, 2)
        if abs(delta) > max_step:
            proposed_f = previous_f + (max_step if delta > 0 else -max_step)
        return round(proposed_f, 2)

    @staticmethod
    def _to_dict(row: CalibrationSnapshot) -> Dict[str, Any]:
        return {
            "id": row.id,
            "parameter": row.parameter,
            "effective_value": row.effective_value_json,
            "default_value": row.default_value_json,
            "personalized_value": row.personalized_value_json,
            "use_personalized": row.use_personalized,
            "sample_count": row.sample_count,
            "confidence": row.confidence,
            "calculated_at": row.calculated_at.isoformat() if row.calculated_at else None,
            "as_of_date": row.as_of_date.isoformat() if row.as_of_date else None,
            "history_window_days": row.history_window_days,
            "method": row.method,
            "threshold_source": row.threshold_source,
        }
