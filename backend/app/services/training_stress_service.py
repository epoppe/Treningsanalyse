import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import logging

from ..database.models.activity import Activity
from ..database.session import get_db
from ..cache.cache_manager import get_cache_manager

logger = logging.getLogger(__name__)

class TrainingStressService:
    """
    Service for å beregne Training Stress Score (TSS) basert på TrainingPeaks-metodikken.
    
    TSS beregnes basert på:
    - Varighet av aktiviteten
    - Intensitet (basert på Training Effect eller estimert fra puls)
    - FTP (Functional Threshold Power) eller LTHR (Lactate Threshold Heart Rate)
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.cache = get_cache_manager()
    
    def calculate_tss_for_activity(self, activity: Activity) -> float:
        """
        Beregn TSS for en enkelt aktivitet basert på EPOC (Exercise Post Oxygen Consumption).
        
        TSS er det samme som EPOC-verdien fra Garmin Connect.
        """
        try:
            # Sjekk cache først
            cached_tss = self.cache.get_tss(str(activity.activity_id))
            if cached_tss is not None:
                logger.debug(f"TSS cache hit for activity {activity.activity_id}")
                return cached_tss
            
            if not activity.duration or activity.duration <= 0:
                return 0.0
            
            # Prioritet 1: Bruk EPOC hvis tilgjengelig
            if activity.epoc and activity.epoc > 0:
                # TSS er det samme som EPOC-verdien fra Garmin
                epoc_value = activity.epoc
                
                logger.debug(f"EPOC-basert TSS for aktivitet {activity.activity_id}: "
                          f"EPOC={epoc_value}")
                tss = round(epoc_value, 1)
                # Cache resultatet
                self.cache.set_tss(str(activity.activity_id), tss)
                return tss  # TSS = EPOC
            
            # Prioritet 2: Fallback til estimert beregning hvis ingen EPOC
            logger.info(f"Ingen EPOC-data for aktivitet {activity.activity_id}, bruker estimert TSS")
            
            # Konverter varighet til timer
            duration_hours = activity.duration / 3600
            
            # Beregn Intensity Factor (IF) basert på tilgjengelige data
            intensity_factor = self._calculate_intensity_factor(activity)
            
            # Estimer FTP (Functional Threshold Power) eller bruk standard
            ftp_equivalent = self._estimate_ftp_equivalent(activity)
            
            # Beregn estimert TSS
            # TSS = timer * IF² * 100
            # Dette gir et fornuftig estimat: 1 time ved IF=1.0 => TSS=100
            tss = duration_hours * intensity_factor * intensity_factor * 100
            
            # Begrens estimert TSS til realistiske verdier
            tss = max(0, min(200, tss))
            
            logger.info(f"Estimert TSS beregnet for aktivitet {activity.activity_id}: {tss:.1f}")
            tss_rounded = round(tss, 1)
            # Cache resultatet
            self.cache.set_tss(str(activity.activity_id), tss_rounded)
            return tss_rounded
            
        except Exception as e:
            logger.error(f"Feil ved beregning av TSS for aktivitet {activity.activity_id}: {e}")
            return 0.0
    
    def _calculate_intensity_factor(self, activity: Activity) -> float:
        """
        Beregn Intensity Factor basert på tilgjengelige data.
        Prioriterer Training Effect, deretter puls-basert estimat.
        """
        # Prioritet 1: Bruk Training Effect hvis tilgjengelig
        if activity.total_training_effect and activity.total_training_effect > 0:
            # Training Effect 1.0-5.0 mappes til IF 0.6-1.2
            te = activity.total_training_effect
            if te <= 1.0:
                return 0.6
            elif te <= 2.0:
                return 0.7 + (te - 1.0) * 0.1  # 0.7-0.8
            elif te <= 3.0:
                return 0.8 + (te - 2.0) * 0.1  # 0.8-0.9
            elif te <= 4.0:
                return 0.9 + (te - 3.0) * 0.15  # 0.9-1.05
            else:  # te > 4.0
                return 1.05 + (te - 4.0) * 0.15  # 1.05-1.2
        
        # Prioritet 2: Bruk puls-basert estimat
        if activity.average_heart_rate and activity.average_heart_rate > 0:
            # Estimer basert på gjennomsnittlig puls
            # Dette er en forenklet tilnærming - i praksis trenger man LTHR
            avg_hr = activity.average_heart_rate
            
            # Estimert LTHR (kan justeres basert på alder/erfaring)
            estimated_lthr = 180  # Standard estimat
            
            # Beregn IF basert på puls
            hr_ratio = avg_hr / estimated_lthr
            
            if hr_ratio < 0.7:
                return 0.6
            elif hr_ratio < 0.8:
                return 0.7
            elif hr_ratio < 0.85:
                return 0.8
            elif hr_ratio < 0.9:
                return 0.9
            elif hr_ratio < 0.95:
                return 1.0
            else:
                return 1.1
        
        # Prioritet 3: Bruk hastighet-basert estimat for løping
        if activity.average_speed and activity.average_speed > 0:
            # For løping, estimer basert på hastighet
            speed_kmh = activity.average_speed * 3.6  # m/s til km/h
            
            # Forenklet hastighet-basert IF (kan justeres)
            if speed_kmh < 8:
                return 0.6
            elif speed_kmh < 10:
                return 0.7
            elif speed_kmh < 12:
                return 0.8
            elif speed_kmh < 14:
                return 0.9
            elif speed_kmh < 16:
                return 1.0
            else:
                return 1.1
        
        # Fallback: Standard IF basert på aktivitetstype
        if activity.activity_type:
            activity_type = activity.activity_type.type_key if hasattr(activity.activity_type, 'type_key') else str(activity.activity_type)
            
            # Standard IF for forskjellige aktivitetstyper
            default_if = {
                'running': 0.8,
                'treadmill_running': 0.8,
                'trail_running': 0.85,
                'cycling': 0.75,
                'indoor_cycling': 0.75,
                'swimming': 0.7,
                'walking': 0.5,
                'hiking': 0.6
            }
            
            return default_if.get(activity_type, 0.7)
        
        # Endelig fallback
        return 0.7
    
    def _estimate_ftp_equivalent(self, activity: Activity) -> float:
        """
        Estimere FTP-ekvivalent for aktiviteten.
        For løping bruker vi VO2max eller standard estimat.
        """
        # For løping, bruk VO2max hvis tilgjengelig
        if activity.vo2_max and activity.vo2_max > 0:
            # Konverter VO2max til FTP-ekvivalent
            # Dette er en forenklet tilnærming
            vo2max = activity.vo2_max
            if vo2max < 40:
                return 200
            elif vo2max < 50:
                return 250
            elif vo2max < 60:
                return 300
            else:
                return 350
        
        # Standard FTP-ekvivalent basert på aktivitetstype
        if activity.activity_type:
            activity_type = activity.activity_type.type_key if hasattr(activity.activity_type, 'type_key') else str(activity.activity_type)
            
            default_ftp = {
                'running': 300,
                'treadmill_running': 300,
                'trail_running': 320,
                'cycling': 250,
                'indoor_cycling': 250,
                'swimming': 200,
                'walking': 150,
                'hiking': 180
            }
            
            return default_ftp.get(activity_type, 250)
        
        return 250  # Standard fallback
    
    def calculate_training_load_metrics(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """
        Beregn CTL, ATL og Form for en periode.
        
        CTL = Chronic Training Load (42-dagers EMA)
        ATL = Acute Training Load (7-dagers EMA)
        Form = CTL - ATL
        """
        try:
            logger.info(f"Starter beregning av Training Load metrics fra {start_date} til {end_date}")
            
            # Hent aktiviteter for perioden
            activities = self.db.query(Activity).filter(
                and_(
                    func.date(Activity.start_time) >= start_date,
                    func.date(Activity.start_time) <= end_date
                )
            ).order_by(Activity.start_time).all()
            
            logger.info(f"Fant {len(activities)} aktiviteter for perioden")
            
            if not activities:
                return {
                    "message": "Ingen aktiviteter funnet for perioden",
                    "data": None
                }
            
            # Beregn TSS for hver aktivitet
            tss_data = []
            for activity in activities:
                try:
                    tss = self.calculate_tss_for_activity(activity)
                    if tss > 0:
                        tss_data.append({
                            'date': activity.start_time.date(),
                            'tss': tss,
                            'activity_id': activity.activity_id,
                            'activity_name': activity.activity_name,
                            'duration': activity.duration,
                            'distance': activity.distance
                        })
                except Exception as e:
                    logger.warning(f"Kunne ikke beregne TSS for aktivitet {activity.activity_id}: {e}")
                    continue
            
            logger.info(f"Beregnet TSS for {len(tss_data)} aktiviteter")
            
            if not tss_data:
                return {
                    "message": "Ingen aktiviteter med TSS > 0",
                    "data": None
                }
            
            # Opprett DataFrame for beregninger
            df = pd.DataFrame(tss_data)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            # Grupper etter dato og summer TSS
            daily_tss = df.groupby(df.index.date)['tss'].sum().reset_index()
            daily_tss['date'] = pd.to_datetime(daily_tss['date'])
            daily_tss.set_index('date', inplace=True)
            
            # Fyll manglende dager med 0 TSS
            date_range = pd.date_range(start=start_date, end=end_date, freq='D')
            daily_tss = daily_tss.reindex(date_range, fill_value=0)
            
            logger.info(f"Beregner CTL, ATL og Form for {len(daily_tss)} dager")
            
            # Beregn CTL, ATL og Form
            daily_tss['CTL'] = daily_tss['tss'].ewm(span=42, adjust=False).mean()
            daily_tss['ATL'] = daily_tss['tss'].ewm(span=7, adjust=False).mean()
            daily_tss['Form'] = daily_tss['CTL'] - daily_tss['ATL']
            
            # Konverter til dictionary for JSON-respons
            result_data = []
            for date, row in daily_tss.iterrows():
                result_data.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'tss': round(row['tss'], 1),
                    'ctl': round(row['CTL'], 1),
                    'atl': round(row['ATL'], 1),
                    'form': round(row['Form'], 1)
                })
            
            # Beregn sammendrag
            latest_data = daily_tss.iloc[-1]
            summary = {
                'current_ctl': round(latest_data['CTL'], 1),
                'current_atl': round(latest_data['ATL'], 1),
                'current_form': round(latest_data['Form'], 1),
                'total_tss_period': round(daily_tss['tss'].sum(), 1),
                'avg_daily_tss': round(daily_tss['tss'].mean(), 1),
                'max_daily_tss': round(daily_tss['tss'].max(), 1),
                'days_with_activity': len(daily_tss[daily_tss['tss'] > 0]),
                'total_days': len(daily_tss)
            }
            
            logger.info(f"Training Load metrics beregnet: CTL={summary['current_ctl']}, ATL={summary['current_atl']}, Form={summary['current_form']}")
            
            return {
                "message": "Training Load metrics beregnet",
                "data": {
                    "daily_data": result_data,
                    "summary": summary,
                    "activities": tss_data
                }
            }
            
        except Exception as e:
            logger.error(f"Feil ved beregning av Training Load metrics: {e}", exc_info=True)
            return {
                "message": f"Feil ved beregning: {str(e)}",
                "data": None
            }
    
    def calculate_training_load_metrics_simple(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """
        Enkel versjon av calculate_training_load_metrics uten pandas.
        """
        try:
            logger.info(f"Starter enkel beregning av Training Load metrics fra {start_date} til {end_date}")
            
            # Hent aktiviteter for perioden
            activities = self.db.query(Activity).filter(
                and_(
                    func.date(Activity.start_time) >= start_date,
                    func.date(Activity.start_time) <= end_date
                )
            ).order_by(Activity.start_time).all()
            
            logger.info(f"Fant {len(activities)} aktiviteter for perioden")
            
            if not activities:
                return {
                    "message": "Ingen aktiviteter funnet for perioden",
                    "data": None
                }
            
            # Bruk lagret TSS fra database i stedet for å beregne på nytt
            tss_data = []
            for activity in activities:
                try:
                    # Prioritet 1: Bruk lagret TSS fra database
                    if activity.training_stress_score and activity.training_stress_score > 0:
                        tss_data.append({
                            'date': activity.start_time.date(),
                            'tss': round(activity.training_stress_score, 1),
                            'activity_id': activity.activity_id,
                            'activity_name': activity.activity_name,
                            'duration': activity.duration,
                            'distance': activity.distance,
                            'calculation_method': 'database'
                        })
                        logger.debug(f"Bruker lagret TSS for aktivitet {activity.activity_id}: {activity.training_stress_score}")
                        
                    # Prioritet 2: Beregn TSS hvis ikke lagret
                    elif activity.duration and activity.duration > 0:
                        # Beregn TSS med riktig metode
                        calculated_tss = self.calculate_tss_for_activity(activity)
                        if calculated_tss > 0:
                            tss_data.append({
                                'date': activity.start_time.date(),
                                'tss': round(calculated_tss, 1),
                                'activity_id': activity.activity_id,
                                'activity_name': activity.activity_name,
                                'duration': activity.duration,
                                'distance': activity.distance,
                                'calculation_method': 'calculated'
                            })
                            logger.info(f"Beregnet TSS for aktivitet {activity.activity_id}: {calculated_tss}")
                        
                except Exception as e:
                    logger.warning(f"Kunne ikke hente/beregne TSS for aktivitet {activity.activity_id}: {e}")
                    continue
            
            logger.info(f"Beregnet TSS for {len(tss_data)} aktiviteter")
            
            if not tss_data:
                return {
                    "message": "Ingen aktiviteter med TSS > 0",
                    "data": None
                }
            
            # Grupper TSS etter dato
            daily_tss = {}
            for item in tss_data:
                date_str = item['date'].isoformat()
                if date_str not in daily_tss:
                    daily_tss[date_str] = 0
                daily_tss[date_str] += item['tss']
            
            # Generer alle datoer i perioden
            all_dates = []
            current_date = start_date
            while current_date <= end_date:
                all_dates.append(current_date)
                current_date += timedelta(days=1)
            
            # Beregn EMA for CTL og ATL for hver dag
            ctl_values = {}
            atl_values = {}
            
            # EMA-parametere
            ctl_span = 42  # 42-dagers EMA for CTL
            atl_span = 7   # 7-dagers EMA for ATL
            
            # Beregn EMA-koeffisienter
            ctl_alpha = 2.0 / (ctl_span + 1)
            atl_alpha = 2.0 / (atl_span + 1)
            
            # Initialiser EMA-verdier
            current_ctl = 0
            current_atl = 0
            
            for date_obj in all_dates:
                date_str = date_obj.isoformat()
                daily_tss_value = daily_tss.get(date_str, 0)
                
                # Oppdater EMA-verdier
                if current_ctl == 0 and daily_tss_value > 0:
                    # Første dag med aktivitet - sett initial verdi
                    current_ctl = daily_tss_value
                    current_atl = daily_tss_value
                elif current_ctl > 0:
                    # Oppdater EMA
                    current_ctl = (ctl_alpha * daily_tss_value) + ((1 - ctl_alpha) * current_ctl)
                    current_atl = (atl_alpha * daily_tss_value) + ((1 - atl_alpha) * current_atl)
                
                ctl_values[date_str] = round(current_ctl, 1)
                atl_values[date_str] = round(current_atl, 1)
            
            # Konverter til liste med alle verdier
            daily_data = []
            for date_obj in all_dates:
                date_str = date_obj.isoformat()
                daily_tss_value = daily_tss.get(date_str, 0)
                ctl_value = ctl_values.get(date_str, 0)
                atl_value = atl_values.get(date_str, 0)
                form_value = ctl_value - atl_value
                
                daily_data.append({
                    'date': date_str,
                    'tss': round(daily_tss_value, 1),
                    'ctl': ctl_value,
                    'atl': atl_value,
                    'form': round(form_value, 1)
                })
            
            # Sammendrag basert på siste dag
            last_date = all_dates[-1].isoformat()
            final_ctl = ctl_values.get(last_date, 0)
            final_atl = atl_values.get(last_date, 0)
            final_form = final_ctl - final_atl
            
            total_tss = sum(daily_tss.values())
            avg_tss = total_tss / len(daily_tss) if daily_tss else 0
            max_tss = max(daily_tss.values()) if daily_tss else 0
            
            summary = {
                'current_ctl': round(final_ctl, 1),
                'current_atl': round(final_atl, 1),
                'current_form': round(final_form, 1),
                'total_tss_period': round(total_tss, 1),
                'avg_daily_tss': round(avg_tss, 1),
                'max_daily_tss': round(max_tss, 1),
                'days_with_activity': len(daily_tss),
                'total_days': len(all_dates)
            }
            
            logger.info(f"Training Load metrics beregnet: CTL={summary['current_ctl']}, ATL={summary['current_atl']}, Form={summary['current_form']}")
            
            return {
                "message": "Training Load metrics beregnet",
                "data": {
                    "daily_data": daily_data,
                    "summary": summary,
                    "activities": tss_data
                }
            }
            
        except Exception as e:
            logger.error(f"Feil ved beregning av Training Load metrics: {e}", exc_info=True)
            return {
                "message": f"Feil ved beregning: {str(e)}",
                "data": None
            }
    
    def get_training_load_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        Hent sammendrag av Training Load for siste N dager.
        """
        try:
            end_date = date.today()
            start_date = end_date - timedelta(days=days)
            
            logger.info(f"Beregner Training Load summary for {days} dager fra {start_date} til {end_date}")
            
            # Bruk den oppdaterte calculate_training_load_metrics_simple metoden
            result = self.calculate_training_load_metrics_simple(start_date, end_date)
            
            if result["data"] is None:
                return {
                    "message": "Test respons",
                    "data": {
                        "daily_data": [],
                        "summary": {
                            "current_ctl": 0,
                            "current_atl": 0,
                            "current_form": 0,
                            "total_tss_period": 0,
                            "avg_daily_tss": 0,
                            "max_daily_tss": 0,
                            "days_with_activity": 0,
                            "total_days": days
                        }
                    }
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Feil ved beregning av Training Load summary: {e}", exc_info=True)
            return {
                "message": f"Feil ved beregning: {str(e)}",
                "data": None
            } 