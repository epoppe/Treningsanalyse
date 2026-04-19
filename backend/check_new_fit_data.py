import pandas as pd
from app.config import data_path

def main():
    print('Sjekker activity_details.parquet...')
    df = pd.read_parquet(data_path("activity_details.parquet"))
    print(f'Totale rader: {len(df)}')
    print(f'Unike aktiviteter: {df["activity_id"].nunique()}')

    # Sjekk noen av aktivitetene som brukte fallback
    test_activities = [17777708999, 17749674264, 17714915929, 17616782580, 17699086959]
    print('\nSjekker aktiviteter som brukte fallback:')
    for activity_id in test_activities:
        has_data = activity_id in df['activity_id'].values
        if has_data:
            count = len(df[df['activity_id'] == activity_id])
            print(f'Aktivitet {activity_id}: {count} datapunkter')
        else:
            print(f'Aktivitet {activity_id}: Ingen data funnet')
    
    # Sjekk datofordeling av nye data
    print('\nAktiviteter per år i FIT-data:')
    df['start_date'] = pd.to_datetime(df['timestamp'], utc=True).dt.date
    activity_dates = df.groupby('activity_id')['start_date'].first()
    activity_dates = pd.to_datetime(activity_dates)
    year_counts = activity_dates.dt.year.value_counts().sort_index()
    print(year_counts)

if __name__ == "__main__":
    main() 