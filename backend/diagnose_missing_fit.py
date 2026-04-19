import pandas as pd
from app.config import data_path

def main():
    # Last FIT-data og sjekk hvilke aktiviteter som faktisk finnes
    df = pd.read_parquet(data_path("activity_details.parquet"))
    print(f'Total FIT-data: {len(df)} rader for {df["activity_id"].nunique()} aktiviteter')

    # Sjekk noen av aktivitetene som returnerte 404 i loggene
    failing_activities = [19002662455, 17870768346, 17839782792, 17854338525, 17826040971]
    
    print('\nSjekker aktiviteter som returnerte 404:')
    for activity_id in failing_activities:
        if activity_id in df['activity_id'].values:
            count = len(df[df['activity_id'] == activity_id])
            speed_count = df[df['activity_id'] == activity_id]['speed'].notna().sum()
            print(f'✓ {activity_id}: {count} datapunkter, {speed_count} med hastighet')
        else:
            print(f'✗ {activity_id}: Ikke funnet i FIT-data')

    # Vis de nyeste aktivitetene som har FIT-data
    print('\nNyeste aktiviteter MED FIT-data:')
    newest_with_fit = df['activity_id'].drop_duplicates().nlargest(15)
    for activity_id in newest_with_fit:
        print(f'  {int(activity_id)}')
    
    # Sjekk datofilteret - kun aktiviteter fra 2022-2024 ble lastet ned  
    print('\nSjekker datoer på FIT-data:')
    # Vi bruker index som er timestamp
    if not df.empty and df.index.name == 'timestamp':
        dates = pd.to_datetime(df.index)
        min_date = dates.min()
        max_date = dates.max()
        print(f'Eldste FIT-data: {min_date.date()}')
        print(f'Nyeste FIT-data: {max_date.date()}')
        
        # Tell aktiviteter per år
        years = dates.year.value_counts().sort_index()
        print('\nFIT-data fordeling per år:')
        for year, count in years.items():
            print(f'  {year}: {count} datapunkter')

if __name__ == "__main__":
    main() 