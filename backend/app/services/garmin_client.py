import asyncio
import logging
import traceback
import uuid
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any, Dict, List, Optional

import garth
from garth.exc import GarthException, GarthHTTPError
from pydantic import BaseModel

from app.config import settings

# Sett opp logging tidlig så den er tilgjengelig
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prøv å importere garth's HRV-, Body Battery- og Stress-klasser hvis tilgjengelige
try:
    DailyHRV = getattr(garth, 'DailyHRV', None)
    HRVData = getattr(garth, 'HRVData', None)
    DailyBodyBatteryStress = getattr(garth, 'DailyBodyBatteryStress', None)
    BodyBatteryDetail = getattr(garth, 'BodyBatteryData', None)
    DailyStress = getattr(garth, 'DailyStress', None)
    WeeklyStress = getattr(garth, 'WeeklyStress', None)
except ImportError as e:
    DailyHRV = None
    HRVData = None
    DailyBodyBatteryStress = None
    BodyBatteryDetail = None
    DailyStress = None
    WeeklyStress = None
    logger.warning(f"Kunne ikke importere HRV-klasser fra garth: {e} - bruker kun API-kall")

# Pydantic-modeller for HRV-data
class HrvSummary(BaseModel):
    last_night_avg: Optional[int] = None
    last_night_5_min_high: Optional[int] = None
    weekly_avg: Optional[int] = None
    status: Optional[str] = None
    baseline_low_upper: Optional[int] = None
    baseline_balanced_lower: Optional[int] = None
    baseline_balanced_upper: Optional[int] = None

class HRVData(BaseModel):
    hrv_summary: Optional[HrvSummary] = None


# Oppdatert User-Agent for kompatibilitet med nyere Garmin API
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"

# Patcher garth for å bruke oppdatert User-Agent
def patch_garth():
    """Applierer patch til garth-biblioteket for å bruke en nyere User-Agent."""
    garth.client.USER_AGENT = USER_AGENT

patch_garth()


def _merge_garmin_daily_and_sleep_detail(
    daily: Optional[Dict[str, Any]],
    detail: Optional[Dict[str, Any]],
    date_str: str,
) -> Optional[Dict[str, Any]]:
    """Kombinerer DailySleep (typisk overall_score) med SleepData (søvnstadier)."""
    if not daily and not detail:
        return None
    keys = (
        "sleep_time",
        "sleep_goal",
        "sleep_score",
        "overall_score",
        "deep_sleep",
        "light_sleep",
        "rem_sleep",
        "awake_time",
        "total_sleep",
    )
    merged: Dict[str, Any] = {"date": date_str}
    for k in keys:
        d_val = daily.get(k) if daily else None
        s_val = detail.get(k) if detail else None
        merged[k] = s_val if s_val is not None else d_val
    if merged.get("total_sleep") is None:
        deep = merged.get("deep_sleep")
        light = merged.get("light_sleep")
        rem = merged.get("rem_sleep")
        if any(x is not None for x in (deep, light, rem)):
            merged["total_sleep"] = (deep or 0) + (light or 0) + (rem or 0)
    if any(v is not None for k, v in merged.items() if k != "date"):
        return merged
    return None


