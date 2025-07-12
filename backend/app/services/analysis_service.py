import pandas as pd
import numpy as np
import logging
from fastapi import HTTPException
from ..storage import DataStorage
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from ..database.models.activity import Activity

logger = logging.getLogger(__name__)

class AnalysisService:
    def __init__(self, storage: DataStorage):
        self.storage = storage

    def calculate_negative_split(self, activity_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """
        Beregner negativ split for en aktivitet basert på FIT-data.
        Negativ split = (andre halvdel pace - første halvdel pace) / første halvdel pace * 100
        Positiv verdi = negativ split (raskere andre halvdel)
        Negativ verdi = positiv split (saktere andre halvdel)
        """
        try:
            # Hent aktivitet fra database
            activity = db.query(Activity).filter(Activity.activity_id == str(activity_id)).first()
            if not activity:
                logger.warning(f"Aktivitet {activity_id} ikke funnet i database")
                return None
            
            # Hvis allerede beregnet, returner cached verdi
            if activity.negative_split_percent is not None:
                return {
                    "activity_id": activity_id,
                    "negative_split_percent": round(activity.negative_split_percent, 2),
                    "calculation_method": "cached"
                }
            
            # Hent FIT-data
            details_df = self.storage.get_activity_details(activity_id)
            if details_df is None or details_df.empty:
                logger.warning(f"Ingen FIT-data tilgjengelig for aktivitet {activity_id}")
                raise HTTPException(status_code=404, detail="No FIT data available for this activity")
            
            # Sjekk at vi har nødvendige kolonner
            required_columns = ['speed', 'timestamp']
            if not all(col in details_df.columns for col in required_columns):
                logger.warning(f"Mangler nødvendige kolonner for negative split: {required_columns}")
                raise HTTPException(status_code=404, detail="Missing required data columns for negative split calculation")
            
            # Filtrer ut rader med gyldig speed og timestamp data
            valid_data = details_df.dropna(subset=['speed', 'timestamp'])
            valid_data = valid_data[(valid_data['speed'] > 0)]
            
            if len(valid_data) < 20:
                logger.warning(f"Ikke nok datapunkter for negative split beregning: {len(valid_data)}")
                raise HTTPException(status_code=404, detail="Insufficient data points for negative split calculation")
            
            # Sorter etter timestamp
            valid_data = valid_data.sort_values('timestamp')
            
            # Del i to halvdeler
            midpoint = len(valid_data) // 2
            first_half = valid_data.iloc[:midpoint]
            second_half = valid_data.iloc[midpoint:]
            
            # Beregn gjennomsnittlig pace for hver halvdel (pace = 1000 / speed / 60)
            first_half_pace = 1000 / (first_half['speed'].mean() * 60)  # min/km
            second_half_pace = 1000 / (second_half['speed'].mean() * 60)  # min/km
            
            if first_half_pace <= 0:
                logger.warning(f"Ugyldig pace for første halvdel: {first_half_pace}")
                return None
            
            # Beregn negative split prosentvis
            negative_split_percent = ((first_half_pace - second_half_pace) / first_half_pace) * 100
            
            # Lagre i database
            activity.negative_split_percent = negative_split_percent
            db.commit()
            
            logger.info(f"Beregnet negative split for aktivitet {activity_id}: {negative_split_percent:.2f}%")
            
            return {
                "activity_id": activity_id,
                "negative_split_percent": round(negative_split_percent, 2),
                "calculation_method": "calculated",
                "first_half_pace": round(first_half_pace, 2),
                "second_half_pace": round(second_half_pace, 2)
            }
            
        except HTTPException:
            # Re-raise HTTPExceptions without logging them as errors
            raise
        except Exception as e:
            logger.error(f"Feil ved beregning av negative split for aktivitet {activity_id}: {e}")
            return None

    def calculate_decoupling(self, activity_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """
        Beregner cardiac-aerobic decoupling for en aktivitet basert på FIT-data.
        Decoupling = ((HR2/Speed2) / (HR1/Speed1) - 1) * 100
        Positiv verdi = positiv decoupling (hjerteraten øker mer enn hastigheten)
        Negativ verdi = negativ decoupling (hjerteraten øker mindre enn hastigheten)
        """
        try:
            # Hent aktivitet fra database
            activity = db.query(Activity).filter(Activity.activity_id == str(activity_id)).first()
            if not activity:
                logger.warning(f"Aktivitet {activity_id} ikke funnet i database")
                return None
            
            # Hvis allerede beregnet, returner cached verdi
            if activity.decoupling_percent is not None:
                return {
                    "activity_id": activity_id,
                    "decoupling_percent": round(activity.decoupling_percent, 2),
                    "calculation_method": "cached"
                }
            
            # Hent FIT-data
            details_df = self.storage.get_activity_details(activity_id)
            if details_df is None or details_df.empty:
                logger.warning(f"Ingen FIT-data tilgjengelig for aktivitet {activity_id}")
                raise HTTPException(status_code=404, detail="No FIT data available for this activity")
            
            # Sjekk at vi har nødvendige kolonner
            required_columns = ['heart_rate', 'speed', 'timestamp']
            if not all(col in details_df.columns for col in required_columns):
                logger.warning(f"Mangler nødvendige kolonner for decoupling: {required_columns}")
                raise HTTPException(status_code=404, detail="Missing required data columns for decoupling calculation")
            
            # Filtrer ut rader med gyldig data
            valid_data = details_df.dropna(subset=['heart_rate', 'speed', 'timestamp'])
            valid_data = valid_data[(valid_data['heart_rate'] > 0) & (valid_data['speed'] > 0)]
            
            if len(valid_data) < 20:
                logger.warning(f"Ikke nok datapunkter for decoupling beregning: {len(valid_data)}")
                raise HTTPException(status_code=404, detail="Insufficient data points for decoupling calculation")
            
            # Sorter etter timestamp
            valid_data = valid_data.sort_values('timestamp')
            
            # Del i to halvdeler
            midpoint = len(valid_data) // 2
            first_half = valid_data.iloc[:midpoint]
            second_half = valid_data.iloc[midpoint:]
            
            # Beregn gjennomsnittlig HR og speed for hver halvdel
            first_half_hr = first_half['heart_rate'].mean()
            first_half_speed = first_half['speed'].mean()
            second_half_hr = second_half['heart_rate'].mean()
            second_half_speed = second_half['speed'].mean()
            
            if (pd.isna(first_half_hr) or pd.isna(first_half_speed) or 
                pd.isna(second_half_hr) or pd.isna(second_half_speed) or
                first_half_speed <= 0 or second_half_speed <= 0):
                logger.warning(f"Ugyldig data for decoupling beregning")
                return None
            
            # Beregn HR:Speed ratio for hver halvdel
            first_half_ratio = first_half_hr / first_half_speed
            second_half_ratio = second_half_hr / second_half_speed
            
            if first_half_ratio <= 0:
                logger.warning(f"Ugyldig ratio for første halvdel: {first_half_ratio}")
                return None
            
            # Beregn decoupling prosentvis
            decoupling_percent = ((second_half_ratio / first_half_ratio) - 1) * 100
            
            # Lagre i database
            activity.decoupling_percent = decoupling_percent
            db.commit()
            
            logger.info(f"Beregnet decoupling for aktivitet {activity_id}: {decoupling_percent:.2f}%")
            
            return {
                "activity_id": activity_id,
                "decoupling_percent": round(decoupling_percent, 2),
                "calculation_method": "calculated",
                "first_half_hr": round(first_half_hr, 1),
                "first_half_speed": round(first_half_speed, 2),
                "second_half_hr": round(second_half_hr, 1),
                "second_half_speed": round(second_half_speed, 2)
            }
            
        except HTTPException:
            # Re-raise HTTPExceptions without logging them as errors
            raise
        except Exception as e:
            logger.error(f"Feil ved beregning av decoupling for aktivitet {activity_id}: {e}")
            return None

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

    def get_hrv_for_activity_date(self, activity_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """Henter HRV-data for datoen en spesifikk aktivitet ble utført."""
        try:
            # 1. Hent aktiviteten fra databasen for å finne datoen
            activity = db.query(Activity).filter(Activity.activity_id == str(activity_id)).first()
            if not activity:
                raise HTTPException(status_code=404, detail="Aktivitet ikke funnet")
            
            activity_date = activity.start_time.date()

            # 2. Sjekk om datoen er før 2023 [[memory:3033754]]
            if activity_date.year < 2023:
                raise HTTPException(
                    status_code=404,
                    detail=f"HRV-data er ikke tilgjengelig for datoen {activity_date} (før 2023)."
                )

            # 3. Hent all HRV-data
            hrv_df = self.storage.get_hrv_data()
            
            if hrv_df is None or hrv_df.empty:
                raise HTTPException(
                    status_code=404,
                    detail=f"Ingen HRV-data funnet i systemet."
                )
            
            # 4. Filtrer på aktivitetsdatoen
            activity_date_pd = pd.to_datetime(activity_date).tz_localize(hrv_df.index.tz)
            daily_hrv_df = hrv_df[hrv_df.index.date == activity_date]
            
            if daily_hrv_df.empty:
                raise HTTPException(
                    status_code=404,
                    detail=f"Ingen HRV-data funnet for datoen {activity_date}."
                )
            
            # 5. Konverter til dict og returner
            hrv_data = daily_hrv_df.iloc[0].to_dict()
            # Legg til datoen som en verdi i responsen
            hrv_data['date'] = activity_date.strftime('%Y-%m-%d')
            
            return hrv_data

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Feil ved henting av HRV-data for aktivitet {activity_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    def get_hrv_over_time(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> dict:
        """Henter HRV-data over tid med valgfri datofiltrering."""
        try:
            hrv_df = self.storage.get_hrv_data()
            
            if hrv_df is None or hrv_df.empty:
                return {"hrv_data": [], "message": "Ingen HRV-data tilgjengelig"}
            
            # Filtrer på dato (indeks) hvis spesifisert
            if start_date:
                start_dt = pd.to_datetime(start_date).tz_localize(hrv_df.index.tz)
                hrv_df = hrv_df[hrv_df.index >= start_dt]
            
            if end_date:
                end_dt = pd.to_datetime(end_date).tz_localize(hrv_df.index.tz)
                hrv_df = hrv_df[hrv_df.index <= end_dt]
            
            # Sorter etter dato (indeks)
            hrv_df.sort_index(inplace=True)
            
            # Beregn 7-dagers glidende gjennomsnitt
            if 'last_night_avg' in hrv_df.columns and not hrv_df.empty:
                hrv_df['rolling_avg_7d'] = hrv_df['last_night_avg'].rolling(window=7, min_periods=1).mean()
            else:
                hrv_df['rolling_avg_7d'] = None
            
            # Konverter til liste av dictionaries, gjør om indeksen til en kolonne
            hrv_data = hrv_df.reset_index().replace({np.nan: None}).to_dict(orient='records')
            
            return {
                "hrv_data": hrv_data,
                "total_records": len(hrv_data)
            }
            
        except Exception as e:
            logger.error(f"Feil ved henting av HRV-data: {e}", exc_info=True)
            return {"hrv_data": [], "error": str(e)}

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
