import pandas as pd
from datetime import datetime
from app.config import data_path

def main():
    # Last activities og sjekk hvilke som finnes i perioden men ikke har FIT-data
    activities_df = pd.read_parquet(data_path("activities.parquet"))
    fit_df = pd.read_parquet(data_path("activity_details.parquet"))

    # Konverter start_time til datetime hvis det er string
    if activities_df['start_time'].dtype == 'object':
        activities_df['start_time'] = pd.to_datetime(activities_df['start_time'], utc=True)

    # Definer perioden som ble lastet ned
    start_date = pd.to_datetime('2022-01-01', utc=True)  
    end_date = pd.to_datetime('2024-07-25 23:59:59', utc=True)

    # Filtrer aktiviteter i perioden
    period_activities = activities_df[(activities_df['start_time'] >= start_date) & (activities_df['start_time'] <= end_date)]
    print(f'Aktiviteter i perioden (2022-2024): {len(period_activities)}')

    # Sjekk hvilke av disse som har FIT-data
    fit_activity_ids = set(fit_df['activity_id'].unique())
    period_activity_ids = set(period_activities['id'].values)

    has_fit = period_activity_ids.intersection(fit_activity_ids)
    missing_fit = period_activity_ids - fit_activity_ids

    print(f'Har FIT-data: {len(has_fit)}')
    print(f'Mangler FIT-data: {len(missing_fit)}')

    # Vis noen eksempler på aktiviteter som mangler FIT-data
    print('\nEksempler på aktiviteter som mangler FIT-data:')
    missing_sample = list(missing_fit)[:10]
    for activity_id in missing_sample:
        activity = period_activities[period_activities['id'] == activity_id].iloc[0]
        print(f'{activity_id}: {activity["start_time"].date()} - {activity["name"]}')
    
    # Sjekk hvilke av aktivitetene som returnerte 404 som faktisk finnes i perioden
    failing_activities = [19002662455, 17870768346, 17839782792, 17854338525, 17826040971]
    print('\nSjekker 404-aktiviteter:')
    for activity_id in failing_activities:
        if activity_id in period_activity_ids:
            activity = activities_df[activities_df['id'] == activity_id].iloc[0]
            print(f'{activity_id}: {activity["start_time"].date()} - I PERIODEN - Mangler FIT')
        else:
            # Sjekk om aktiviteten finnes i hele datasettet
            if activity_id in activities_df['id'].values:
                activity = activities_df[activities_df['id'] == activity_id].iloc[0]
                print(f'{activity_id}: {activity["start_time"].date()} - UTENFOR PERIODEN')
            else:
                print(f'{activity_id}: Ikke funnet i hele datasettet')

if __name__ == "__main__":
    main() 