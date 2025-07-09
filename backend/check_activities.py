from app.database.session import SessionLocal
from app.database.models.activity import Activity
import pandas as pd
import os

def check_activities():
    db = SessionLocal()
    try:
        # ID-er fra frontend-loggene
        test_ids = [19646723564, 19619864122, 19541908762, 19497981315, 19467083955, 17749674264]
        
        print("Sjekker aktivitets-ID-er fra frontend-loggene:")
        for aid in test_ids:
            activity = db.query(Activity).filter_by(id=aid).first()
            if activity:
                has_details = activity.details is not None and activity.details != {}
                details_size = len(str(activity.details)) if activity.details else 0
                print(f"Aktivitet {aid}: Finnes, Details: {'Ja' if has_details else 'Nei'} ({details_size} tegn), Type: {activity.type}")
            else:
                print(f"Aktivitet {aid}: Finnes IKKE")
        
        print("\nAlle aktiviteter i databasen (totalt):")
        total_count = db.query(Activity).count()
        print(f"Totalt {total_count} aktiviteter")
        
        print("\nAktiviteter med details:")
        activities_with_details = db.query(Activity).filter(Activity.details.isnot(None)).count()
        print(f"{activities_with_details} aktiviteter har details-felt")
        
        print("\nAktivitets-ID range:")
        min_id = db.query(Activity.id).order_by(Activity.id.asc()).first()
        max_id = db.query(Activity.id).order_by(Activity.id.desc()).first()
        if min_id and max_id:
            print(f"Minste ID: {min_id[0]}")
            print(f"Største ID: {max_id[0]}")
        
        # Sjekk parquet-fil
        print("\nParquet-fil status:")
        parquet_path = "data/activity_details.parquet"
        if os.path.exists(parquet_path):
            try:
                df = pd.read_parquet(parquet_path)
                unique_activities = df['activity_id'].unique()
                print(f"Parquet-fil inneholder {len(unique_activities)} unike aktiviteter")
                print(f"Aktiviteter i parquet: {sorted(unique_activities)}")
                
                print("\nTester ID-er mot parquet:")
                for aid in test_ids:
                    in_parquet = aid in unique_activities
                    print(f"Aktivitet {aid} i parquet: {'Ja' if in_parquet else 'Nei'}")
                    
            except Exception as e:
                print(f"Feil ved lesing av parquet: {e}")
        else:
            print("Parquet-fil finnes ikke")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_activities() 