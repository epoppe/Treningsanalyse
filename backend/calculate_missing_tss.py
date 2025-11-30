#!/usr/bin/env python3
"""Beregn TSS for aktiviteter som mangler det."""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.services.training_stress_service import TrainingStressService
from datetime import datetime, timezone

db = SessionLocal()
tss_service = TrainingStressService(db)

activities_without_tss = db.query(Activity).filter(
    Activity.training_stress_score.is_(None)
).all()

print(f'Beregner TSS for {len(activities_without_tss)} aktiviteter...')

updated = 0
for activity in activities_without_tss:
    try:
        tss = tss_service.calculate_tss_for_activity(activity)
        if tss and tss > 0:
            activity.training_stress_score = tss
            updated += 1
    except Exception as e:
        print(f'Feil for aktivitet {activity.activity_id}: {e}')

db.commit()
print(f'Oppdatert {updated} aktiviteter med TSS')

db.close()

