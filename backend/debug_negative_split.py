import pandas as pd
from app.storage import DataStorage
from app.config import data_path, settings

def debug_negative_split():
    storage = DataStorage(settings.DATA_DIR)
    activity_id = 9990507603  # Aktivitet som vi nettopp lastet ned med ny parquet-fil
    
    print(f"=== DEBUG NEGATIV SPLIT FOR AKTIVITET {activity_id} ===")
    
    # Test storage.get_activity_details
    try:
        details_df = storage.get_activity_details(activity_id)
        print(f"Storage returnerte: {type(details_df)}")
        
        if details_df is None:
            print("❌ details_df er None")
            return
        elif details_df.empty:
            print("❌ details_df er tom")
            return
        else:
            print(f"✓ details_df har {len(details_df)} rader")
            print(f"Kolonner: {list(details_df.columns)}")
            
            # Sjekk speed-kolonnen
            if 'speed' in details_df.columns:
                speed_data = details_df['speed'].dropna()
                print(f"Speed-data: {len(speed_data)} ikke-null verdier")
                print(f"Speed range: {speed_data.min():.3f} - {speed_data.max():.3f}")
                print(f"Gjennomsnittlig speed: {speed_data.mean():.3f}")
                print(f"Første 5 speed-verdier: {speed_data.head().tolist()}")
                
                # Test pace-beregning
                if speed_data.mean() > 0:
                    avg_pace = 1000 / (speed_data.mean() * 60)
                    print(f"Beregnet gjennomsnittlig pace: {avg_pace:.2f} min/km")
            else:
                print("❌ Ingen 'speed' kolonne funnet")
                
            # Sjekk timestamp-kolonnen
            if 'timestamp' in details_df.columns:
                timestamp_data = details_df['timestamp'].dropna()
                print(f"Timestamp-data: {len(timestamp_data)} ikke-null verdier")
                print(f"Timestamp range: {timestamp_data.min()} - {timestamp_data.max()}")
            else:
                print("❌ Ingen 'timestamp' kolonne funnet")
    
    except Exception as e:
        print(f"❌ Feil ved henting av activity details: {e}")
        import traceback
        traceback.print_exc()
    
    # Sjekk parquet-fil direkte
    print(f"\n=== DIREKTE PARQUET-SJEKK ===")
    try:
        parquet_df = pd.read_parquet(data_path("activity_details.parquet"))
        activity_data = parquet_df[parquet_df['activity_id'] == activity_id]
        print(f"Parquet har {len(activity_data)} rader for aktivitet {activity_id}")
        
        if not activity_data.empty:
            print(f"Kolonner i parquet: {list(activity_data.columns)}")
            if 'speed' in activity_data.columns:
                speed_vals = activity_data['speed'].dropna()
                print(f"Speed i parquet: {len(speed_vals)} verdier, range: {speed_vals.min():.3f} - {speed_vals.max():.3f}")
        
    except Exception as e:
        print(f"❌ Feil ved lesing av parquet: {e}")

if __name__ == "__main__":
    debug_negative_split() 