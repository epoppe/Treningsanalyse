import pandas as pd
from datetime import datetime

def main():
    # Last aktiviteter
    df = pd.read_parquet('data/activities.parquet')
    print(f'Totalt antall aktiviteter: {len(df)}')

    # Konverter start_time til datetime hvis det er string
    if df['start_time'].dtype == 'object':
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True)

    # Definer perioden
    start_date = pd.to_datetime('2022-01-01', utc=True)
    end_date = pd.to_datetime('2024-07-25 23:59:59', utc=True)

    # Filtrer aktiviteter i perioden
    filtered_df = df[(df['start_time'] >= start_date) & (df['start_time'] <= end_date)]
    print(f'Aktiviteter mellom {start_date.date()} og {end_date.date()}: {len(filtered_df)}')

    # Vis datofordeling
    print('\nAntall aktiviteter per år:')
    filtered_df['year'] = filtered_df['start_time'].dt.year
    year_counts = filtered_df['year'].value_counts().sort_index()
    print(year_counts)

    # Sjekk hvilke aktiviteter som allerede har FIT-data
    try:
        details_df = pd.read_parquet('data/activity_details.parquet')
        existing_fit_ids = set(details_df['activity_id'].unique())
        print(f'\nAktiviteter som allerede har FIT-data: {len(existing_fit_ids)}')
        
        # Finn aktiviteter som mangler FIT-data
        missing_fit_ids = filtered_df[~filtered_df['id'].isin(existing_fit_ids)]
        print(f'Aktiviteter i perioden som mangler FIT-data: {len(missing_fit_ids)}')
        
        # Vis de første 10 manglende
        print('\nFørste 10 aktiviteter som mangler FIT-data:')
        for _, row in missing_fit_ids.head(10).iterrows():
            print(f'ID: {row["id"]}, Dato: {row["start_time"].strftime("%Y-%m-%d")}, Navn: {row["name"]}')
            
        # Lagre liste over manglende aktiviteter
        missing_ids_list = missing_fit_ids['id'].tolist()
        print(f'\nTotalt {len(missing_ids_list)} aktiviteter mangler FIT-data')
        
        return missing_ids_list
            
    except Exception as e:
        print(f'Feil ved lesing av activity_details.parquet: {e}')
        return []

if __name__ == "__main__":
    main() 