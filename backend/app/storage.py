import os
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
from datetime import timezone
import json
from io import BytesIO
import fitparse
import zipfile
from sqlalchemy.orm import Session
from .database.models.activity import Activity
from .config import settings

logger = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder som håndterer datetime-objekter."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class DataStorage:
    def __init__(self, data_dir: str = "data"):
        """Initialiserer DataStorage med definerte datamodeller og filbaner."""
        self.data_dir = data_dir
        self._ensure_data_directory()
        
        # Definer filbaner
        self.activities_file = os.path.join(self.data_dir, "activities.parquet")
        self.activity_details_file = os.path.join(self.data_dir, "activity_details.parquet")

        self.heart_rate_file = os.path.join(self.data_dir, "heart_rate.parquet")
        self.resting_heart_rate_file = os.path.join(self.data_dir, "resting_heart_rate.parquet")
        self.hrv_file = os.path.join(self.data_dir, "hrv.parquet")

        # Definer kolonner og datatyper for hver DataFrame
        self.activities_columns = {
            'activity_id': 'int64', 'activity_name': 'object', 'start_time': 'datetime64[ns]', 'distance': 'float64',
            'duration': 'float64', 'elapsed_duration': 'float64', 'moving_duration': 'float64', 'elevation_gain': 'float64',
            'elevation_loss': 'float64', 'average_speed': 'float64', 'max_speed': 'float64', 'average_hr': 'float64',
            'max_hr': 'float64', 'average_running_cadence': 'float64', 'max_running_cadence': 'float64', 'steps': 'int64',
            'calories': 'float64', 'activity_type': 'object', 'lap_count': 'int64'
        }
        self.activity_details_columns = {
            'activity_id': 'int64', 'timestamp': 'datetime64[ns]', 'latitude': 'float64', 'longitude': 'float64',
            'distance': 'float64', 'speed': 'float64', 'heart_rate': 'int64', 'cadence': 'int64', 'temperature': 'int64', 'altitude': 'float64'
        }

        self.heart_rate_columns = {'timestamp': 'datetime64[ns]', 'heart_rate': 'int64'}
        self.resting_heart_rate_columns = {'date': 'datetime64[ns]', 'resting_hr': 'int64'}
        self.hrv_columns = {
            'date': 'datetime64[ns]', 'last_night_avg': 'float64', 'last_night_5_min_high': 'float64', 
            'baseline_low_upper': 'float64', 'baseline_balanced_lower': 'float64', 
            'baseline_balanced_upper': 'float64', 'status': 'object'
        }
        
        # Last inn data ved initialisering
        self.activities_df = self._load_or_initialize_dataframe(self.activities_file, self.activities_columns, 'activity_id')
        self.activity_details_df = self._load_or_initialize_dataframe(self.activity_details_file, self.activity_details_columns)

        self.heart_rate_df = self._load_or_initialize_dataframe(self.heart_rate_file, self.heart_rate_columns, 'timestamp')
        self.resting_heart_rate_df = self._load_or_initialize_dataframe(self.resting_heart_rate_file, self.resting_heart_rate_columns, 'date')
        self.hrv_df = self._load_or_initialize_dataframe(self.hrv_file, self.hrv_columns, 'date')

    def _ensure_data_directory(self):
        """Sikrer at datalagringskatalogen eksisterer."""
        os.makedirs(self.data_dir, exist_ok=True)

    def _load_or_initialize_dataframe(self, file_path: str, columns: Dict[str, str], index_col: Optional[str] = None) -> pd.DataFrame:
        """Laster en DataFrame fra en Parquet-fil eller initialiserer en ny hvis den ikke finnes."""
        if os.path.exists(file_path):
            try:
                df = pd.read_parquet(file_path)
                logger.info(f"Lastet DataFrame fra {file_path} ({len(df)} rader)")
            except Exception as e:
                logger.error(f"Kunne ikke lese Parquet-filen {file_path}: {e}. Oppretter en ny DataFrame.")
                df = pd.DataFrame({col: pd.Series(dtype=dt) for col, dt in columns.items()})
        else:
            logger.info(f"Oppretter ny DataFrame-struktur for {file_path}")
            df = pd.DataFrame({col: pd.Series(dtype=dt) for col, dt in columns.items()})

        if index_col:
            if index_col in df.columns:
                df[index_col] = pd.to_datetime(df[index_col])
                df.set_index(index_col, inplace=True)
                df.sort_index(inplace=True)
            elif df.index.name != index_col:
                 # Hvis index_col ikke er i kolonner, men vi forventer det, kan det være at df er tom
                df.index.name = index_col
        
        return df
    
    def _save_dataframe(self, df: pd.DataFrame, file_path: str, df_name: str):
        """Lagrer en DataFrame til en Parquet-fil og logger prosessen."""
        try:
            # Sanitér uønskede dtype-utvidelser (som Period) som kan krasje Parquet-serialisering
            try:
                df = df.copy()
                for col in df.columns:
                    try:
                        import pandas as pd  # local import for safety
                        from pandas.api.types import is_period_dtype
                        if is_period_dtype(df[col]):
                            df[col] = df[col].astype(str)
                    except Exception:
                        pass
                # Håndter PeriodIndex dersom brukt som index
                try:
                    if getattr(df.index, 'dtype', None) is not None:
                        if str(df.index.dtype).startswith('period'):
                            df.index = df.index.astype(str)
                except Exception:
                    pass
            except Exception:
                pass
            # Bruk fastparquet som primær motor for å unngå kjente pyarrow type extension-problemer
            try:
                df.to_parquet(file_path, engine="fastparquet")
            except Exception as e_fast:
                logger.warning(f"fastparquet feilet for {df_name} ({e_fast}), prøver pyarrow...")
                import pyarrow  # sikre import
                df.to_parquet(file_path, engine="pyarrow")
            logger.info(f"Lagret {df_name}-data til {file_path} ({len(df)} rader).")
        except Exception as e:
            logger.error(f"Kunne ikke lagre DataFrame til {file_path}: {e}")
            
    def _convert_to_type(self, series: pd.Series, dtype_str: str, col_name: str) -> pd.Series:
        """Konverterer en pandas Series til spesifisert type, med feilhåndtering."""
        if 'datetime' in dtype_str:
            return pd.to_datetime(series, errors='coerce')
        try:
            return series.astype(dtype_str)
        except (ValueError, TypeError) as e:
            logger.warning(f"Kunne ikke konvertere kolonne '{col_name}' til {dtype_str}. "
                           f"Satt verdier som ikke kunne konverteres til NaN/NaT. Feil: {e}")
            return pd.to_numeric(series, errors='coerce') if 'int' in dtype_str or 'float' in dtype_str else series

    def _save_data_internal(self, new_data: List[Dict[str, Any]], df_attr: str, file_path: str, columns: Dict[str, str], merge_on: str, df_name: str):
        """Intern metode for å lagre data, sjekke for endringer og håndtere sammenslåing."""
        if not new_data:
            return
        
        new_df = pd.DataFrame(new_data)
        for col, dtype in columns.items():
            if col in new_df.columns:
                new_df[col] = self._convert_to_type(new_df[col], dtype, col)

        current_df = getattr(self, df_attr)
        
        if not current_df.empty:
            # For å unngå duplikater ved concat, må vi sørge for at indeksen er unik
            if current_df.index.name == merge_on:
                 current_df.reset_index(inplace=True)

            # Fjern duplikater fra new_df som allerede eksisterer i current_df
            new_df = new_df[~new_df[merge_on].isin(current_df[merge_on])]

        if new_df.empty:
            logger.info(f"Ingen nye data å legge til for {df_name}.")
            return

        combined_df = pd.concat([current_df, new_df], ignore_index=True)
        if merge_on in combined_df.columns:
            combined_df.set_index(merge_on, inplace=True)
            combined_df.sort_index(inplace=True)

        setattr(self, df_attr, combined_df)
        self._save_dataframe(combined_df, file_path, df_name)

    def get_all_activities(self) -> pd.DataFrame:
        return self.activities_df
    
    def reload_activity_details(self):
        """Laster aktivitetsdetaljene på nytt fra parquet-filen."""
        self.activity_details_df = self._load_or_initialize_dataframe(
            self.activity_details_file, 
            self.activity_details_columns
        )
        logger.info(f"Lastet aktivitetsdetaljer på nytt: {len(self.activity_details_df)} rader")

    def get_activity_details(self, activity_id: int) -> Optional[pd.DataFrame]:
        # Last data på nytt for å sikre at vi har de nyeste dataene
        self.reload_activity_details()
        
        activity_data = self.activity_details_df[self.activity_details_df['activity_id'] == activity_id]
        if activity_data.empty:
            return None
        
        # Reset index for å få timestamp som kolonne
        activity_data = activity_data.reset_index()
        return activity_data



    def get_hrv_data(self) -> Optional[pd.DataFrame]:
        """Henter HRV-data som en DataFrame."""
        if self.hrv_df.empty:
            return None
        return self.hrv_df.copy()

    def get_resting_heart_rate_data(self) -> pd.DataFrame:
        return self.resting_heart_rate_df

    def get_existing_activity_ids(self, db: Session) -> set:
        """Henter alle eksisterende aktivitets-ID-er fra databasen."""
        try:
            existing_activities = db.query(Activity.activity_id).all()
            existing_ids = {str(activity.activity_id) for activity in existing_activities}
            logger.info(f"Hentet {len(existing_ids)} eksisterende aktivitets-ID-er fra databasen")
            return existing_ids
        except Exception as e:
            logger.error(f"Feil ved henting av eksisterende aktivitets-ID-er: {e}")
            return set()

    def save_activities(self, activities_data: List[Dict[str, Any]]):
        self._save_data_internal(activities_data, 'activities_df', self.activities_file, self.activities_columns, 'activity_id', 'Aktiviteter')

    def save_activity_details(self, details_data: List[Dict[str, Any]]):
        """Lagrer aktivitetsdetaljer med spesiell duplikatsjekk basert på activity_id og timestamp."""
        if not details_data:
            return
        
        new_df = pd.DataFrame(details_data)
        for col, dtype in self.activity_details_columns.items():
            if col in new_df.columns:
                new_df[col] = self._convert_to_type(new_df[col], dtype, col)

        current_df = self.activity_details_df
        
        if not current_df.empty:
            # For activity_details bruker vi kombinasjon av activity_id og timestamp for duplikatsjekk
            if current_df.index.name == 'timestamp':
                current_df_reset = current_df.reset_index()
            else:
                current_df_reset = current_df.copy()
            
            # Opprett kombinert nøkkel for duplikatsjekk
            if 'activity_id' in current_df_reset.columns and 'timestamp' in current_df_reset.columns and 'activity_id' in new_df.columns and 'timestamp' in new_df.columns:
                existing_keys = set(zip(current_df_reset['activity_id'], current_df_reset['timestamp']))
                new_keys = list(zip(new_df['activity_id'], new_df['timestamp']))
                
                # Behold kun nye kombinasjoner av (activity_id, timestamp)
                mask = [key not in existing_keys for key in new_keys]
                new_df = new_df[mask]
            else:
                # Fallback til timestamp-only hvis kolonner mangler
                new_df = new_df[~new_df['timestamp'].isin(current_df_reset['timestamp'])]

        if new_df.empty:
            logger.info("Ingen nye data å legge til for Aktivitetsdetaljer.")
            return

        # Kombiner data
        if not current_df.empty and current_df.index.name == 'timestamp':
            current_df = current_df.reset_index()
        
        combined_df = pd.concat([current_df, new_df], ignore_index=True)
        combined_df.set_index('timestamp', inplace=True)
        combined_df.sort_index(inplace=True)

        self.activity_details_df = combined_df
        self._save_dataframe(combined_df, self.activity_details_file, 'Aktivitetsdetaljer')


    
    def save_heart_rate_data(self, heart_rate_data: List[Dict[str, Any]]):
        self._save_data_internal(heart_rate_data, 'heart_rate_df', self.heart_rate_file, self.heart_rate_columns, 'timestamp', 'Puls')

    def save_resting_heart_rate_data(self, resting_hr_data: List[Dict[str, Any]]):
        self._save_data_internal(resting_hr_data, 'resting_heart_rate_df', self.resting_heart_rate_file, self.resting_heart_rate_columns, 'date', 'Resting Heart Rate')

    def save_hrv_data(self, hrv_data: List[Dict[str, Any]]):
        """Lagrer HRV-data, overskriver duplikater basert på dato."""
        if not hrv_data:
            logger.info("Ingen HRV-data å lagre.")
            return

        # 1. Konverter innkommende data til en DataFrame og sett 'date' som en UTC-tidsstemplet indeks
        new_data_df = pd.DataFrame(hrv_data)
        for col, dtype_str in self.hrv_columns.items():
            if col in new_data_df.columns:
                new_data_df[col] = self._convert_to_type(new_data_df[col], dtype_str, col)
        
        if 'date' not in new_data_df.columns:
            logger.warning("Innkommende HRV-data mangler 'date'-kolonne. Kan ikke lagre.")
            return
            
        new_data_df['date'] = pd.to_datetime(new_data_df['date'], utc=True)
        new_data_df.set_index('date', inplace=True)

        # 2. Hent eksisterende data og sikre at indeksen er UTC
        existing_df = self.hrv_df.copy()
        if not existing_df.empty:
            if existing_df.index.tz is None:
                existing_df.index = existing_df.index.tz_localize('UTC')
            else:
                existing_df.index = existing_df.index.tz_convert('UTC')

        # 3. Fjern rader fra eksisterende data som finnes i nye data for å unngå duplikater
        common_dates = existing_df.index.intersection(new_data_df.index)
        if not common_dates.empty:
            existing_df.drop(common_dates, inplace=True)
        
        # 4. Kombiner de gamle (filtrerte) dataene med de helt nye dataene
        combined_df = pd.concat([existing_df, new_data_df])
        combined_df.sort_index(inplace=True)

        # 5. Lagre den oppdaterte DataFrame-en
        self.hrv_df = combined_df
        self._save_dataframe(self.hrv_df, self.hrv_file, 'HRV')

    def save_activity_from_fit(self, db: Session, fit_file_content: bytes, activity_id: int):
        # ... (eksisterende funksjon, ingen endringer)
        pass

# Global storage instance
_storage_instance = None

def get_storage() -> DataStorage:
    """Returnerer en global DataStorage instans."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = DataStorage(settings.DATA_DIR)
    return _storage_instance