class GarminClient:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(GarminClient, cls).__new__(cls)
        return cls._instance

    def __init__(self, email: str, password: str, token_dir: str):
        self.email = email
        self.password = password
        self.token_dir = Path(token_dir)
        self.client_id = str(uuid.uuid4())
        self._initialized = False
        logger.info(f"GarminClient instance {self.client_id} __init__. Token directory: {self.token_dir}. Patches ensured.")
        
    async def initialize(self):
        """Initialiserer Garmin-klienten.
        
        Prøver først å gjenopprette en eksisterende sesjon. Hvis det feiler,
        utfører en ny pålogging og lagrer sesjonsinformasjonen.
        """
        logger.info(f"GarminClient instance {self.client_id} initialize. Initialiserer Garmin Client for {self.email}...")
        try:
            # Prøv først å gjenopprette eksisterende sesjon
            await asyncio.to_thread(garth.resume, str(self.token_dir))
            logger.info("Vellykket gjenoppretting av eksisterende Garmin-sesjon.")
            
            # Test at sesjonen fungerer
            try:
                await asyncio.to_thread(lambda: garth.client.username)
                logger.info("Sesjon bekreftet som gyldig.")
                self._initialized = True
                return True
            except GarthException:
                logger.info("Eksisterende sesjon er utløpt, utfører ny pålogging...")
                raise  # Trigger ny pålogging nedenfor
                
        except (GarthException, FileNotFoundError, Exception) as e:
            logger.info(f"Kunne ikke gjenopprette sesjon ({e}), utfører ny pålogging...")
            try:
                # Utfør ny pålogging
                await asyncio.to_thread(garth.login, self.email, self.password)
                # Lagre sesjonsinformasjon for fremtidig bruk
                await asyncio.to_thread(garth.save, str(self.token_dir))
                logger.info("Vellykket ny pålogging og lagring av sesjon.")
                self._initialized = True
                return True
            except GarthException as login_error:
                logger.error(f"Pålogging feilet: {login_error}")
                self._initialized = False
                return False

    def is_authenticated(self) -> bool:
        """Sjekker om en token-fil finnes i katalogen uten å gjøre et nettverkskall."""
        if not self.token_dir.exists():
            return False
        # Sjekker om det finnes noen .json-filer i token-katalogen
        for _ in self.token_dir.glob("*.json"):
            return True
        return False

    async def get_activities(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Henter aktiviteter for en gitt periode."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente aktiviteter.")
            return []
        
        try:
            # Konverter datoer til strenger som Garmin API forventer
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            
            logger.info(f"Henter aktiviteter fra Garmin API: {start_str} til {end_str}")
            
            # Hent aktiviteter fra Garmin Connect API
            activities = await asyncio.to_thread(
                garth.connectapi, 
                f"/activitylist-service/activities/search/activities?startDate={start_str}&endDate={end_str}"
            )
            
            if isinstance(activities, list):
                logger.info(f"Hentet {len(activities)} aktiviteter fra Garmin")
                return activities
            else:
                logger.warning("Uventet respons fra Garmin API - ikke en liste")
                return []
                
        except GarthHTTPError as e:
            logger.error(f"HTTP-feil ved henting av aktiviteter: {e}")
            return []
        except Exception as e:
            logger.error(f"Feil ved henting av aktiviteter: {e}")
            logger.error(traceback.format_exc())
            return []

    async def get_activity_details(self, activity_id: str) -> Optional[bytes]:
        """Henter detaljerte data (FIT-fil) for en aktivitet."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente aktivitetsdetaljer.")
            return None
        
        try:
            logger.info(f"Henter detaljer for aktivitet {activity_id}")
            
            # Hent FIT-fil fra Garmin Connect API
            fit_data = await asyncio.to_thread(
                garth.download, 
                f"/download-service/files/activity/{activity_id}"
            )
            
            if isinstance(fit_data, bytes):
                logger.info(f"Hentet FIT-data for aktivitet {activity_id} ({len(fit_data)} bytes)")
                return fit_data
            else:
                logger.warning(f"Uventet respons ved henting av FIT-data for aktivitet {activity_id}")
                return None
                
        except GarthHTTPError as e:
            # Sjekk om det er en 404-feil (ingen data funnet)
            if "404" in str(e) or "not found" in str(e).lower():
                logger.info(f"Ingen FIT-data funnet for aktivitet {activity_id}")
                return None
            logger.error(f"HTTP-feil ved henting av FIT-data for aktivitet {activity_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Feil ved henting av FIT-data for aktivitet {activity_id}: {e}")
            logger.error(traceback.format_exc())
            return None

    async def get_hrv_data_alternative(self, date: datetime) -> Optional[Dict[str, Any]]:
        """Alternativ implementasjon som bruker garth's innebygde HRV-funksjonalitet."""
        if not self.is_authenticated():
            logger.error("Ikke autentiseret. Kan ikke hente HRV-data.")
            return None
        
        date_obj = date.date()
        date_str = date.strftime("%Y-%m-%d")
        logger.info(f"Henter HRV-data (alternativ metode) for {date_str}")
        
        # Debugging: List alle garth-attributter og metoder
        garth_attrs = [attr for attr in dir(garth) if 'HRV' in attr or 'hrv' in attr]
        logger.info(f"Garth HRV-relaterte attributter: {garth_attrs}")
        logger.info(f"Garth HRV klasser tilgjengelig: DailyHRV={DailyHRV is not None}, HRVData={HRVData is not None}")
        
        if DailyHRV:
            logger.info(f"DailyHRV metoder: {[m for m in dir(DailyHRV) if not m.startswith('_')]}")
        if HRVData:
            logger.info(f"HRVData metoder: {[m for m in dir(HRVData) if not m.startswith('_')]}")
        
        # Prøv flere garth-metoder i prioritert rekkefølge
        methods_to_try = []
        
        if DailyHRV is not None and hasattr(DailyHRV, 'list'):
            methods_to_try.append(("DailyHRV.list", lambda: DailyHRV.list(date_str, 1)))
        
        if HRVData is not None and hasattr(HRVData, 'get'):
            methods_to_try.append(("HRVData.get", lambda: HRVData.get(date_str)))
            
        if HRVData is not None and hasattr(HRVData, 'list'):
            methods_to_try.append(("HRVData.list", lambda: HRVData.list(date_str, 1)))
        
        # Prøv også direct garth calls
        methods_to_try.append(("garth.DailyHRV.list", lambda: garth.DailyHRV.list(date_str, 1)))
        
        for method_name, method_func in methods_to_try:
            try:
                logger.info(f"Prøver {method_name} for {date_str}")
                hrv_data = await asyncio.to_thread(method_func)
                
                if hrv_data:
                    logger.info(f"HRV-data funnet med {method_name} for {date_str}: {hrv_data}")
                    
                    # Håndter ulike returformater
                    if isinstance(hrv_data, list) and len(hrv_data) > 0:
                        # DailyHRV.list returnerer liste
                        hrv_item = hrv_data[0]
                        if hasattr(hrv_item, 'last_night_avg'):
                            # Prøv å hente baseline-verdier på ulike måter
                            baseline_low_upper = None
                            baseline_balanced_lower = None
                            baseline_balanced_upper = None
                            
                            # Prøv direkte attributter
                            if hasattr(hrv_item, 'baseline_balanced_lower'):
                                baseline_balanced_lower = hrv_item.baseline_balanced_lower
                            elif hasattr(hrv_item, 'balanced_low'):
                                baseline_balanced_lower = hrv_item.balanced_low
                            
                            if hasattr(hrv_item, 'baseline_balanced_upper'):
                                baseline_balanced_upper = hrv_item.baseline_balanced_upper
                            elif hasattr(hrv_item, 'balanced_upper'):
                                baseline_balanced_upper = hrv_item.balanced_upper
                            
                            if hasattr(hrv_item, 'baseline_low_upper'):
                                baseline_low_upper = hrv_item.baseline_low_upper
                            
                            # Prøv gjennom baseline-objekt hvis det eksisterer
                            if hasattr(hrv_item, 'baseline') and hrv_item.baseline:
                                if baseline_balanced_lower is None:
                                    baseline_balanced_lower = getattr(hrv_item.baseline, 'balanced_lower', None) or getattr(hrv_item.baseline, 'balanced_low', None)
                                if baseline_balanced_upper is None:
                                    baseline_balanced_upper = getattr(hrv_item.baseline, 'balanced_upper', None)
                                if baseline_low_upper is None:
                                    baseline_low_upper = getattr(hrv_item.baseline, 'low_upper', None)
                            
                            logger.info(f"HRV baseline-verdier for {date_str}: lower={baseline_balanced_lower}, upper={baseline_balanced_upper}")
                            
                            hrv_dict = {
                                "hrv_summary": {
                                    "last_night_avg": hrv_item.last_night_avg,
                                    "last_night_5_min_high": getattr(hrv_item, 'last_night_5_min_high', None),
                                    "weekly_avg": getattr(hrv_item, 'weekly_avg', None),
                                    "status": getattr(hrv_item, 'status', None),
                                    "baseline_low_upper": baseline_low_upper,
                                    "baseline_balanced_lower": baseline_balanced_lower,
                                    "baseline_balanced_upper": baseline_balanced_upper,
                                }
                            }
                            return hrv_dict
                    elif hasattr(hrv_data, 'hrv_summary'):
                        # HRVData.get returnerer objekt med hrv_summary
                        hrv_summary = hrv_data.hrv_summary
                        
                        # Prøv å hente baseline-verdier på ulike måter
                        baseline_low_upper = None
                        baseline_balanced_lower = None
                        baseline_balanced_upper = None
                        
                        if hrv_summary:
                            if hasattr(hrv_summary, 'baseline') and hrv_summary.baseline:
                                baseline_obj = hrv_summary.baseline
                                baseline_low_upper = getattr(baseline_obj, 'low_upper', None)
                                baseline_balanced_lower = getattr(baseline_obj, 'balanced_lower', None) or getattr(baseline_obj, 'balanced_low', None)
                                baseline_balanced_upper = getattr(baseline_obj, 'balanced_upper', None)
                            
                            # Prøv direkte på hrv_summary hvis baseline-objekt ikke fungerte
                            if baseline_balanced_lower is None:
                                baseline_balanced_lower = getattr(hrv_summary, 'baseline_balanced_lower', None) or getattr(hrv_summary, 'balanced_low', None)
                            if baseline_balanced_upper is None:
                                baseline_balanced_upper = getattr(hrv_summary, 'baseline_balanced_upper', None) or getattr(hrv_summary, 'balanced_upper', None)
                            if baseline_low_upper is None:
                                baseline_low_upper = getattr(hrv_summary, 'baseline_low_upper', None)
                            
                            logger.info(f"HRV baseline-verdier (hrv_summary) for {date_str}: lower={baseline_balanced_lower}, upper={baseline_balanced_upper}")
                        
                        hrv_dict = {
                            "hrv_summary": {
                                "last_night_avg": hrv_summary.last_night_avg if hrv_summary else None,
                                "last_night_5_min_high": hrv_summary.last_night_5_min_high if hrv_summary else None,
                                "weekly_avg": hrv_summary.weekly_avg if hrv_summary else None,
                                "status": hrv_summary.status if hrv_summary else None,
                                "baseline_low_upper": baseline_low_upper,
                                "baseline_balanced_lower": baseline_balanced_lower,
                                "baseline_balanced_upper": baseline_balanced_upper,
                            }
                        }
                        return hrv_dict
                        
                logger.info(f"{method_name} returnerte data men i ukjent format for {date_str}")
                        
            except Exception as e:
                logger.debug(f"{method_name} feilet for {date_str}: {e}")
                continue
        
        logger.info(f"Ingen av garth-metodene fant HRV-data for {date_str}, faller tilbake til API-kall")
        return await self.get_hrv_data(date)

    async def get_hrv_data(self, date: datetime) -> Optional[Dict[str, Any]]:
        """Henter HRV-data for en spesifikk dato."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente HRV-data.")
            return None
        try:
            date_str = date.strftime("%Y-%m-%d")
            logger.info(f"Henter HRV-data for {date_str}")
            
            # Prøv først standard API-endepunkt
            try:
                hrv_data = await asyncio.to_thread(
                    garth.connectapi, f"/hrv-service/hrv/daily/{date_str}"
                )
            except GarthHTTPError as api_error:
                logger.info(f"Standard HRV API feilet for {date_str}, prøver alternative endepunkter: {api_error}")
                hrv_data = None
                
                # Prøv flere alternative API-endepunkter
                alternative_endpoints = [
                    # Prøv DailyHRV endpoint som garth bruker
                    (f"/usersummary-service/stats/hrv/daily/{date_str}", {}),
                    # Prøv wellness endpoint
                    (f"/usersummary-service/usersummary/daily/{garth.client.username}", {"calendarDate": date_str}),
                    # Prøv direkte wellness HRV endpoint
                    (f"/wellness-service/wellness/dailyHRV/{garth.client.username}", {"date": date_str}),
                ]
                
                for endpoint, params in alternative_endpoints:
                    try:
                        logger.info(f"Prøver alternativt endepunkt: {endpoint} med params: {params}")
                        alt_data = await asyncio.to_thread(
                            garth.connectapi, endpoint, params=params
                        )
                        logger.debug(f"Alternativt endepunkt {endpoint} returnerte: {alt_data}")
                        
                        if alt_data:
                            # Prøv å trekke ut HRV-data fra ulike responsformater
                            if 'allMetrics' in alt_data:
                                # Format fra usersummary endpoint
                                hrv_metrics = alt_data.get('allMetrics', {}).get('metricsMap', {}).get('WELLNESS_HRV_RMSSD', {})
                                if hrv_metrics and hrv_metrics.get('value'):
                                    hrv_data = {
                                        "hrv_summary": {
                                            "last_night_avg": hrv_metrics.get('value'),
                                            "last_night_5_min_high": None,
                                            "weekly_avg": None,
                                            "status": None,
                                            "baseline_low_upper": None,
                                            "baseline_balanced_lower": None,
                                            "baseline_balanced_upper": None,
                                        }
                                    }
                                    logger.info(f"Hentet HRV-data fra usersummary endpoint for {date_str}: {hrv_data}")
                                    break
                            elif 'hrvSummary' in alt_data:
                                # Format fra wellness endpoint
                                hrv_data = {"hrv_summary": alt_data['hrvSummary']}
                                logger.info(f"Hentet HRV-data fra wellness endpoint for {date_str}: {hrv_data}")
                                break
                            elif isinstance(alt_data, dict) and any(key in alt_data for key in ['last_night_avg', 'weekly_avg']):
                                # Direkte HRV format
                                hrv_data = {"hrv_summary": alt_data}
                                logger.info(f"Hentet HRV-data i direkte format for {date_str}: {hrv_data}")
                                break
                                
                    except Exception as alt_error:
                        logger.debug(f"Alternativt endepunkt {endpoint} feilet: {alt_error}")
                        continue
                
                if not hrv_data:
                    logger.info(f"Ingen HRV-data funnet i noen av de alternative endepunktene for {date_str}")
                    return None
            
            # Logg rå data for debugging
            logger.debug(f"Rå HRV-data for {date_str}: {hrv_data}")
            
            # Sjekk om data er tomt eller None
            if not hrv_data:
                logger.info(f"Tomt HRV-data-svar for {date_str}")
                return None
            
            # Validerer data med Pydantic-modellen
            validated_data = HRVData.model_validate(hrv_data)
            logger.info(f"Validerte HRV-data for {date_str}: {validated_data.model_dump()}")
            return validated_data.model_dump()
        except GarthHTTPError as e:
            # Denne catch-blokken håndterer bare feil som ikke ble håndtert i try-blokken over
            logger.info(f"GarthHTTPError ved henting av HRV-data for {date_str}: {e}")
            # Sjekk om det er en 404-feil (ingen data funnet)
            if "404" in str(e) or "not found" in str(e).lower():
                logger.info(f"Ingen HRV-data funnet for {date_str} (404 Not Found)")
                return None
            logger.error(f"HTTP-feil ved henting av HRV-data for {date_str}: {e}")
            return None
        except Exception as e:
            logger.error(f"En uventet feil oppstod under henting av HRV-data for {date_str}: {e}")
            logger.error(traceback.format_exc())
            return None

    async def get_activity_epoc_data(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """Henter EPOC (Exercise Post Oxygen Consumption) data for en aktivitet."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente EPOC-data.")
            return None
        
        try:
            logger.info(f"Henter EPOC data for aktivitet {activity_id}")
            
            # Hent detaljerte aktivitetsdata fra activity-service
            activity_data = await asyncio.to_thread(
                garth.connectapi, 
                f"/activity-service/activity/{activity_id}"
            )
            
            if isinstance(activity_data, dict) and 'summaryDTO' in activity_data:
                summary = activity_data['summaryDTO']
                
                epoc_data = {
                    "activity_training_load": summary.get('activityTrainingLoad'),  # Dette er EPOC
                    "training_effect": summary.get('trainingEffect'),
                    "aerobic_training_effect": summary.get('aerobicTrainingEffect'),
                    "anaerobic_training_effect": summary.get('anaerobicTrainingEffect'),
                    "training_effect_label": summary.get('trainingEffectLabel'),
                    "aerobic_te_message": summary.get('aerobicTrainingEffectMessage'),
                    "anaerobic_te_message": summary.get('anaerobicTrainingEffectMessage'),
                    "elevation_gain": summary.get('elevationGain') or summary.get('totalElevationGain'),
                    "elevation_loss": summary.get('elevationLoss') or summary.get('totalElevationLoss')
                }
                
                logger.info(f"Hentet EPOC data for aktivitet {activity_id}: "
                           f"Training Load={epoc_data['activity_training_load']}, "
                           f"Elevation Gain={epoc_data['elevation_gain']}")
                
                return epoc_data
            else:
                logger.warning(f"Uventet respons fra activity-service for aktivitet {activity_id}")
                return None
                
        except GarthHTTPError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.info(f"Ingen EPOC data funnet for aktivitet {activity_id}")
                return None
            logger.error(f"HTTP-feil ved henting av EPOC data for aktivitet {activity_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Feil ved henting av EPOC data for aktivitet {activity_id}: {e}")
            logger.error(traceback.format_exc())
            return None

    async def get_activity_training_effect(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """Henter Training Effect data for en spesifikk aktivitet fra activity-service."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente Training Effect data.")
            return None
        
        try:
            logger.info(f"Henter Training Effect data for aktivitet {activity_id}")
            
            # Hent detaljerte aktivitetsdata fra activity-service
            activity_data = await asyncio.to_thread(
                garth.connectapi, 
                f"/activity-service/activity/{activity_id}"
            )
            
            if isinstance(activity_data, dict) and 'summaryDTO' in activity_data:
                summary = activity_data['summaryDTO']
                
                training_effect_data = {
                    # Garmin: 'aerobicTrainingEffect' er aerob TE; 'trainingEffect' er total/combined
                    "aerobic_training_effect": summary.get('aerobicTrainingEffect') or summary.get('trainingEffect'),
                    "anaerobic_training_effect": summary.get('anaerobicTrainingEffect'),
                    "aerobic_te_message": summary.get('aerobicTrainingEffectMessage'),
                    "anaerobic_te_message": summary.get('anaerobicTrainingEffectMessage'),
                    "training_effect_label": summary.get('trainingEffectLabel'),
                    "training_load": summary.get('activityTrainingLoad')
                }
                
                logger.info(f"Hentet Training Effect for aktivitet {activity_id}: "
                           f"Aerobic={training_effect_data['aerobic_training_effect']}, "
                           f"Anaerobic={training_effect_data['anaerobic_training_effect']}")
                
                return training_effect_data
            else:
                logger.warning(f"Uventet respons fra activity-service for aktivitet {activity_id}")
                return None
                
        except GarthHTTPError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.info(f"Ingen detaljerte data funnet for aktivitet {activity_id}")
                return None
            logger.error(f"HTTP-feil ved henting av Training Effect for aktivitet {activity_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Feil ved henting av Training Effect for aktivitet {activity_id}: {e}")
            logger.error(traceback.format_exc())
            return None

    # Nye metoder basert på Garmy metrics

    async def get_training_status(self) -> Optional[Dict[str, Any]]:
        """Henter treningstatus fra Garmin Connect."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente treningstatus.")
            return None
        
        try:
            logger.info("Henter treningstatus...")
            
            # Hent treningsstatistikk fra Garmin API
            stats_data = await asyncio.to_thread(
                garth.connectapi,
                "/userstats-service/stats"
            )
            
            logger.info(f"Stats data type: {type(stats_data)}")
            logger.info(f"Stats data keys (if dict): {list(stats_data.keys())[:10] if isinstance(stats_data, dict) else 'Not a dict'}")
            
            if isinstance(stats_data, dict):
                logger.info(f"Hentet treningstatus-data med {len(stats_data)} nøkler")
                return stats_data
            else:
                logger.warning(f"Uventet data-type: {type(stats_data)}")
                return None
                
        except GarthHTTPError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.info("Ingen treningstatus-data funnet (404)")
                return None
            else:
                logger.error(f"HTTP-feil ved henting av treningstatus: {e}")
                return None
        except Exception as e:
            logger.error(f"Feil ved henting av treningstatus: {e}", exc_info=True)
            return None

    async def get_body_battery_data(self, date) -> Optional[Dict[str, Any]]:
        """Henter body battery data for en spesifikk dato."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente body battery data.")
            return None

        try:
            if hasattr(date, 'date'):
                date_str = date.date().strftime("%Y-%m-%d")
            else:
                date_str = date.strftime("%Y-%m-%d")
            logger.info(f"Henter body battery data for {date_str}")

            # 0) Prøv garth-objekter hvis tilgjengelig (gir ofte mest stabile svar)
            if DailyBodyBatteryStress is not None:
                try:
                    bb_obj = await asyncio.to_thread(DailyBodyBatteryStress.get, date_str)
                    # Forsøk å konvertere til dictionary
                    if bb_obj is None:
                        logger.debug("DailyBodyBatteryStress.get returnerte None")
                    else:
                        if hasattr(bb_obj, 'to_dict'):
                            bb_data = bb_obj.to_dict()
                        elif hasattr(bb_obj, 'dict'):
                            bb_data = bb_obj.dict()
                        elif isinstance(bb_obj, dict):
                            bb_data = bb_obj
                        else:
                            # Best-effort: hent __dict__
                            bb_data = getattr(bb_obj, '__dict__', {})

                        # Ekstraher verdier
                        values_array = bb_data.get('body_battery_values_array') or bb_data.get('values')
                        raw_max = bb_data.get('max_body_battery')
                        raw_min = bb_data.get('min_body_battery')

                        def to_num(x):
                            if isinstance(x, (int, float)):
                                return x
                            if isinstance(x, (list, tuple)) and len(x) >= 3 and isinstance(x[2], (int, float)):
                                return x[2]
                            return None

                        max_bb = to_num(raw_max)
                        min_bb = to_num(raw_min)
                        if (max_bb is None or min_bb is None) and isinstance(values_array, (list, tuple)) and len(values_array) > 0:
                            try:
                                nums = [to_num(v) for v in values_array]
                                nums = [n for n in nums if isinstance(n, (int, float))]
                                if nums:
                                    if max_bb is None:
                                        max_bb = max(nums)
                                    if min_bb is None:
                                        min_bb = min(nums)
                            except Exception:
                                pass

                        result_from_obj = {
                            "date": date_str,
                            # Disse feltene finnes ikke alltid i DailyBodyBatteryStress – settes til None hvis ukjent
                            "body_battery_charged": bb_data.get('body_battery_charged'),
                            "body_battery_drained": bb_data.get('body_battery_drained'),
                            "body_battery_charged_start": bb_data.get('body_battery_charged_start'),
                            "body_battery_drained_start": bb_data.get('body_battery_drained_start'),
                            "max_body_battery": max_bb,
                            "min_body_battery": min_bb,
                            "net_charge": None,
                        }

                        # Forsøk kalkulert net_charge hvis mulig
                        if result_from_obj["body_battery_charged"] is not None and result_from_obj["body_battery_drained"] is not None:
                            result_from_obj["net_charge"] = (result_from_obj["body_battery_charged"] or 0) - (result_from_obj["body_battery_drained"] or 0)

                        logger.info(f"Hentet body battery via garth.DailyBodyBatteryStress for {date_str}: {result_from_obj}")
                        return result_from_obj
                except Exception as e:
                    logger.debug(f"DailyBodyBatteryStress.get feilet for {date_str}: {e}")

            # 0b) Prøv garth BodyBatteryData for event-detaljer (kan berike men ikke nødvendig for lagring)
            if BodyBatteryDetail is not None:
                try:
                    _bb_detail = await asyncio.to_thread(BodyBatteryDetail.get, date_str)
                    # Vi bruker ikke event-detaljer i DB-modellen, så vi logger kun tilgjengelighet
                    if _bb_detail is not None:
                        logger.debug("BodyBatteryData.get fant event-detaljer for %s", date_str)
                except Exception:
                    pass

            # 1) Prøv flere Connect API-endepunkter, likt som HRV
            endpoints = [
                (f"/usersummary-service/usersummary/daily/{garth.client.username}", {"calendarDate": date_str}),
                (f"/wellness-service/wellness/dailyBodyBattery/{garth.client.username}", {"date": date_str}),
            ]

            body_battery_data = None
            for endpoint, params in endpoints:
                try:
                    logger.info(f"Prøver body battery-endepunkt: {endpoint} med params: {params}")
                    data = await asyncio.to_thread(garth.connectapi, endpoint, params=params)
                    logger.debug(f"Body battery-endepunkt {endpoint} returnerte: {data}")

                    # Håndter ulike responsformater
                    if isinstance(data, dict):
                        if 'allMetrics' in data:
                            metrics = data.get('allMetrics', {}).get('metricsMap', {})
                            result = {
                                "date": date_str,
                                "body_battery_charged": metrics.get('BODY_BATTERY_CHARGED', {}).get('value'),
                                "body_battery_drained": metrics.get('BODY_BATTERY_DRAINED', {}).get('value'),
                                "body_battery_charged_start": metrics.get('BODY_BATTERY_CHARGED_START', {}).get('value'),
                                "body_battery_drained_start": metrics.get('BODY_BATTERY_DRAINED_START', {}).get('value'),
                                "net_charge": (
                                    (metrics.get('BODY_BATTERY_CHARGED', {}).get('value') or 0)
                                    - (metrics.get('BODY_BATTERY_DRAINED', {}).get('value') or 0)
                                ),
                            }
                            logger.info(f"Hentet body battery data fra allMetrics for {date_str}: {result}")
                            body_battery_data = result
                            break
                        elif 'bodyBattery' in data:
                            result = data['bodyBattery']
                            logger.info(f"Hentet body battery data fra bodyBattery for {date_str}: {result}")
                            body_battery_data = result
                            break
                    # Legg til flere formater hvis nødvendig

                except Exception as e:
                    logger.debug(f"Body battery-endepunkt {endpoint} feilet: {e}")
                    continue

            if not body_battery_data:
                logger.info(f"Ingen body battery data funnet for {date_str}")
                return None

            return body_battery_data

        except GarthHTTPError as e:
            e_str = str(e)
            if isinstance(e_str, str) and ("404" in e_str or "not found" in e_str.lower()):
                logger.info(f"Ingen body battery data funnet for {date_str}")
                return None
            logger.error(f"HTTP-feil ved henting av body battery data for {date_str}: {e_str}")
            return None
        except Exception as e:
            logger.error(f"Feil ved henting av body battery data for {date_str}: {e}")
            return None

    async def get_body_battery_range(self, start_date, end_date) -> List[Dict[str, Any]]:
        """Henter body battery data for en datoperiode."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente body battery data.")
            return []
        
        try:
            # Konverter til datetime hvis det er date objekter
            if hasattr(start_date, 'date'):
                start_date_str = start_date.date().strftime("%Y-%m-%d")
            else:
                start_date_str = start_date.strftime("%Y-%m-%d")
                
            if hasattr(end_date, 'date'):
                end_date_str = end_date.date().strftime("%Y-%m-%d")
            else:
                end_date_str = end_date.strftime("%Y-%m-%d")
                
            logger.info(f"Henter body battery data fra {start_date_str} til {end_date_str}")
            
            all_data = []
            # Konverter til datetime for å kunne bruke timedelta
            if hasattr(start_date, 'date'):
                current_date = datetime.combine(start_date.date(), datetime.min.time())
                end_datetime = datetime.combine(end_date.date(), datetime.min.time())
            else:
                current_date = start_date
                end_datetime = end_date
            
            while current_date <= end_datetime:
                data = await self.get_body_battery_data(current_date)
                if data:
                    all_data.append(data)
                
                current_date += timedelta(days=1)
                await asyncio.sleep(0.5)  # Rate limiting
            
            logger.info(f"Hentet {len(all_data)} dager med body battery data")
            return all_data
            
        except Exception as e:
            logger.error(f"Feil ved henting av body battery range: {e}")
            return []

    async def get_sleep_data(self, date: datetime) -> Optional[Dict[str, Any]]:
        """Henter søvndata for en spesifikk dato."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente søvndata.")
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            logger.info(f"Henter søvndata for {date_str}")

            result_from_daily: Optional[Dict[str, Any]] = None
            result_from_sleep: Optional[Dict[str, Any]] = None

            # 0) Prøv garth.DailySleep (score pr dag, tider som sekunder)
            try:
                DailySleep = getattr(garth, 'DailySleep', None)
                if DailySleep is not None:
                    ds = await asyncio.to_thread(DailySleep.list, date_str, 1)
                    if ds:
                        payload_raw = ds[0] if isinstance(ds, list) else ds
                        
                        # Konverter til dict hvis objekt
                        if hasattr(payload_raw, 'to_dict'):
                            payload = payload_raw.to_dict()
                        elif hasattr(payload_raw, 'dict'):
                            payload = payload_raw.dict()
                        elif hasattr(payload_raw, '__dict__'):
                            payload = payload_raw.__dict__.copy()
                        elif isinstance(payload_raw, dict):
                            payload = payload_raw
                        else:
                            # Prøv å hente verdier direkte via getattr
                            payload = {}
                            for attr in ['total_sleep_seconds', 'totalSleepSeconds', 'deep_sleep_seconds', 
                                       'deepSleepSeconds', 'light_sleep_seconds', 'lightSleepSeconds',
                                       'rem_sleep_seconds', 'remSleepSeconds', 'awake_seconds', 
                                       'awakeDurationInSeconds', 'scores', 'sleep_scores', 'sleep_score',
                                       'sleepScore', 'overall_score', 'overallScore', 'score', 'value']:
                                if hasattr(payload_raw, attr):
                                    payload[attr] = getattr(payload_raw, attr)
                        
                        # Hjelpere
                        def find_score_from_dict(d: dict):
                            # Direkte felt
                            for k in ['sleep_score', 'sleepScore', 'score']:
                                v = d.get(k)
                                if isinstance(v, (int, float)):
                                    return v
                            # Nestet under "scores" - søk etter "sleep" først
                            scores = d.get('scores')
                            if scores:
                                # Håndter både dict og objekt
                                if isinstance(scores, dict):
                                    for k in ['sleep', 'sleepScore']:
                                        v = scores.get(k)
                                        if isinstance(v, (int, float)):
                                            return v
                                elif hasattr(scores, 'sleep'):
                                    v = getattr(scores, 'sleep', None)
                                    if isinstance(v, (int, float)):
                                        return v
                            # Prøv sleep_scores som eget attributt
                            sleep_scores = d.get('sleep_scores')
                            if sleep_scores:
                                if isinstance(sleep_scores, dict):
                                    for k in ['sleep', 'sleepScore']:
                                        v = sleep_scores.get(k)
                                        if isinstance(v, (int, float)):
                                            return v
                            return None
                        
                        def find_overall_score_from_dict(d: dict):
                            """Hent overall score spesifikt fra sleep_scores"""
                            # Prøv først 'value' - DailySleep bruker dette for overall score
                            value = d.get('value')
                            if isinstance(value, (int, float)):
                                return value
                            
                            # Søk under "scores" -> "overall"
                            scores = d.get('scores')
                            if scores:
                                if isinstance(scores, dict):
                                    overall = scores.get('overall')
                                    if isinstance(overall, (int, float)):
                                        return overall
                                    overall_score = scores.get('overallScore')
                                    if isinstance(overall_score, (int, float)):
                                        return overall_score
                                elif hasattr(scores, 'overall'):
                                    overall = getattr(scores, 'overall', None)
                                    if isinstance(overall, (int, float)):
                                        return overall
                                elif hasattr(scores, 'overallScore'):
                                    overall_score = getattr(scores, 'overallScore', None)
                                    if isinstance(overall_score, (int, float)):
                                        return overall_score
                            # Prøv sleep_scores som eget attributt
                            sleep_scores = d.get('sleep_scores')
                            if sleep_scores:
                                if isinstance(sleep_scores, dict):
                                    overall = sleep_scores.get('overall')
                                    if isinstance(overall, (int, float)):
                                        return overall
                                elif hasattr(sleep_scores, 'overall'):
                                    overall = getattr(sleep_scores, 'overall', None)
                                    if isinstance(overall, (int, float)):
                                        return overall
                            # Prøv direkte felt
                            for k in ['overall_score', 'overallScore']:
                                v = d.get(k)
                                if isinstance(v, (int, float)):
                                    return v
                            return None
                        
                        to_min = lambda s: (s/60.0) if isinstance(s, (int, float)) else None
                        sleep_time = to_min(payload.get('total_sleep_seconds') or payload.get('totalSleepSeconds'))
                        deep = to_min(payload.get('deep_sleep_seconds') or payload.get('deepSleepSeconds'))
                        light = to_min(payload.get('light_sleep_seconds') or payload.get('lightSleepSeconds'))
                        rem = to_min(payload.get('rem_sleep_seconds') or payload.get('remSleepSeconds'))
                        awake = to_min(payload.get('awake_seconds') or payload.get('awakeDurationInSeconds'))
                        score = find_score_from_dict(payload)
                        overall_score = find_overall_score_from_dict(payload)
                        
                        # Log hvis overall_score finnes for debugging
                        if overall_score is not None:
                            logger.info(f"Fant overall_score = {overall_score} for {date_str}")
                        
                        result = {
                            "date": date_str,
                            "sleep_time": sleep_time,
                            "sleep_goal": None,
                            "sleep_score": score,
                            "overall_score": overall_score,
                            "deep_sleep": deep,
                            "light_sleep": light,
                            "rem_sleep": rem,
                            "awake_time": awake,
                            "total_sleep": sleep_time if sleep_time is not None else ((deep or 0) + (light or 0) + (rem or 0))
                        }
                        if any(v is not None for k, v in result.items() if k != 'date'):
                            logger.info(
                                "DailySleep for %s: lagrer score/tider (henter SleepData for stadier)",
                                date_str,
                            )
                            result_from_daily = result
            except Exception as e:
                logger.debug(f"DailySleep.list feilet for {date_str}: {e}")

            # 1) Prøv garth.SleepData (detaljer per dag)
            try:
                SleepData = getattr(garth, 'SleepData', None)
                if SleepData is not None:
                    sd = await asyncio.to_thread(SleepData.get, date_str)
                    if sd:
                        # garth 0.5+: SleepData har data i daily_sleep_dto (ikke to_dict() på roten)
                        dto = getattr(sd, 'daily_sleep_dto', None)
                        if dto is not None:
                            sd_dict = {
                                k: v
                                for k, v in vars(dto).items()
                                if not k.startswith('_')
                            }
                        elif hasattr(sd, 'to_dict'):
                            sd_dict = sd.to_dict()
                        elif hasattr(sd, 'dict'):
                            sd_dict = sd.dict()
                        else:
                            sd_dict = sd if isinstance(sd, dict) else {}

                        if not isinstance(sd_dict, dict):
                            sd_dict = {}

                        def find_num(d: dict, keys: list):
                            for k in keys:
                                if k in d and isinstance(d[k], (int, float)):
                                    return d[k]
                            return None

                        def find_score(d: dict):
                            # Direkte felt
                            for k in ['sleepScore', 'sleep_score', 'score']:
                                v = d.get(k)
                                if isinstance(v, (int, float)):
                                    return v
                            # Nestet under "scores"-struktur - søk etter "sleep" først
                            scores = d.get('scores') if isinstance(d.get('scores'), dict) else None
                            if scores:
                                for k in ['sleep', 'sleepScore']:
                                    v = scores.get(k)
                                    if isinstance(v, (int, float)):
                                        return v
                            # Noen ganger under "summary"
                            summary = d.get('summary') if isinstance(d.get('summary'), dict) else None
                            if summary:
                                for k in ['sleepScore', 'sleep_score']:
                                    v = summary.get(k)
                                    if isinstance(v, (int, float)):
                                        return v
                            return None

                        def find_overall_score(d: dict):
                            """Hent overall score fra sleep_scores (garth DailySleepDTO) eller scores-dict."""
                            ss = d.get('sleep_scores')
                            if ss is not None and hasattr(ss, 'overall'):
                                ov = getattr(ss.overall, 'value', None)
                                if isinstance(ov, (int, float)):
                                    return ov
                            scores = d.get('scores') if isinstance(d.get('scores'), dict) else None
                            if scores:
                                overall = scores.get('overall')
                                if isinstance(overall, (int, float)):
                                    return overall
                                overall_score = scores.get('overallScore')
                                if isinstance(overall_score, (int, float)):
                                    return overall_score
                            for k in ['overall_score', 'overallScore']:
                                v = d.get(k)
                                if isinstance(v, (int, float)):
                                    return v
                            summary = d.get('summary') if isinstance(d.get('summary'), dict) else None
                            if summary:
                                for k in ['overall', 'overallScore']:
                                    v = summary.get(k)
                                    if isinstance(v, (int, float)):
                                        return v
                            return None

                        to_min = lambda s: (s / 60.0) if isinstance(s, (int, float)) else None
                        deep = to_min(find_num(sd_dict, ['deepSleepSeconds', 'deep_sleep_seconds']))
                        light = to_min(find_num(sd_dict, ['lightSleepSeconds', 'light_sleep_seconds']))
                        rem = to_min(find_num(sd_dict, ['remSleepSeconds', 'rem_sleep_seconds']))
                        awake = to_min(
                            find_num(
                                sd_dict,
                                ['awakeSeconds', 'awake_seconds', 'awake_sleep_seconds'],
                            )
                        )
                        total_sec = find_num(
                            sd_dict,
                            ['totalSleepSeconds', 'total_sleep_seconds', 'sleep_time_seconds'],
                        )
                        total = to_min(total_sec)
                        score = find_score(sd_dict)
                        overall_score = find_overall_score(sd_dict)
                        result = {
                            "date": date_str,
                            "sleep_time": total,
                            "sleep_goal": None,
                            "sleep_score": score,
                            "overall_score": overall_score,
                            "deep_sleep": deep,
                            "light_sleep": light,
                            "rem_sleep": rem,
                            "awake_time": awake,
                            "total_sleep": total if total is not None else ((deep or 0) + (light or 0) + (rem or 0))
                        }
                        if any(v is not None for k, v in result.items() if k != 'date'):
                            logger.info(f"Hentet søvndata via garth.SleepData for {date_str}")
                            result_from_sleep = result
            except Exception as e:
                logger.debug(f"SleepData.get feilet for {date_str}: {e}")

            merged_garth = _merge_garmin_daily_and_sleep_detail(
                result_from_daily, result_from_sleep, date_str
            )
            if merged_garth:
                logger.info(f"Hentet søvndata (DailySleep + SleepData) for {date_str}")
                return merged_garth

            # 2) Prøv usersummary allMetrics
            try:
                sleep_data = await asyncio.to_thread(
                    garth.connectapi,
                    f"/usersummary-service/usersummary/daily/{garth.client.username}",
                    params={"calendarDate": date_str}
                )
                if isinstance(sleep_data, dict) and 'allMetrics' in sleep_data:
                    metrics = sleep_data.get('allMetrics', {}).get('metricsMap', {})
                    sleep_time = metrics.get('SLEEP_TIME', {}).get('value')
                    sleep_goal = metrics.get('SLEEP_GOAL', {}).get('value')
                    sleep_score = metrics.get('SLEEP_SCORE', {}).get('value')
                    deep_sleep = metrics.get('DEEP_SLEEP', {}).get('value')
                    light_sleep = metrics.get('LIGHT_SLEEP', {}).get('value')
                    rem_sleep = metrics.get('REM_SLEEP', {}).get('value')
                    awake_time = metrics.get('AWAKE_TIME', {}).get('value')
                    result = {
                        "date": date_str,
                        "sleep_time": sleep_time,
                        "sleep_goal": sleep_goal,
                        "sleep_score": sleep_score,
                        "deep_sleep": deep_sleep,
                        "light_sleep": light_sleep,
                        "rem_sleep": rem_sleep,
                        "awake_time": awake_time,
                        "total_sleep": (deep_sleep or 0) + (light_sleep or 0) + (rem_sleep or 0)
                    }
                    logger.info(f"Hentet søvndata (usersummary) for {date_str}")
                    return result
            except Exception as e:
                logger.debug(f"usersummary sleep feilet {date_str}: {e}")

            # 3) Prøv wellness-service dailySleepData rå-endepunkt
            for params in ( {"date": date_str}, {"calendarDate": date_str} ):
                try:
                    data = await asyncio.to_thread(
                        garth.connectapi,
                        f"/wellness-service/wellness/dailySleepData/{garth.client.username}",
                        params=params
                    )
                    if isinstance(data, dict):
                        summary = data.get('dailySleepDTO') or data.get('summary') or data
                        def find_score_summary(d: dict):
                            for k in ['sleepScore', 'sleep_score', 'overallScore', 'overall_score', 'score']:
                                v = d.get(k)
                                if isinstance(v, (int, float)):
                                    return v
                            scores = d.get('scores') if isinstance(d.get('scores'), dict) else None
                            if scores:
                                for k in ['overall', 'overallScore', 'sleep', 'sleepScore']:
                                    v = scores.get(k)
                                    if isinstance(v, (int, float)):
                                        return v
                            return None
                        to_min = lambda s: (s/60.0) if isinstance(s, (int, float)) else None
                        total = to_min(summary.get('totalSleepSeconds') or summary.get('total_sleep_seconds'))
                        deep = to_min(summary.get('deepSleepSeconds') or summary.get('deep_sleep_seconds'))
                        light = to_min(summary.get('lightSleepSeconds') or summary.get('light_sleep_seconds'))
                        rem = to_min(summary.get('remSleepSeconds') or summary.get('rem_sleep_seconds'))
                        awake = to_min(summary.get('awakeSeconds') or summary.get('awake_seconds'))
                        score = find_score_summary(summary)
                        result = {
                            "date": date_str,
                            "sleep_time": total,
                            "sleep_goal": None,
                            "sleep_score": score,
                            "deep_sleep": deep,
                            "light_sleep": light,
                            "rem_sleep": rem,
                            "awake_time": awake,
                            "total_sleep": total if total is not None else ((deep or 0) + (light or 0) + (rem or 0))
                        }
                        if any(v is not None for k, v in result.items() if k != 'date'):
                            logger.info(f"Hentet søvndata (wellness dailySleepData) for {date_str}")
                            return result
                except Exception as e:
                    logger.debug(f"wellness dailySleepData feilet {date_str}: {e}")

            logger.info(f"Ingen søvndata funnet for {date_str}")
            return None
                
        except GarthHTTPError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.info(f"Ingen søvndata funnet for {date_str}")
                return None
            logger.error(f"HTTP-feil ved henting av søvndata for {date_str}: {e}")
            return None
        except Exception as e:
            logger.error(f"Feil ved henting av søvndata for {date_str}: {e}")
            return None

    async def get_sleep_range(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Henter søvndata for en datoperiode."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente søvndata.")
            return []
        
        try:
            logger.info(f"Henter søvndata fra {start_date.date()} til {end_date.date()}")
            
            all_data = []
            current_date = start_date
            
            while current_date <= end_date:
                data = await self.get_sleep_data(current_date)
                if data:
                    all_data.append(data)
                
                current_date += timedelta(days=1)
                await asyncio.sleep(0.5)  # Rate limiting
            
            logger.info(f"Hentet {len(all_data)} dager med søvndata")
            return all_data
            
        except Exception as e:
            logger.error(f"Feil ved henting av søvndata range: {e}")
            return []

    async def get_stress_data(self, date_input) -> Optional[Dict[str, Any]]:
        """Henter stressdata for en spesifikk dato."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente stressdata.")
            return None
        
        try:
            # Håndter både date og datetime
            if isinstance(date_input, datetime):
                date_obj = date_input.date()
            elif isinstance(date_input, date):
                date_obj = date_input
            else:
                # Fallback - prøv å hente date-attribute
                date_obj = date_input.date() if hasattr(date_input, 'date') else date_input
            
            date_str = date_obj.strftime("%Y-%m-%d") if hasattr(date_obj, 'strftime') else str(date_obj)
            logger.info(f"Henter stressdata for {date_str}")
            
            # Prøv først garth.DailyStress hvis tilgjengelig
            if DailyStress:
                try:
                    logger.debug(f"Prøver DailyStress.list for {date_str}")
                    stress_list = await asyncio.to_thread(DailyStress.list, date_str, 1)
                    
                    if stress_list and len(stress_list) > 0:
                        stress = stress_list[0]
                        
                        # Konverter sekunder til minutter
                        def to_minutes(seconds):
                            return round(seconds / 60) if seconds else None
                        
                        result = {
                            "date": date_str,
                            "stress_time": to_minutes(getattr(stress, 'activity_stress_duration', None) or getattr(stress, 'low_stress_duration', 0) + getattr(stress, 'medium_stress_duration', 0) + getattr(stress, 'high_stress_duration', 0)),
                            "rest_time": to_minutes(getattr(stress, 'rest_stress_duration', None)),
                            "low_stress_time": to_minutes(getattr(stress, 'low_stress_duration', None)),
                            "medium_stress_time": to_minutes(getattr(stress, 'medium_stress_duration', None)),
                            "high_stress_time": to_minutes(getattr(stress, 'high_stress_duration', None)),
                            "stress_level": getattr(stress, 'overall_stress_level', None),
                            "total_time": None  # Beregnes på klientsiden
                        }
                        
                        # Beregn total_time
                        stress_time = result['stress_time'] or 0
                        rest_time = result['rest_time'] or 0
                        result['total_time'] = stress_time + rest_time
                        
                        logger.info(f"Hentet stressdata via DailyStress for {date_str}: {result}")
                        return result
                    else:
                        logger.debug(f"DailyStress.list returnerte ingen data for {date_str}")
                except Exception as e:
                    logger.debug(f"Feil ved bruk av DailyStress: {e}")
            
            # Fallback til API-kall hvis DailyStress ikke fungerer
            logger.debug(f"Prøver API-kall for {date_str}")
            stress_data = await asyncio.to_thread(
                garth.connectapi,
                f"/usersummary-service/usersummary/daily/{garth.client.username}",
                params={"calendarDate": date_str}
            )
            
            if isinstance(stress_data, dict) and 'allMetrics' in stress_data:
                metrics = stress_data.get('allMetrics', {}).get('metricsMap', {})
                
                # Hent stress-relaterte metrics
                stress_time = metrics.get('STRESS_TIME', {}).get('value')
                rest_time = metrics.get('REST_TIME', {}).get('value')
                low_stress_time = metrics.get('LOW_STRESS_TIME', {}).get('value')
                medium_stress_time = metrics.get('MEDIUM_STRESS_TIME', {}).get('value')
                high_stress_time = metrics.get('HIGH_STRESS_TIME', {}).get('value')
                
                result = {
                    "date": date_str,
                    "stress_time": stress_time,
                    "rest_time": rest_time,
                    "low_stress_time": low_stress_time,
                    "medium_stress_time": medium_stress_time,
                    "high_stress_time": high_stress_time,
                    "total_time": (stress_time or 0) + (rest_time or 0)
                }
                
                logger.info(f"Hentet stressdata via API for {date_str}: {result}")
                return result
            else:
                logger.info(f"Ingen stressdata funnet for {date_str}")
                return None
                
        except GarthHTTPError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.info(f"Ingen stressdata funnet for {date_str}")
                return None
            logger.error(f"HTTP-feil ved henting av stressdata for {date_str}: {e}")
            return None
        except Exception as e:
            logger.error(f"Feil ved henting av stressdata for {date_str}: {e}")
            return None

    async def get_stress_range(self, start_date, end_date) -> List[Dict[str, Any]]:
        """Henter stressdata for en datoperiode."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente stressdata.")
            return []
        
        try:
            # Konverter til datetime hvis nødvendig
            if isinstance(start_date, date) and not isinstance(start_date, datetime):
                start_datetime = datetime.combine(start_date, datetime.min.time())
            elif isinstance(start_date, datetime):
                start_datetime = start_date
            else:
                start_datetime = start_date
            
            if isinstance(end_date, date) and not isinstance(end_date, datetime):
                end_datetime = datetime.combine(end_date, datetime.max.time())
            elif isinstance(end_date, datetime):
                end_datetime = end_date
            else:
                end_datetime = end_date
            
            # Logg med sikker datohåndtering
            start_date_str = start_datetime.date().isoformat() if isinstance(start_datetime, datetime) else str(start_datetime)
            end_date_str = end_datetime.date().isoformat() if isinstance(end_datetime, datetime) else str(end_datetime)
            logger.info(f"Henter stressdata fra {start_date_str} til {end_date_str}")
            
            all_data = []
            current_date = start_datetime
            
            while current_date <= end_datetime:
                data = await self.get_stress_data(current_date)
                if data:
                    all_data.append(data)
                
                current_date += timedelta(days=1)
                await asyncio.sleep(0.5)  # Rate limiting
            
            logger.info(f"Hentet {len(all_data)} dager med stressdata")
            return all_data
            
        except Exception as e:
            logger.error(f"Feil ved henting av stressdata range: {e}", exc_info=True)
            return []

    async def get_hrv_range(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Henter HRV-data for en datoperiode."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente HRV-data.")
            return []
        
        try:
            logger.info(f"Henter HRV-data fra {start_date.date()} til {end_date.date()}")
            
            all_data = []
            current_date = start_date
            
            while current_date <= end_date:
                data = await self.get_hrv_data(current_date)
                if data:
                    all_data.append(data)
                
                current_date += timedelta(days=1)
                await asyncio.sleep(0.5)  # Rate limiting
            
            logger.info(f"Hentet {len(all_data)} dager med HRV-data")
            return all_data
            
        except Exception as e:
            logger.error(f"Feil ved henting av HRV-data range: {e}")
            return []

    async def get_daily_metrics_summary(self, date: datetime) -> Dict[str, Any]:
        """Henter et sammendrag av alle tilgjengelige metrics for en dato."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente metrics sammendrag.")
            return {}
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            logger.info(f"Henter metrics sammendrag for {date_str}")
            
            # Hent alle metrics for dagen
            summary_data = await asyncio.to_thread(
                garth.connectapi, 
                f"/usersummary-service/usersummary/daily/{garth.client.username}",
                {"calendarDate": date_str}
            )
            
            if isinstance(summary_data, dict) and 'allMetrics' in summary_data:
                metrics = summary_data.get('allMetrics', {}).get('metricsMap', {})
                
                # Samle alle tilgjengelige metrics
                result = {
                    "date": date_str,
                    "metrics": {}
                }
                
                # Legg til alle tilgjengelige metrics
                for metric_name, metric_data in metrics.items():
                    if isinstance(metric_data, dict) and 'value' in metric_data:
                        result["metrics"][metric_name] = metric_data['value']
                
                logger.info(f"Hentet metrics sammendrag for {date_str} med {len(result['metrics'])} metrics")
                return result
            else:
                logger.info(f"Ingen metrics sammendrag funnet for {date_str}")
                return {"date": date_str, "metrics": {}}
                
        except GarthHTTPError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.info(f"Ingen metrics sammendrag funnet for {date_str}")
                return {"date": date_str, "metrics": {}}
            logger.error(f"HTTP-feil ved henting av metrics sammendrag for {date_str}: {e}")
            return {"date": date_str, "metrics": {}}
        except Exception as e:
            logger.error(f"Feil ved henting av metrics sammendrag for {date_str}: {e}")
            return {"date": date_str, "metrics": {}}

    async def get_lactate_threshold_speed(self) -> Optional[float]:
        """
        Henter lactate threshold speed fra Garmin Connect eller konfigurasjon.
        
        Returns:
            Optional[float]: Lactate threshold speed i m/s, eller None hvis ikke tilgjengelig
        """
        try:
            if not self.is_authenticated():
                logger.warning("Garmin-klient ikke autentisert")
                # Sjekk konfigurasjon som fallback
                if settings.LACTATE_THRESHOLD_SPEED is not None:
                    logger.info(f"Bruker konfigurert lactate threshold speed: {settings.LACTATE_THRESHOLD_SPEED} m/s")
                    return settings.LACTATE_THRESHOLD_SPEED
                return None
            
            logger.info("Henter lactate threshold speed fra Garmin Connect")
            
            # Prøv å bruke garth.UserSettings.get() direkte
            try:
                import garth
                user_settings = await asyncio.to_thread(garth.UserSettings.get)
                
                if hasattr(user_settings, 'user_data') and user_settings.user_data:
                    user_data = user_settings.user_data
                    lactate_speed = getattr(user_data, 'lactate_threshold_speed', None)
                    if lactate_speed is not None:
                        logger.info(f"Lactate threshold speed hentet fra Garmin: {lactate_speed} (råverdi)")
                        if 2.0 <= lactate_speed <= 6.0:
                            logger.info(f"Lactate threshold speed ({lactate_speed} m/s) er innenfor forventet område, returnerer verdi")
                            return lactate_speed
                        logger.warning(
                            f"Lactate threshold speed {lactate_speed} m/s fra Garmin er utenfor forventet intervall "
                            "(2.0 - 6.0 m/s). Bruker fallback fra konfigurasjon."
                        )
                    else:
                        logger.warning("Lactate threshold speed ikke tilgjengelig i user_data")
                else:
                    logger.warning("user_data ikke tilgjengelig")
                    
            except Exception as e:
                logger.warning(f"Kunne ikke hente lactate threshold speed via garth.UserSettings.get(): {e}")
                
            # Fallback til konfigurasjon
            if settings.LACTATE_THRESHOLD_SPEED is not None:
                logger.info(f"Bruker konfigurert lactate threshold speed: {settings.LACTATE_THRESHOLD_SPEED} m/s")
                return settings.LACTATE_THRESHOLD_SPEED
            else:
                logger.info("Ingen lactate threshold speed tilgjengelig fra Garmin eller konfigurasjon")
                return None
                    
        except Exception as e:
            logger.error(f"Uventet feil ved henting av lactate threshold speed: {e}")
            return None