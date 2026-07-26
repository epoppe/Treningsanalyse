"""Upsert-hjelpere: insert / update / unchanged for aktiviteter.

Oppdaterer eksisterende rader når Garmin leverer rikere data
(f.eks. VO2Max, HR, Training Effect, vær) i stedet for å hoppe over.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple

# Felter som typisk kommer rikere fra Garmin over tid / ved re-synk
RICH_GARMIN_FIELDS = (
    "vo2_max",
    "vo2_max_precise",
    "average_heart_rate",
    "max_heart_rate",
    "min_heart_rate",
    "total_training_effect",
    "total_anaerobic_training_effect",
    "training_effect_label",
    "aerobic_training_effect_message",
    "anaerobic_training_effect_message",
    "epoc",
    "temperature",
    "weather_condition",
    "humidity",
    "wind_speed",
    "wind_direction",
    "lactate_threshold_heart_rate",
    "lactate_threshold_speed",
    "total_ascent",
    "total_descent",
    "moving_duration",
    "elapsed_duration",
    "total_steps",
    "min_elevation",
    "max_elevation",
    "calories",
    "average_speed",
    "average_moving_speed",
    "avg_grade_adjusted_speed",
    "average_pace",
    "average_running_cadence",
    "max_running_cadence",
    "activity_name",
    "distance",
    "duration",
    "activity_type_id",
)

# Ved overwrite (force refresh) — ikke nullstill beregnede metrikker
OVERWRITE_SAFE_FIELDS = RICH_GARMIN_FIELDS + (
    "start_time",
    "detailed_metrics",
)


def _values_differ(old: Any, new: Any) -> bool:
    if old is None and new is None:
        return False
    if old is None or new is None:
        return True
    if isinstance(old, float) and isinstance(new, (int, float)):
        return abs(float(old) - float(new)) > 1e-9
    if isinstance(new, float) and isinstance(old, (int, float)):
        return abs(float(old) - float(new)) > 1e-9
    return old != new


def is_richer_value(old: Any, new: Any) -> bool:
    """True hvis new fyller hull eller gir en annen ikke-tom Garmin-verdi."""
    if new is None:
        return False
    if old is None:
        return True
    return _values_differ(old, new)


def apply_activity_field_updates(
    activity: Any,
    fields: Dict[str, Any],
    *,
    overwrite: bool = False,
    field_names: Optional[Iterable[str]] = None,
) -> Tuple[bool, list[str]]:
    """Oppdater Activity-objekt fra felt-dict.

    Returns:
        (changed, list of changed field names)
    """
    names = tuple(field_names) if field_names is not None else (
        OVERWRITE_SAFE_FIELDS if overwrite else RICH_GARMIN_FIELDS
    )
    changed_fields: list[str] = []

    for name in names:
        if name not in fields:
            continue
        new_val = fields[name]
        if new_val is None and not overwrite:
            continue
        if overwrite and new_val is None:
            # Behold eksisterende ved null — ikke slett rikere historikk
            continue

        old_val = getattr(activity, name, None)
        if overwrite:
            should_set = new_val is not None and _values_differ(old_val, new_val)
        else:
            should_set = is_richer_value(old_val, new_val)

        if should_set:
            setattr(activity, name, new_val)
            changed_fields.append(name)

    # detailed_metrics: fyll inn hvis mangler, eller overwrite hvis satt
    if "detailed_metrics" in fields:
        new_details = fields["detailed_metrics"]
        old_details = getattr(activity, "detailed_metrics", None)
        if new_details is not None:
            if old_details is None or (overwrite and new_details != old_details):
                activity.detailed_metrics = new_details
                if "detailed_metrics" not in changed_fields:
                    changed_fields.append("detailed_metrics")

    return bool(changed_fields), changed_fields
