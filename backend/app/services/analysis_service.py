import pandas as pd
import numpy as np
import logging
from ..storage import DataStorage
from typing import Optional

logger = logging.getLogger(__name__)

class AnalysisService:
    def __init__(self, storage: DataStorage):
        self.storage = storage

    def get_running_economy(self, activity_id: int) -> dict:
        """Beregner løpsøkonomi for en gitt aktivitet."""
        details_df = self.storage.activity_details
        activity_details = details_df[details_df['activity_id'] == activity_id]

        if activity_details.empty:
            return {"error": "Aktivitetsdetaljer ikke funnet"}

        # Eksempel på beregning (forenklet)
        # Løpsøkonomi = O2-forbruk (ml/kg/min) / hastighet (m/min)
        # Her bruker vi puls/hastighet som en proxy
        
        # Filtrer for å unngå deling på null
        activity_details = activity_details[activity_details['speed'] > 0]
        if activity_details.empty:
            return {"error": "Ingen bevegelsesdata i aktiviteten"}

        activity_details['heart_rate_per_speed'] = activity_details['heart_rate'] / activity_details['speed']
        
        avg_economy = activity_details['heart_rate_per_speed'].mean()
        
        # Erstatt NaN-verdier med None for JSON-kompatibilitet
        economy_data = activity_details[['timestamp', 'heart_rate_per_speed']].replace({np.nan: None})
        
        # Konverter datetime-kolonner til strenger for JSON-serialisering
        if 'timestamp' in economy_data.columns:
            economy_data['timestamp'] = economy_data['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        return {
            "activity_id": activity_id,
            "average_economy": avg_economy if pd.notna(avg_economy) else None,
            "economy_timeseries": economy_data.to_dict(orient='records')
        }

    def get_training_load(self) -> dict:
        """Beregner ukentlig Training Stress Score (TSS)."""
        activities_df = self.storage.activities
        if activities_df.empty:
            return {"weekly_tss": [], "avg_weekly_tss": 0}

        # Sørg for at 'start_time' er datetime
        activities_df['start_time'] = pd.to_datetime(activities_df['start_time'])
        
        # Beregn en forenklet TSS (dette er ikke en nøyaktig formel)
        activities_df['tss'] = activities_df['duration'] / 60 * (activities_df['average_hr'] / 150) ** 2
        
        # Grupper etter uke
        weekly_tss = activities_df.set_index('start_time').resample('W-Mon', label='left', closed='left')['tss'].sum().reset_index()
        weekly_tss.rename(columns={'start_time': 'week', 'tss': 'total_tss'}, inplace=True)
        
        avg_weekly_tss = weekly_tss['total_tss'].mean()

        if weekly_tss.empty:
            return {"weekly_tss": [], "avg_weekly_tss": 0}

        # Konverter til liste av dictionaries for JSON-respons
        # Erstatt NaN-verdier med None for JSON-kompatibilitet
        tss_clean = weekly_tss.replace({np.nan: None})
        
        # Konverter datetime-kolonner til strenger for JSON-serialisering
        if 'week' in tss_clean.columns:
            tss_clean['week'] = tss_clean['week'].dt.strftime('%Y-%m-%d')
        
        tss_list = tss_clean.to_dict(orient='records')
        
        return {
            "weekly_tss": tss_list,
            "avg_weekly_tss": avg_weekly_tss if pd.notna(avg_weekly_tss) else None
        }
        
    def get_hrv_over_time(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> dict:
        """Beregner HRV over tid med 7-dagers rullerende gjennomsnitt, valgfritt filtrert på dato."""
        hrv_df = self.storage.get_hrv_data()
        
        if hrv_df is None or hrv_df.empty:
            return {"hrv_data": []}

        # Filtrer på dato hvis start- og sluttdato er gitt
        if start_date and end_date:
            start = pd.to_datetime(start_date, utc=True)
            end = pd.to_datetime(end_date, utc=True)
            hrv_df = hrv_df[(hrv_df.index >= start) & (hrv_df.index <= end)]

        if hrv_df.empty or 'last_night_avg' not in hrv_df.columns:
            return {"hrv_data": []}

        # Sorter etter indeksen (som er 'date')
        hrv_df = hrv_df.sort_index()
        
        # Fjern dager der 'last_night_avg' er 0 eller None
        hrv_df_filtered = hrv_df[hrv_df['last_night_avg'].notna() & (hrv_df['last_night_avg'] > 0)].copy()

        if hrv_df_filtered.empty:
            return {"hrv_data": []}

        # Beregn 7-dagers rullerende gjennomsnitt for 'last_night_avg'
        hrv_df_filtered['rolling_avg_7d'] = hrv_df_filtered['last_night_avg'].rolling(window=7, min_periods=1).mean()

        # Konverter tilbake til en liste av dictionaries for API-et
        # Erstatt NaN-verdier med None for JSON-kompatibilitet
        hrv_df_clean = hrv_df_filtered.reset_index().replace({np.nan: None})
        
        # Konverter datetime-kolonner til strenger for JSON-serialisering
        if 'date' in hrv_df_clean.columns:
            hrv_df_clean['date'] = hrv_df_clean['date'].dt.strftime('%Y-%m-%d')
        
        hrv_data_list = hrv_df_clean.to_dict(orient='records')
        
        return {"hrv_data": hrv_data_list}

    def get_activity_details_for_running_economy(self, activity_id: int) -> Optional[pd.DataFrame]:
        """Henter detaljerte data for en spesifikk aktivitet for å beregne løpsøkonomi."""
        details_df = self.storage.activity_details
        activity_details = details_df[details_df['activity_id'] == activity_id]

        if activity_details.empty:
            return None

        # Eksempel på beregning (forenklet)
        # Løpsøkonomi = O2-forbruk (ml/kg/min) / hastighet (m/min)
        # Her bruker vi puls/hastighet som en proxy
        
        # Filtrer for å unngå deling på null
        activity_details = activity_details[activity_details['speed'] > 0]
        if activity_details.empty:
            return None

        activity_details['heart_rate_per_speed'] = activity_details['heart_rate'] / activity_details['speed']
        
        avg_economy = activity_details['heart_rate_per_speed'].mean()
        
        return activity_details[['timestamp', 'heart_rate_per_speed']]
