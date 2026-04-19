from app.database.session import SessionLocal
from app.database.models.activity import Activity
from app.config import data_path
import pandas as pd
import os

def detailed_check():
    db = SessionLocal()
    try:
        print("=== DETALJERT SJEKK AV FIT-DATA PROBLEM ===\n")
        
        # Sjekk database-størrelse og details
        total_count = db.query(Activity).count()
        activities_with_details = db.query(Activity).filter(Activity.details.isnot(None)).count()
        print(f"Database: {total_count} aktiviteter totalt")
        print(f"Database: {activities_with_details} aktiviteter med details-felt\n")
        
        # Hent de 20 nyeste aktivitetene og sjekk details
        print("=== 20 NYESTE AKTIVITETER ===")
        recent_activities = db.query(Activity.id, Activity.details, Activity.type, Activity.name).order_by(Activity.id.desc()).limit(20).all()
        
        for i, activity in enumerate(recent_activities):
            has_details = activity.details is not None and activity.details != {}
            details_size = len(str(activity.details)) if activity.details else 0
            has_records = 'records' in str(activity.details) if activity.details else False
            print(f"{i+1:2d}. ID: {activity.id}, Type: {activity.type}, Details: {details_size} tegn, Records: {'Ja' if has_records else 'Nei'}")
        
        # Sjekk parquet-fil
        print(f"\n=== PARQUET-FIL ===")
        parquet_path = str(data_path("activity_details.parquet"))
        if os.path.exists(parquet_path):
            df = pd.read_parquet(parquet_path)
            unique_activities = df['activity_id'].unique()
            print(f"Parquet: {len(unique_activities)} unike aktiviteter")
            print(f"Parquet aktiviteter: {sorted(unique_activities)}")
            
            # Test logikken fra sync_service
            print(f"\n=== SYNC_SERVICE LOGIKK TEST ===")
            existing_fit_activity_ids = set(unique_activities)
            
            # Simuler logikken fra download_fit_data_for_activities
            query = db.query(Activity.id, Activity.details).order_by(Activity.id.desc()).limit(30)
            all_activities = query.all()
            
            missing_count = 0
            found_missing = []
            
            for activity in all_activities:
                activity_id = activity.id
                has_parquet_data = activity_id in existing_fit_activity_ids
                has_db_details = activity.details is not None and activity.details != {} and 'records' in str(activity.details)
                
                if not (has_parquet_data and has_db_details):
                    missing_count += 1
                    found_missing.append(activity_id)
                    if missing_count <= 10:  # Vis bare de første 10
                        print(f"Mangler FIT-data: {activity_id} (parquet: {'Ja' if has_parquet_data else 'Nei'}, db_details: {'Ja' if has_db_details else 'Nei'})")
            
            print(f"\nTotalt {missing_count} aktiviteter mangler FIT-data")
            print(f"Første 10 som mangler: {found_missing[:10]}")
        else:
            print("Parquet-fil finnes ikke")
            
    finally:
        db.close()

if __name__ == "__main__":
    detailed_check() 