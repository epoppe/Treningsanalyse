import pandas as pd
from app.config import data_path

def main():
    # Last FIT-data
    df = pd.read_parquet(data_path("activity_details.parquet"))
    print(f'Totalt {len(df)} rader med FIT-data for {df["activity_id"].nunique()} aktiviteter')
    
    # Sjekk aktiviteter som brukte fallback
    test_activities = [17777708999, 17749674264, 17714915929, 17616782580, 17699086959]
    
    for activity_id in test_activities:
        if activity_id in df['activity_id'].values:
            activity_data = df[df['activity_id'] == activity_id]
            speed_points = activity_data['speed'].notna().sum()
            print(f'✓ Aktivitet {activity_id}: {len(activity_data)} datapunkter, {speed_points} med hastighet')
        else:
            print(f'✗ Aktivitet {activity_id}: Ikke funnet i FIT-data')
    
    # Vis de nyeste aktivitetene i FIT-dataene
    print('\nNyeste aktiviteter i FIT-data:')
    unique_activities = df.groupby('activity_id').first().reset_index()
    newest_activities = unique_activities.nlargest(10, 'activity_id')
    for _, row in newest_activities.iterrows():
        print(f'  {row["activity_id"]}')

if __name__ == "__main__":
    main() 