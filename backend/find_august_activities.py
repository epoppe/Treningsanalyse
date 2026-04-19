import pandas as pd
from app.config import data_path

def main():
    # Last aktiviteter og finn de fra august 2024
    activities_df = pd.read_parquet(data_path("activities.parquet"))

    if activities_df['start_time'].dtype == 'object':
        activities_df['start_time'] = pd.to_datetime(activities_df['start_time'], utc=True)

    # Finn aktiviteter fra august 2024
    august_activities = activities_df[
        (activities_df['start_time'].dt.year == 2024) & 
        (activities_df['start_time'].dt.month == 8) &
        (activities_df['name'].str.contains('løp', case=False, na=False) | 
         activities_df['name'].str.contains('run', case=False, na=False) |
         activities_df['name'].str.contains('Running', case=False, na=False))
    ].head(5)
    
    print(f'Løpsaktiviteter fra august 2024:')
    for _, activity in august_activities.iterrows():
        print(f'ID: {activity["id"]} - {activity["start_time"].date()} - {activity["name"]}')
    
    # Test den første
    if len(august_activities) > 0:
        test_id = august_activities.iloc[0]['id']
        print(f'\nTester aktivitet {test_id} for negative split...')
        
        # Sjekk om den finnes i FIT-data
        fit_df = pd.read_parquet(data_path("activity_details.parquet"))
        if test_id in fit_df['activity_id'].values:
            count = len(fit_df[fit_df['activity_id'] == test_id])
            print(f'✓ Har FIT-data: {count} datapunkter')
        else:
            print('✗ Ingen FIT-data funnet')
            
        return test_id
    else:
        print('Ingen løpsaktiviteter funnet i august 2024')
        return None

if __name__ == "__main__":
    main() 