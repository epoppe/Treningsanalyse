#!/usr/bin/env python3
"""
Script for å sjekke Training Effect verdier i databasen
"""

from app.database.session import SessionLocal
from app.database.models.activity import Activity
from sqlalchemy import desc

def check_training_effect_values():
    db = SessionLocal()
    try:
        print('=== TRAINING EFFECT SJEKK ===')
        
        # Hent de 20 nyeste aktivitetene basert på start_time
        print('De 20 nyeste aktivitetene (basert på start_time):')
        activities = db.query(Activity).order_by(desc(Activity.start_time)).limit(20).all()
        
        for i, activity in enumerate(activities, 1):
            print(f'{i:2d}. ID: {activity.activity_id}')
            print(f'    Navn: {activity.activity_name}')
            print(f'    Start: {activity.start_time}')
            print(f'    Aerobic TE: {activity.total_training_effect}')
            print(f'    Anaerobic TE: {activity.total_anaerobic_training_effect}')
            print()
        
        # Tell hvor mange aktiviteter som har Training Effect data
        print('=== STATISTIKK ===')
        total_activities = db.query(Activity).count()
        activities_with_aerobic_te = db.query(Activity).filter(Activity.total_training_effect.isnot(None)).count()
        activities_with_anaerobic_te = db.query(Activity).filter(Activity.total_anaerobic_training_effect.isnot(None)).count()
        
        print(f'Totalt aktiviteter: {total_activities}')
        print(f'Med Aerobic TE: {activities_with_aerobic_te} ({activities_with_aerobic_te/total_activities*100:.1f}%)')
        print(f'Med Anaerobic TE: {activities_with_anaerobic_te} ({activities_with_anaerobic_te/total_activities*100:.1f}%)')
        
        # Vis eksempler på aktiviteter med Training Effect data (hvis noen)
        if activities_with_aerobic_te > 0:
            print('\n=== AKTIVITETER MED TRAINING EFFECT DATA ===')
            activities_with_te = db.query(Activity).filter(Activity.total_training_effect.isnot(None)).limit(10).all()
            for activity in activities_with_te:
                print(f'ID: {activity.activity_id} - Aerobic: {activity.total_training_effect}, Anaerobic: {activity.total_anaerobic_training_effect}')
        
    finally:
        db.close()

if __name__ == "__main__":
    check_training_effect_values() 