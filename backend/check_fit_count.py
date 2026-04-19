import pandas as pd
from app.config import data_path

def check_fit_count():
    try:
        df = pd.read_parquet(data_path("activity_details.parquet"))
        unique_activities = len(df['activity_id'].unique())
        total_records = len(df)
        
        print(f"🎉 Parquet har nå {unique_activities} aktiviteter med FIT-data")
        print(f"📊 Totalt {total_records} FIT-records")
        
        # Sjekk de nyeste aktivitets-ID-ene
        top_activities = sorted(df['activity_id'].unique(), reverse=True)[:10]
        print(f"🔝 De 10 nyeste aktivitetene med FIT-data: {top_activities}")
        
    except Exception as e:
        print(f"❌ Feil: {e}")

if __name__ == "__main__":
    check_fit_count() 