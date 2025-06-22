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
        self.sleep_file = os.path.join(self.data_dir, "sleep.parquet")
        self.heart_rate_file = os.path.join(self.data_dir, "heart_rate.parquet")
        self.resting_heart_rate_file = os.path.join(self.data_dir, "resting_heart_rate.parquet")
        
        # Definer kolonnedefinisjoner for hver datamodell
        self.activity_columns = {
            'id': 'Int64',  # Garmin aktivitets-ID
            'name': 'string',  # Aktivitetsnavn
            'type': 'string',  # Aktivitetstype
            'start_time': 'datetime64[ns, UTC]',  # Starttidspunkt
            'duration': 'float64',  # Varighet i minutter
            'distance': 'float64',  # Distanse i kilometer
            'calories': 'float64',  # Kaloriforbruk
            'average_hr': 'float64',  # Gjennomsnittlig puls
            'max_hr': 'float64',  # Maksimal puls
            'average_pace': 'float64',  # Gjennomsnittlig tempo (min/km)
            'total_elevation_gain': 'float64',  # Total stigning
            'steps': 'Int64',  # Antall skritt
            'training_effect': 'float64',  # Treningseffekt
            'vo2_max': 'float64',  # VO2 max
            'anaerobic_training_effect': 'float64',  # Anaerob treningseffekt
            'aerobic_training_effect': 'float64',  # Aerob treningseffekt
            'fitness_age': 'float64',  # Treningsalder
            'intensity_minutes': 'float64',  # Intensitetsminutter
            'max_cadence': 'float64',  # Maksimal kadens
            'average_cadence': 'float64',  # Gjennomsnittlig kadens
            'max_power': 'float64',  # Maksimal watt
            'average_power': 'float64',  # Gjennomsnittlig watt
            'updated_at': 'datetime64[ns, UTC]'  # Sist oppdatert
        }
        
        self.activity_details_columns = {
            'activity_id': 'Int64',
            'timestamp': 'datetime64[ns, UTC]',
            'latitude': 'float64',
            'longitude': 'float64',
            'altitude': 'float64',
            'speed': 'float64', # m/s
            'heart_rate': 'Int64',
            'cadence': 'Int64',
            'temperature': 'float64',
            'distance': 'float64' # meter
        }
        
        self.sleep_columns = {
            'date': 'datetime64[ns, UTC]',  # Dato for søvnøkt
            'duration': 'float64',  # Total søvnvarighet i timer
            'deep_sleep': 'float64',  # Dyp søvn i timer
            'light_sleep': 'float64',  # Lett søvn i timer
            'rem_sleep': 'float64',  # REM søvn i timer
            'awake': 'float64',  # Våken tid i timer
            'start_time': 'datetime64[ns, UTC]',  # Når man la seg
            'end_time': 'datetime64[ns, UTC]',  # Når man sto opp
            'updated_at': 'datetime64[ns, UTC]'  # Sist oppdatert
        }
        
        self.heart_rate_columns = {
            'date': 'datetime64[ns, UTC]',  # Dato
            'timestamp': 'datetime64[ns, UTC]',  # Tidspunkt for måling
            'value': 'float64',  # Pulsverdi
            'updated_at': 'datetime64[ns, UTC]'  # Sist oppdatert
        }
        
        self.resting_heart_rate_columns = {
            'date': 'datetime64[ns, UTC]',  # Dato
            'resting_heart_rate': 'float64',  # Hvilepuls
            'max_heart_rate': 'float64',  # Maksimal puls for dagen
            'min_heart_rate': 'float64',  # Minimal puls for dagen
            'updated_at': 'datetime64[ns, UTC]'  # Sist oppdatert
        }
        
        # Last eksisterende data eller opprett tomme DataFrames
        self.activities_df = self._load_or_create_df(self.activities_file, self.activity_columns, 'id')
        self.activity_details_df = self._load_or_create_df(self.activity_details_file, self.activity_details_columns)
        self.sleep_df = self._load_or_create_df(self.sleep_file, self.sleep_columns, 'date')
        self.heart_rate_df = self._load_or_create_df(self.heart_rate_file, self.heart_rate_columns, 'timestamp')
        self.resting_heart_rate_df = self._load_or_create_df(self.resting_heart_rate_file, self.resting_heart_rate_columns, 'date')

    def _ensure_data_directory(self):
        """Opprett data-mappen hvis den ikke eksisterer."""
        if not os.path.exists(self.data_dir):
            logger.info(f"Oppretter data-mappe: {self.data_dir}")
            os.makedirs(self.data_dir)

    def _convert_to_type(self, series: pd.Series, dtype: str, col_name: str) -> pd.Series:
        logger.debug(f"_convert_to_type kalt for kolonne '{col_name}', mål-dtype: {dtype}. Inndata eksempel (første 3): {series.head(3).to_list() if not series.empty else 'Tom serie'}")
        original_dtype = series.dtype
        try:
            if dtype == 'datetime64[ns, UTC]':
                converted_series = pd.to_datetime(series, errors='coerce', utc=True)
                logger.debug(f"  Etter pd.to_datetime for '{col_name}' (til UTC): type={converted_series.dtype}, eksempel: {converted_series.head(3).to_list() if not converted_series.empty else 'Tom serie'}")
                return converted_series
            elif dtype.startswith('datetime64'): # For other datetimes (e.g. no specified tz)
                converted_series = pd.to_datetime(series, errors='coerce')
                logger.debug(f"  Etter pd.to_datetime for '{col_name}' (uten UTC): type={converted_series.dtype}, eksempel: {converted_series.head(3).to_list() if not converted_series.empty else 'Tom serie'}")
                return converted_series
            elif dtype == 'Int64': 
                return pd.to_numeric(series, errors='coerce').astype(dtype)
            elif dtype.startswith('int') or dtype.startswith('float'):
                numeric_series = pd.to_numeric(series, errors='coerce')
                return numeric_series.astype(dtype) 
            elif dtype == 'string':
                return series.astype('string').fillna(pd.NA)
            else: 
                return series.astype(dtype)
        except Exception as e:
            logger.warning(f"Kunne ikke konvertere kolonne '{col_name}' til {dtype}. Feil: {e}. Bruker NA/NaT.", exc_info=True)
            # Fallback to a series of NAs/NaTs of the target type to prevent crashes
            if dtype.startswith('datetime64'): return pd.Series(pd.NaT, index=series.index, name=series.name, dtype=dtype)
            if dtype == 'Int64': return pd.Series(pd.NA, index=series.index, name=series.name, dtype=pd.Int64Dtype())
            if dtype.startswith('float'): return pd.Series(pd.NA, index=series.index, name=series.name, dtype='float64')
            if dtype == 'string': return pd.Series(pd.NA, index=series.index, name=series.name, dtype='string')
            return pd.Series([pd.NA] * len(series), index=series.index, name=series.name) # Generic NA for other types

    def _load_or_create_df(self, file_path: str, columns_schema: Dict[str, str], id_column: Optional[str] = None) -> pd.DataFrame:
        df = pd.DataFrame()
        expected_cols_dtypes = {col: dtype_str for col, dtype_str in columns_schema.items()}

        if os.path.exists(file_path):
            try:
                df = pd.read_parquet(file_path)
                logger.info(f"Lastet DataFrame fra {file_path} ({len(df)} rader)")
                
                # Sjekk for manglende kolonner og legg dem til
                for col, dtype_str in expected_cols_dtypes.items():
                    if col not in df.columns:
                        logger.warning(f"Kolonne '{col}' mangler i {file_path}. Legger den til med type {dtype_str}.")
                        if dtype_str.startswith('datetime64'):
                            df[col] = pd.Series(pd.NaT, index=df.index, dtype=dtype_str)
                        elif dtype_str == 'Int64':
                            df[col] = pd.Series(pd.NA, index=df.index, dtype=pd.Int64Dtype())
                        elif dtype_str == 'string':
                            df[col] = pd.Series(pd.NA, index=df.index, dtype='string')
                        elif dtype_str.startswith('float'):
                             df[col] = pd.Series(pd.NA, index=df.index, dtype='float64')
                        else: 
                            df[col] = pd.Series(pd.NA, index=df.index).astype(dtype_str) 
                
                # Sjekk for ekstra kolonner i filen som ikke er i skjemaet, og fjern dem
                extra_cols = [col for col in df.columns if col not in expected_cols_dtypes]
                if extra_cols:
                    logger.warning(f"Fjerner ekstra kolonner fra {file_path} som ikke er i skjemaet: {extra_cols}")
                    df.drop(columns=extra_cols, inplace=True)

                # Konverter alle kolonner til definert skjematype
                for col, dtype_str in expected_cols_dtypes.items():
                    if col in df.columns: # Kolonnen skal nå eksistere
                        df[col] = self._convert_to_type(df[col], dtype_str, col)

            except Exception as e:
                logger.error(f"Kunne ikke laste eller validere Parquet-fil {file_path}: {e}. Oppretter/bruker ny DataFrame.", exc_info=True)
                df = pd.DataFrame() # Nullstill df ved feil
        
        if df.empty:
            logger.info(f"Oppretter ny DataFrame-struktur for {file_path}")
            df = pd.DataFrame({col: pd.Series(dtype=dtype_str) for col, dtype_str in expected_cols_dtypes.items()})
        
        # Sikre korrekt kolonnerekkefølge som definert i skjemaet
        df = df.reindex(columns=list(expected_cols_dtypes.keys()))

        if id_column and id_column in df.columns:
            df.dropna(subset=[id_column], inplace=True)
            if not df.empty and df.index.name != id_column:
                 try:
                    df = df.set_index(id_column, drop=True)
                    df.sort_index(inplace=True)
                 except Exception as e_index:
                    logger.error(f"Kunne ikke sette/sortere index '{id_column}' for {file_path}: {e_index}. Beholder standard index.")
        elif id_column:
             logger.warning(f"ID-kolonne '{id_column}' ikke funnet i DataFrame for {file_path} under lasting/oppretting.")

        logger.debug(f"DataFrame for {file_path} initialisert. Kolonner: {df.columns.tolist()}, Typer: {df.dtypes.to_dict()}, Index: {df.index.name}, Størrelse: {len(df)}")
        return df

    def _save_data_internal(
        self, 
        data_list: List[Dict[str, Any]], 
        df_attr_name: str, 
        file_path: str, 
        columns_schema: Dict[str, str], 
        id_column: str,
        data_type_name: str 
    ):
        if not data_list:
            logger.debug(f"Ingen {data_type_name}-data å lagre.")
            return

        current_df_in_memory: pd.DataFrame = getattr(self, df_attr_name).copy()
        
        # Robust håndtering av duplikat 'id' i kolonne og indeks
        if current_df_in_memory.index.name == id_column:
            if id_column in current_df_in_memory.columns:
                logger.warning(f"Fjerner duplikat '{id_column}' kolonne før reset_index for {data_type_name}.")
                current_df_in_memory.drop(columns=[id_column], inplace=True)
            current_df_in_memory.reset_index(inplace=True)

        # For å sammenligne senere, lag en kopi av den nåværende tilstanden slik den *ville* blitt lagret (med riktig indeks og sortering)
        # Dette sikrer at .equals() fungerer som forventet.
        # Vi må også sikre at current_df_in_memory har samme kolonner og rekkefølge som schema
        current_df_state_for_comparison = current_df_in_memory.reindex(columns=list(columns_schema.keys())).copy()
        if id_column in current_df_state_for_comparison.columns and current_df_state_for_comparison.index.name == id_column:
            current_df_state_for_comparison.sort_index(inplace=True)
        elif id_column in current_df_state_for_comparison.columns: # Hvis id_column er en kolonne, men ikke index
            current_df_state_for_comparison.sort_values(by=id_column, inplace=True)
            current_df_state_for_comparison.reset_index(drop=True, inplace=True)

        # 1. Klargjør innkommende data
        temp_df = pd.DataFrame(data_list)
        new_data_df = pd.DataFrame(columns=list(columns_schema.keys()))
        for col_name in columns_schema:
            if col_name in temp_df.columns:
                new_data_df[col_name] = temp_df[col_name]
            else: 
                # Fyll manglende kolonner med passende NA-type basert på skjema
                dtype_str = columns_schema[col_name]
                if dtype_str.startswith('datetime64'):
                    new_data_df[col_name] = pd.Series(pd.NaT, index=temp_df.index, dtype=dtype_str)
                elif dtype_str == 'Int64':
                    new_data_df[col_name] = pd.Series(pd.NA, index=temp_df.index, dtype=pd.Int64Dtype())
                elif dtype_str == 'string':
                    new_data_df[col_name] = pd.Series(pd.NA, index=temp_df.index, dtype='string')
                else: 
                    new_data_df[col_name] = pd.Series(pd.NA, index=temp_df.index)
        
        new_data_df['updated_at'] = pd.Timestamp.now(tz='UTC')
        for col, dtype_str in columns_schema.items():
            if col in new_data_df.columns:
                new_data_df[col] = self._convert_to_type(new_data_df[col], dtype_str, col)
        
        original_incoming_count = len(new_data_df)
        new_data_df.dropna(subset=[id_column], inplace=True)
        valid_incoming_count = len(new_data_df)
        if original_incoming_count != valid_incoming_count:
            logger.warning(f"{original_incoming_count - valid_incoming_count} rader fjernet fra {data_type_name} pga. manglende ID etter konvertering.")

        if new_data_df.empty:
            logger.info(f"Ingen gyldige {data_type_name}-data igjen å lagre etter ID-validering.")
            # Oppdater den interne DataFrame-en selv om ingenting lagres til disk, hvis den var tom
            if current_df_in_memory.empty:
                 setattr(self, df_attr_name, pd.DataFrame(columns=columns_schema.keys()).set_index(id_column, drop=False) if id_column else pd.DataFrame(columns=columns_schema.keys()) )
            return
            
        # 2. Upsert-logikk
        # Kombiner nåværende (fra minne, ikke sammenligningskopi) og nye data
        # Reset index for å unngå konflikter, spesielt hvis ID-kolonnen ikke er index i current_df_in_memory
        current_df_reset = current_df_in_memory.reset_index(drop=True)
        new_data_df_reset = new_data_df.reset_index(drop=True)

        # Forbered for concat: sikre at ID-kolonnen har samme datatype i begge for å unngå cast-feil
        id_col_dtype_target = columns_schema[id_column]
        if id_column in current_df_reset.columns:
            current_df_reset[id_column] = self._convert_to_type(current_df_reset[id_column], id_col_dtype_target, id_column)
        if id_column in new_data_df_reset.columns:
             new_data_df_reset[id_column] = self._convert_to_type(new_data_df_reset[id_column], id_col_dtype_target, id_column)
        
        combined_df = pd.concat([current_df_reset, new_data_df_reset], ignore_index=True)
        combined_df.drop_duplicates(subset=[id_column], keep='last', inplace=True)
        
        # Sikre kolonnerekkefølge og sortering for konsistens og for .equals() sammenligning
        combined_df = combined_df.reindex(columns=list(columns_schema.keys()))
        if id_column in combined_df:
            combined_df.sort_values(by=id_column, inplace=True)
            combined_df.reset_index(drop=True, inplace=True) # Reset index etter sortering før .equals()

        # 3. Sammenlign for å se om det er faktiske endringer
        # Klargjør current_df_state_for_comparison for .equals()
        current_df_state_for_comparison = current_df_state_for_comparison.reindex(columns=list(columns_schema.keys()))
        if id_column in current_df_state_for_comparison:
            current_df_state_for_comparison.sort_values(by=id_column, inplace=True)
            current_df_state_for_comparison.reset_index(drop=True, inplace=True)

        data_changed = not combined_df.equals(current_df_state_for_comparison)

        # 4. Sett ID-kolonnen som index igjen på den endelige combined_df før den settes på self
        final_df_for_memory = combined_df.copy()
        if id_column in final_df_for_memory.columns:
            final_df_for_memory.dropna(subset=[id_column], inplace=True) # Viktig før set_index
            if not final_df_for_memory.empty:
                try:
                    final_df_for_memory = final_df_for_memory.set_index(id_column, drop=False)
                    final_df_for_memory.sort_index(inplace=True) # Sorter etter den nye indeksen
                except Exception as e_idx_final:
                    logger.warning(f"Kunne ikke sette/sortere index på final_df_for_memory for {data_type_name}: {e_idx_final}.")
            elif id_column: # Hvis tom etter dropna, men id_column er forventet
                 final_df_for_memory = pd.DataFrame(columns=columns_schema.keys()).set_index(id_column, drop=False)

        setattr(self, df_attr_name, final_df_for_memory)
        
        num_in_final_df = len(final_df_for_memory)
        # Beregn statistikk mer nøyaktig basert på IDer
        incoming_ids = set(new_data_df[id_column].dropna().unique())
        existing_ids_before = set(current_df_in_memory[id_column].dropna().unique() if id_column in current_df_in_memory else [])
        
        num_newly_added = len(incoming_ids - existing_ids_before)
        num_potentially_updated = len(incoming_ids.intersection(existing_ids_before))

        if data_changed:
            logger.info(f"Data for {data_type_name} har endret seg. Lagrer til disk...")
            try:
                self._ensure_data_directory() 
                # Bruk den *ikke*-indekserte combined_df for lagring for å unngå index-navn problemer
                # Parquet lagrer ikke indeksen på samme måte som CSV, så det er tryggere å resette den.
                df_to_save = combined_df.reset_index(drop=True) 
                if not df_to_save.empty:
                    df_to_save.to_parquet(file_path)
                elif os.path.exists(file_path):
                    logger.info(f"Lagrer tom DataFrame til {file_path} for {data_type_name} (overskriver eksisterende).")
                    pd.DataFrame(columns=list(columns_schema.keys())).to_parquet(file_path)
                else:
                    logger.info(f"Ingen {data_type_name}-data å lagre til {file_path} (DataFrame er tom).")
                
                logger.info(
                    f"{data_type_name.capitalize()} lagret til {file_path}. "
                    f"Mottatt: {original_incoming_count}, Gyldige innkommende: {valid_incoming_count}, "
                    f"Nye: {num_newly_added}, Potensielt oppdatert: {num_potentially_updated}. "
                    f"Totalt i fil: {num_in_final_df}."
                )
            except Exception as e:
                logger.error(f"Kunne ikke lagre {data_type_name} til Parquet-fil {file_path}: {e}", exc_info=True)
        else:
            logger.info(
                f"Ingen endringer i data for {data_type_name}. Hopper over skriving til disk. "
                f"Mottatt: {original_incoming_count}, Gyldige innkommende: {valid_incoming_count}, "
                f"Nye (ikke lagret): {num_newly_added}, Potensielt oppdatert (ikke lagret): {num_potentially_updated}. "
                f"Totalt (uendret): {num_in_final_df}."
            )

    def save_activities(self, activities: List[Dict[str, Any]]) -> None:
        """Lagrer en liste med aktiviteter etter å ha transformert dem til riktig format."""
        if not activities:
            logger.info("Ingen aktiviteter å lagre.")
            return
        
        logger.info(f"Lagrer {len(activities)} aktiviteter. Første aktivitet nøkler: {list(activities[0].keys()) if activities else 'Ingen'}")
        logger.debug(f"Første aktivitet data: {json.dumps(activities[0], cls=DateTimeEncoder, indent=2) if activities else 'Ingen'}")

        # Kartlegging fra Garmin API-felt til DataFrame-kolonner
        column_mapping = {
            'activityId': 'id',
            'activityName': 'name',
            'activityType.typeKey': 'type',
            'startTimeGMT': 'start_time',
            'duration': 'duration', # I sekunder fra Garmin
            'distance': 'distance', # I meter fra Garmin
            'calories': 'calories',
            'averageHR': 'average_hr',
            'maxHR': 'max_hr',
            'vO2MaxValue': 'vo2_max',
            'trainingEffectLabel': 'training_effect_label',
            'totalElevationGain': 'total_elevation_gain',
            'steps': 'steps'
            # Flere felt kan legges til her
        }
        
        transformed_data = []
        for activity in activities:
            record = {}
            for api_key, df_key in column_mapping.items():
                # Håndter nøstede nøkler som 'activityType.typeKey'
                value = activity
                try:
                    for part in api_key.split('.'):
                        value = value.get(part) if isinstance(value, dict) else None
                        if value is None:
                            break
                    record[df_key] = value
                except (KeyError, TypeError):
                    record[df_key] = None # Sett til None hvis nøkkelen ikke finnes

            # Konverteringer og beregninger
            if record.get('duration'):
                record['duration'] /= 60  # Fra sekunder til minutter
            if record.get('distance'):
                record['distance'] /= 1000  # Fra meter til km
            if record.get('distance') and record.get('duration') and record['duration'] > 0:
                record['average_pace'] = (record['duration'] * 60 / record['distance']) / 60 if record['distance'] > 0 else 0
            
            transformed_data.append(record)
            
        self._save_data_internal(
            data_list=transformed_data,
            df_attr_name='activities_df',
            file_path=self.activities_file,
            columns_schema=self.activity_columns,
            id_column='id',
            data_type_name='aktiviteter'
        )

    def save_sleep_data(self, sleep_data: List[Dict[str, Any]]):
        self._save_data_internal(
            data_list=sleep_data,
            df_attr_name='sleep_df',
            file_path=self.sleep_file,
            columns_schema=self.sleep_columns,
            id_column='date',
            data_type_name="søvndata"
        )

    def save_heart_rate_data(self, heart_rate_data: List[Dict[str, Any]]):
        self._save_data_internal(
            data_list=heart_rate_data,
            df_attr_name='heart_rate_df',
            file_path=self.heart_rate_file,
            columns_schema=self.heart_rate_columns,
            id_column='timestamp', 
            data_type_name="pulsdata"
        )

    def save_resting_heart_rate_data(self, resting_hr_data: List[Dict[str, Any]]):
        if isinstance(resting_hr_data, dict):
            resting_hr_data = [resting_hr_data]
            
        self._save_data_internal(
            data_list=resting_hr_data,
            df_attr_name='resting_heart_rate_df',
            file_path=self.resting_heart_rate_file,
            columns_schema=self.resting_heart_rate_columns,
            id_column='date',
            data_type_name="hvilepulsdata"
        )

    def save_activity_details(self, activity_id: int, fit_data: bytes):
        """Parser en .fit-fil og lagrer tidsseriedataene."""
        if not fit_data:
            logger.warning("Mottok ingen .fit-data å lagre.")
            return

        try:
            # Garmin sender ofte .fit-filer i et zip-arkiv.
            if fit_data.startswith(b'PK\x03\x04'):
                logger.info(f"Mottok zip-arkiv for aktivitet {activity_id}. Pakker ut...")
                with zipfile.ZipFile(BytesIO(fit_data)) as z:
                    # Finn den første .fit-filen i arkivet
                    fit_filename = next((name for name in z.namelist() if name.lower().endswith('.fit')), None)
                    if not fit_filename:
                        raise ValueError(f"Fant ingen .fit-fil i zip-arkivet for aktivitet {activity_id}.")
                    
                    logger.info(f"Fant {fit_filename} i zip-arkivet. Leser innholdet.")
                    fit_data = z.read(fit_filename) # Overskriv fit_data med det utpakkede innholdet

            # Prøv å parse .fit-filen
            fitfile = fitparse.FitFile(BytesIO(fit_data))
            
            records = []
            for record in fitfile.get_messages('record'):
                record_data = {}
                # Gå gjennom alle feltene i recorden
                for field in record:
                    # Hopp over ukjente eller irrelevante felter
                    if field.name and 'unknown' not in field.name and field.value is not None:
                        # Spesifikk navne-mapping
                        if field.name == 'enhanced_speed':
                            # Konverter fra m/s til km/t
                            record_data['speed'] = field.value * 3.6 
                        elif field.name == 'enhanced_altitude':
                            record_data['altitude'] = field.value
                        else:
                            record_data[field.name] = field.value
                
                # Sørg for at 'timestamp' finnes før vi legger til
                if 'timestamp' in record_data:
                    records.append(record_data)

            if not records:
                logger.warning(f"Fant ingen 'record'-meldinger med gyldige data i FIT-filen for aktivitet {activity_id}.")
                return
            
            # Lag en DataFrame fra de innsamlede records
            new_details_df = pd.DataFrame(records)
            
            # Sørg for at activity_id blir lagt til
            new_details_df['activity_id'] = activity_id

            # Definer forventede kolonner for å sikre at de finnes
            final_columns = ['activity_id', 'timestamp', 'heart_rate', 'speed', 'altitude', 'latitude', 'longitude', 'distance']
            
            # Sjekk hvilke kolonner som faktisk finnes i den nye dataframen
            for col in final_columns:
                if col not in new_details_df.columns:
                    new_details_df[col] = np.nan # Legg til som tom hvis den mangler

            # Velg og rekkestill kolonner for å matche skjemaet
            new_details_df = new_details_df[final_columns]
            
            # Konverter datatyper ved å iterere gjennom kolonner
            for col in final_columns:
                if col in new_details_df.columns:
                    new_details_df[col] = self._convert_to_type(new_details_df[col], self.activity_details_columns[col], col)

            # Fjern eksisterende detaljer for denne aktiviteten for å unngå duplikater
            if 'activity_id' in self.activity_details_df.columns and not self.activity_details_df.empty:
                self.activity_details_df = self.activity_details_df[self.activity_details_df['activity_id'] != activity_id]

            # Legg til de nye detaljene
            self.activity_details_df = pd.concat([self.activity_details_df, new_details_df], ignore_index=True)

            logger.info(f"Lagret {len(new_details_df)} detaljerte datapunkter for aktivitet {activity_id}.")
        except (fitparse.utils.FitHeaderError, fitparse.utils.FitCRCError) as e:
            logger.error(f"FITParse-feil ved behandling av data for aktivitet {activity_id}: {e}", exc_info=True)
            return
        except Exception as e:
            logger.error(f"Uventet feil under behandling av FIT-data for aktivitet {activity_id}: {e}", exc_info=True)
            return

        try:
            # Lagre til fil
            self.activity_details_df.to_parquet(self.activity_details_file, index=False)
            logger.info(f"Lagret {len(new_details_df)} detaljerte datapunkter for aktivitet {activity_id}.")
        except Exception as e:
            logger.error(f"Kunne ikke lagre detaljerte datapunkter for aktivitet {activity_id} til Parquet-fil: {e}", exc_info=True)

    def _get_data_internal(
        self, 
        df_attr_name: str, 
        id_column: Optional[str] = None, 
        start_date_col: Optional[str] = None, 
        end_date_col: Optional[str] = None,   
        start_date_val: Optional[datetime] = None, 
        end_date_val: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        df_in_memory: pd.DataFrame = getattr(self, df_attr_name)
        
        if df_in_memory.empty:
            return []

        # Arbeid med en kopi for å unngå å endre den interne DataFrame-tilstanden
        filtered_df = df_in_memory.copy()

        # --- Løsning for "ValueError: cannot insert id, already exists" ---
        # Hvis en kolonne har samme navn som indeksen, vil reset_index() krasje.
        if filtered_df.index.name and filtered_df.index.name in filtered_df.columns:
            logger.debug(f"Fjerner duplikatkolonne '{filtered_df.index.name}' før reset_index for å unngå krasj.")
            filtered_df = filtered_df.drop(columns=[filtered_df.index.name])
        
        # Gjør indeksen om til en vanlig kolonne slik at den inkluderes i resultatet
        filtered_df = filtered_df.reset_index()
        
        # --- Robust datofiltrering ---
        try:
            if start_date_val and start_date_col and start_date_col in filtered_df.columns:
                series_to_filter = pd.to_datetime(filtered_df[start_date_col], errors='coerce', utc=True)
                valid_dates_mask = series_to_filter.notna()
                filtered_df = filtered_df[valid_dates_mask]
                filtered_df = filtered_df[series_to_filter[valid_dates_mask] >= pd.Timestamp(start_date_val, tz='UTC')]

            if end_date_val and end_date_col and end_date_col in filtered_df.columns:
                series_to_filter = pd.to_datetime(filtered_df[end_date_col], errors='coerce', utc=True)
                valid_dates_mask = series_to_filter.notna()
                filtered_df = filtered_df[valid_dates_mask]
                filtered_df = filtered_df[series_to_filter[valid_dates_mask] <= pd.Timestamp(end_date_val, tz='UTC')]
        except Exception as e:
            logger.error(f"Uventet feil under datofiltrering i {df_attr_name}: {e}", exc_info=True)
            return []

        # --- Løsning for "ValueError: ... nan is not JSON compliant" ---
        # Erstatt pandas/numpy sine 'Not a Number/Time'-verdier med None, som blir til 'null' i JSON.
        final_df = filtered_df.replace({pd.NA: None, np.nan: None, pd.NaT: None})

        return final_df.to_dict('records')

    def get_activities(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Leser alle JSON-filer med aktiviteter fra data-mappen.
        Filtrering på dato er ikke implementert for denne JSON-leseren.
        """
        all_activities = []
        json_files = [f for f in os.listdir(self.data_dir) if f.endswith('.json') and not f.startswith('sleep')]
        
        logger.info(f"Fant {len(json_files)} potensielle JSON-filer for aktiviteter.")

        for filename in json_files:
            file_path = os.path.join(self.data_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Noen filer er en liste direkte, andre er et objekt med en liste
                    if isinstance(data, list):
                        all_activities.extend(data)
                    elif isinstance(data, dict) and 'activities' in data and isinstance(data['activities'], list):
                        all_activities.extend(data['activities'])
            except json.JSONDecodeError:
                logger.warning(f"Kunne ikke lese JSON fra {file_path}. Filen kan være korrupt eller tom.")
            except Exception as e:
                logger.error(f"En uventet feil oppstod ved lesing av {file_path}: {e}")
        
        logger.info(f"Lastet totalt {len(all_activities)} aktiviteter fra JSON-filer.")
        return all_activities

    def get_sleep_data(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        return self._get_data_internal(
            df_attr_name='sleep_df',
            id_column='date',
            start_date_col='date', 
            end_date_col='date',
            start_date_val=start_date,
            end_date_val=end_date
        )

    def get_heart_rate_data(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        return self._get_data_internal(
            df_attr_name='heart_rate_df',
            id_column='timestamp',
            start_date_col='timestamp', 
            end_date_col='timestamp',
            start_date_val=start_date,
            end_date_val=end_date
        )

    def get_resting_heart_rate_data(self, target_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        if target_date:
            start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            return self._get_data_internal(
                df_attr_name='resting_heart_rate_df',
                id_column='date',
                start_date_col='date',
                end_date_col='date',
                start_date_val=start_of_day,
                end_date_val=end_of_day
            )
        else: 
             return self._get_data_internal(
                df_attr_name='resting_heart_rate_df',
                id_column='date'
            )

    def get_activity_date_coverage(self) -> (Optional[datetime], Optional[datetime]):
        """
        Finner den tidligste og seneste 'start_time' for lagrede aktiviteter.
        Returnerer (min_date, max_date) eller (None, None) hvis ingen data finnes.
        """
        if self.activities_df.empty or 'start_time' not in self.activities_df.columns:
            return None, None
        
        start_time_series = self.activities_df['start_time'].dropna()
        if start_time_series.empty:
            return None, None
            
        min_date = start_time_series.min()
        max_date = start_time_series.max()
        
        # Sørg for at vi returnerer datetime-objekter
        min_date_ts = pd.to_datetime(min_date, utc=True) if pd.notna(min_date) else None
        max_date_ts = pd.to_datetime(max_date, utc=True) if pd.notna(max_date) else None
        
        logger.info(f"Datadekning for aktiviteter funnet: Fra {min_date_ts} til {max_date_ts}")
        return min_date_ts, max_date_ts

    def get_activity_details(self, activity_id: int) -> List[Dict[str, Any]]:
        """Henter detaljerte tidsseriedata for en gitt aktivitet."""
        if self.activity_details_df.empty or 'activity_id' not in self.activity_details_df.columns:
             logger.warning("Activity details DataFrame er tom eller mangler 'activity_id' kolonne.")
             return []

        details_df = self.activity_details_df[self.activity_details_df['activity_id'] == activity_id]
        
        if details_df.empty:
            return []
            
        # Sorter etter tidspunkt
        details_df = details_df.sort_values(by='timestamp').copy()

        # Konverter NaN til None for JSON-serialisering
        details_df.replace({np.nan: None}, inplace=True)
        
        return details_df.to_dict('records')