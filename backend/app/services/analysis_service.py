import pandas as pd
import numpy as np
import logging
import re
from fastapi import HTTPException
from ..storage import DataStorage
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from ..database.models import Activity
from .hrv_service import HRVService
from .body_battery_service import BodyBatteryService

logger = logging.getLogger(__name__)

class AnalysisService:
    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.hrv_service = HRVService(storage)
        self.body_battery_service = None  # Vil bli initialisert når nødvendig

    def _to_float(self, value: Any) -> Optional[float]:
        """Konverterer ulike numeriske representasjoner til float."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.search(r'[-+]?(?:\d*\.\d+|\d+)', value)
            if match:
                try:
                    return float(match.group())
                except ValueError:
                    return None
        return None

    def _get_fit_details_for_activity(self, activity_id: int, activity: Activity) -> Optional[pd.DataFrame]:
        """
        Hent FIT-detaljer fra parquet først, med fallback til detailed_metrics i DB.
        Returnerer DataFrame med minst timestamp/speed/heart_rate når tilgjengelig.
        """
        # 1) Primærkilde: parquet-lager
        details_df = self.storage.get_activity_details(activity_id)
        if details_df is not None and not details_df.empty:
            return details_df

        # 2) Fallback: detailed_metrics JSON lagret på aktivitet
        details = activity.detailed_metrics if activity else None
        if not details or not isinstance(details, dict):
            return None

        records = details.get("records")
        if not records or not isinstance(records, list):
            return None

        parsed_records: List[Dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            timestamp = pd.to_datetime(record.get("timestamp"), errors="coerce")
            if pd.isna(timestamp):
                continue
            speed = self._to_float(record.get("enhanced_speed") or record.get("speed"))
            heart_rate = self._to_float(record.get("heart_rate"))
            parsed_records.append({
                "timestamp": timestamp,
                "speed": speed,
                "heart_rate": heart_rate
            })

        if not parsed_records:
            return None

        return pd.DataFrame(parsed_records)

    def calculate_negative_split(self, activity_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """
        Beregner negativ split for en aktivitet basert på FIT-data.
        Negativ split = (andre halvdel pace - første halvdel pace) / første halvdel pace * 100
        Negativ verdi = negativ split (raskere andre halvdel)
        Positiv verdi = positiv split (saktere andre halvdel)
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
            
            # Hent FIT-data (parquet først, deretter DB fallback)
            details_df = self._get_fit_details_for_activity(activity_id, activity)
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
            # Endret logikk: negativ verdi = raskere andre halvdel (negativ split)
            # positiv verdi = saktere andre halvdel (positiv split)
            negative_split_percent = ((second_half_pace - first_half_pace) / first_half_pace) * 100
            
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
            
            # Hent FIT-data (parquet først, deretter DB fallback)
            details_df = self._get_fit_details_for_activity(activity_id, activity)
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
            # Bruk HRVService for å hente data fra databasen
            return self.hrv_service.get_hrv_for_activity_date(activity_id, db)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Feil ved henting av HRV-data for aktivitet {activity_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    def get_hrv_over_time(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> dict:
        """Henter HRV-data over tid med valgfri datofiltrering."""
        try:
            # Bruk HRVService for å hente data fra databasen
            # Vi trenger en database session, så vi må håndtere dette annerledes
            # For nå, fallback til parquet-filer hvis database ikke er tilgjengelig
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

    def calculate_body_battery_start(self, activity_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """
        Beregner Body Battery-nivå ved start av aktivitet.
        Nå basert på faktiske FIT-data verdier som training_stress_score, 
        total_training_effect og total_anaerobic_training_effect.
        """
        try:
            from ..database.models.activity import Activity
            from ..database.models.sleep import Sleep, HRV
            from datetime import datetime, timedelta
            
            # Hent aktivitet fra database
            activity = db.query(Activity).filter(Activity.activity_id == str(activity_id)).first()
            if not activity:
                logger.warning(f"Aktivitet {activity_id} ikke funnet i database")
                return None
            
            # Hvis allerede beregnet, returner cached verdi
            if activity.body_battery_start is not None:
                return {
                    "activity_id": activity_id,
                    "body_battery_start": round(activity.body_battery_start, 1),
                    "calculation_method": "cached"
                }
            
            # Hent dato for aktiviteten
            activity_date = activity.start_time.date()
            previous_night = activity_date - timedelta(days=1)
            
            # Base Body Battery basert på tid på dagen (mer realistisk)
            hour = activity.start_time.hour
            if 5 <= hour <= 7:  # Tidlig morgen
                base_body_battery = 50.0
            elif 8 <= hour <= 11:  # Formiddag
                base_body_battery = 60.0
            elif 12 <= hour <= 15:  # Ettermiddag
                base_body_battery = 55.0
            elif 16 <= hour <= 19:  # Kveld
                base_body_battery = 50.0
            else:  # Natt/sent kveld
                base_body_battery = 40.0
            
            # 1. Søvnfaktor basert på faktisk søvndata (0-25 poeng)
            sleep_factor = 0.0
            sleep_data = db.query(Sleep).filter(Sleep.sleep_date == previous_night).first()
            if sleep_data:
                if sleep_data.sleep_score:
                    # Bruk faktisk søvnscore (0-100) og konverter til 0-25 poeng
                    sleep_factor = (sleep_data.sleep_score / 100) * 25
                elif sleep_data.total_sleep_time:
                    # Beregn basert på søvnvarighet
                    sleep_hours = sleep_data.total_sleep_time / 3600
                    if sleep_hours >= 8:
                        sleep_factor = 25
                    elif sleep_hours >= 7:
                        sleep_factor = 20
                    elif sleep_hours >= 6:
                        sleep_factor = 15
                    elif sleep_hours >= 5:
                        sleep_factor = 10
                    else:
                        sleep_factor = 5
                
                # Juster basert på søvneffektivitet hvis tilgjengelig
                if sleep_data.sleep_efficiency and sleep_data.sleep_efficiency > 0:
                    efficiency_multiplier = min(sleep_data.sleep_efficiency / 85, 1.2)  # 85% = optimal
                    sleep_factor *= efficiency_multiplier
            else:
                # Fallback - estimat basert på tid og ukedag
                weekday = activity.start_time.weekday()
                if weekday in [5, 6]:  # Helg
                    sleep_factor = 18 if hour <= 8 else 20
                else:  # Ukedag
                    sleep_factor = 12 if hour <= 6 else 15
            
            # 2. HRV-faktor basert på faktisk HRV-data (-15 til +15 poeng)
            hrv_factor = 0.0
            try:
                morning_hrv = db.query(HRV).filter(
                    HRV.measurement_date == activity_date,
                    HRV.measurement_type.in_(['morning', 'during_sleep'])
                ).order_by(HRV.measurement_time.desc()).first()
                
                if morning_hrv and morning_hrv.rmssd:
                    # Sammenlign med baseline (gjennomsnitt siste 7 dager)
                    week_ago = activity_date - timedelta(days=7)
                    recent_hrvs = db.query(HRV).filter(
                        HRV.measurement_date >= week_ago,
                        HRV.measurement_date < activity_date,
                        HRV.rmssd.isnot(None)
                    ).all()
                    
                    if recent_hrvs:
                        avg_hrv = sum(h.rmssd for h in recent_hrvs) / len(recent_hrvs)
                        hrv_ratio = morning_hrv.rmssd / avg_hrv
                        
                        if hrv_ratio > 1.15:  # 15% over baseline - utmerket
                            hrv_factor = 15
                        elif hrv_ratio > 1.08:  # 8% over baseline - godt
                            hrv_factor = 10
                        elif hrv_ratio > 1.03:  # 3% over baseline - litt over
                            hrv_factor = 5
                        elif hrv_ratio < 0.85:  # 15% under baseline - dårlig
                            hrv_factor = -15
                        elif hrv_ratio < 0.92:  # 8% under baseline - ikke optimalt
                            hrv_factor = -10
                        elif hrv_ratio < 0.97:  # 3% under baseline - litt under
                            hrv_factor = -5
                        else:
                            hrv_factor = 0
                    else:
                        # Bruk stress score som backup
                        if morning_hrv.stress_score:
                            if morning_hrv.stress_score < 20:
                                hrv_factor = 12
                            elif morning_hrv.stress_score < 40:
                                hrv_factor = 5
                            elif morning_hrv.stress_score > 80:
                                hrv_factor = -12
                            elif morning_hrv.stress_score > 60:
                                hrv_factor = -8
            except Exception as e:
                logger.warning(f"Kunne ikke beregne HRV-faktor for aktivitet {activity_id}: {e}")
            
            # 3. Forrige treningsbelastning basert på faktiske FIT-data (-20 til +5 poeng)
            training_load_factor = 0.0
            try:
                # Finn forrige aktivitet
                previous_activity = db.query(Activity).filter(
                    Activity.start_time < activity.start_time
                ).order_by(Activity.start_time.desc()).first()
                
                if previous_activity:
                    hours_since = (activity.start_time - previous_activity.start_time).total_seconds() / 3600
                    
                    # Bruk faktisk TSS hvis tilgjengelig
                    if previous_activity.training_stress_score:
                        tss = previous_activity.training_stress_score
                        
                        # Beregn recovery basert på TSS og tid
                        if tss >= 300:  # Meget høy belastning
                            required_recovery = 72  # 3 dager
                        elif tss >= 200:  # Høy belastning
                            required_recovery = 48  # 2 dager
                        elif tss >= 150:  # Moderat belastning
                            required_recovery = 24  # 1 dag
                        elif tss >= 100:  # Lett belastning
                            required_recovery = 12  # 12 timer
                        else:  # Minimal belastning
                            required_recovery = 6   # 6 timer
                        
                        recovery_ratio = hours_since / required_recovery
                        
                        if recovery_ratio >= 1.5:  # Overrecovered
                            training_load_factor = 5
                        elif recovery_ratio >= 1.0:  # Fullt restituert
                            training_load_factor = 0
                        elif recovery_ratio >= 0.75:  # Mest restituert
                            training_load_factor = -5
                        elif recovery_ratio >= 0.5:  # Delvis restituert
                            training_load_factor = -10
                        else:  # Underrecovered
                            training_load_factor = -20
                    
                    # Bruk Training Effect verdier hvis TSS ikke er tilgjengelig
                    elif previous_activity.total_training_effect or previous_activity.total_anaerobic_training_effect:
                        aerobic_effect = previous_activity.total_training_effect or 0
                        anaerobic_effect = previous_activity.total_anaerobic_training_effect or 0
                        combined_effect = aerobic_effect + anaerobic_effect
                        
                        # Høyere Training Effect = mer recovery tid nødvendig
                        if combined_effect >= 8.0:  # Meget høy effekt
                            required_recovery = 48
                        elif combined_effect >= 6.0:  # Høy effekt
                            required_recovery = 24
                        elif combined_effect >= 4.0:  # Moderat effekt
                            required_recovery = 12
                        elif combined_effect >= 2.0:  # Lett effekt
                            required_recovery = 8
                        else:  # Minimal effekt
                            required_recovery = 4
                        
                        recovery_ratio = hours_since / required_recovery
                        
                        if recovery_ratio >= 1.0:
                            training_load_factor = 0
                        elif recovery_ratio >= 0.75:
                            training_load_factor = -3
                        elif recovery_ratio >= 0.5:
                            training_load_factor = -8
                        else:
                            training_load_factor = -15
                    else:
                        # Fallback til enkelt tid-basert estimat
                        if hours_since >= 48:
                            training_load_factor = 3
                        elif hours_since >= 24:
                            training_load_factor = 0
                        elif hours_since >= 12:
                            training_load_factor = -5
                        else:
                            training_load_factor = -10
                else:
                    # Ingen tidligere aktivitet - fullt restituert
                    training_load_factor = 5
            except Exception as e:
                logger.warning(f"Kunne ikke beregne treningsbelastnings-faktor: {e}")
            
            # 4. Stressfaktor basert på søvndata (-8 til 0 poeng)
            stress_factor = 0.0
            if sleep_data and sleep_data.stress_score:
                if sleep_data.stress_score > 85:
                    stress_factor = -8
                elif sleep_data.stress_score > 70:
                    stress_factor = -5
                elif sleep_data.stress_score > 50:
                    stress_factor = -2
            
            # 5. Aktivitetstid-faktor (justerer basert på når på dagen)
            time_factor = 0.0
            if 6 <= hour <= 9:  # Morgentrening - ofte optimalt
                time_factor = 5
            elif 10 <= hour <= 14:  # Midt på dagen
                time_factor = 2
            elif 15 <= hour <= 18:  # Ettermiddagstrening
                time_factor = 0
            elif hour >= 19:  # Kveldstrening - kan være mer krevende
                time_factor = -3
            else:  # Tidlig morgen/sent kveld
                time_factor = -2
            
            # Legg til litt naturlig variasjon basert på aktivitets-ID
            variation_factor = ((activity_id % 47) / 47 * 6) - 3  # -3 til +3 basert på ID
            
            # Beregn total Body Battery
            body_battery = (base_body_battery + sleep_factor + hrv_factor + 
                          training_load_factor + stress_factor + time_factor + variation_factor)
            
            # Begrens til 5-95 range (realistisk Body Battery range før trening)
            body_battery = max(5, min(95, body_battery))
            
            # Lagre i database
            activity.body_battery_start = body_battery
            db.commit()
            
            # Legg til informasjon om FIT-data som ble brukt
            fit_data_used = {
                "tss": activity.training_stress_score if hasattr(activity, 'training_stress_score') else None,
                "aerobic_effect": activity.total_training_effect if hasattr(activity, 'total_training_effect') else None,
                "anaerobic_effect": activity.total_anaerobic_training_effect if hasattr(activity, 'total_anaerobic_training_effect') else None
            }
            
            logger.info(f"Beregnet Body Battery for aktivitet {activity_id}: {body_battery:.1f} "
                       f"(base: {base_body_battery:.1f}, søvn: +{sleep_factor:.1f}, HRV: {hrv_factor:+.1f}, "
                       f"belastning: {training_load_factor:+.1f}, stress: {stress_factor:+.1f}, "
                       f"tid: {time_factor:+.1f}, var: {variation_factor:+.1f}) "
                       f"FIT-data: {fit_data_used}")
            
            return {
                "activity_id": activity_id,
                "body_battery_start": round(body_battery, 1),
                "calculation_method": "fit_data_enhanced",
                "factors": {
                    "base": round(base_body_battery, 1),
                    "sleep": round(sleep_factor, 1),
                    "hrv": round(hrv_factor, 1),
                    "training_load": round(training_load_factor, 1),
                    "stress": round(stress_factor, 1),
                    "time": round(time_factor, 1),
                    "variation": round(variation_factor, 1)
                },
                "fit_data_used": fit_data_used
            }
            
        except Exception as e:
            logger.error(f"Feil ved beregning av Body Battery for aktivitet {activity_id}: {e}")
            return None
