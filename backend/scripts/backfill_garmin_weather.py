"""
Fyll inn temperatur fra lagret Garmin activitylist-data (detailed_metrics).

Kjør fra backend-mappen:
  python scripts/backfill_garmin_weather.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.services.activity_field_extraction import extract_garmin_weather_fields


def main() -> None:
    db = SessionLocal()
    updated = 0
    try:
        rows = db.query(Activity).filter(Activity.temperature.is_(None)).all()
        for activity in rows:
            metrics = activity.detailed_metrics
            if not isinstance(metrics, dict):
                continue
            fields = extract_garmin_weather_fields(metrics)
            if fields.get("temperature") is None:
                continue
            activity.temperature = fields["temperature"]
            if not activity.weather_condition:
                activity.weather_condition = fields.get("weather_condition")
            updated += 1
        db.commit()
        print(f"Oppdatert temperatur på {updated} aktiviteter fra lagret Garmin-data.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
