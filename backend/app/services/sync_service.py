from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional
import asyncio
import logging
from sqlalchemy.orm import Session
import json
import fitparse
from io import BytesIO
from fitparse.utils import FitHeaderError
import pandas as pd

from .garmin_client import GarminClient
from ..storage import DataStorage, DateTimeEncoder
from ..database.models.activity import Activity, ActivityType

logger = logging.getLogger(__name__)

class SyncService:
    def __init__(
        self, 
        garmin_client: GarminClient, 
        storage: DataStorage,
        db_session: Session
    ):
        self.garmin_client = garmin_client
        self.storage = storage
        self.db = db_session

    def _extract_numeric_value(self, value) -> Optional[float]:
        """Ekstraherer numerisk verdi fra FIT-data som kan inneholde enheter."""
        if value is None:
            return None
        
        if isinstance(value, (int, float)):
            return float(value)
        
        if isinstance(value, str):
            # Prøv å ekstrahere tall fra streng som kan inneholde enheter (f.eks. "5.2 m/s")
            import re
            match = re.search(r'[-+]?(?:\d*\.\d+|\d+)', value)
            if match:
                try:
                    return float(match.group())
                except ValueError:
                    pass
        
        return None

    def _parse_fit_data(self, fit_data: bytes) -> Optional[dict]:
        """Parser FIT-data fra bytes til strukturert JSON."""
        if not fit_data:
            return None
        
        try:
            import zipfile
            import io
            from fitparse import FitFile
            
            # Sjekk om dataene er en ZIP-fil
            if fit_data.startswith(b'PK'):
                logger.info("FIT-data er en ZIP-fil, ekstrakterer FIT-fil...")
                try:
                    with zipfile.ZipFile(io.BytesIO(fit_data), 'r') as zip_file:
                        # Finn FIT-filen i ZIP-arkivet
                        fit_files = [name for name in zip_file.namelist() if name.endswith('.fit')]
                        if not fit_files:
                            logger.warning("Ingen FIT-fil funnet i ZIP-arkivet")
                            return None
                        
                        # Bruk den første FIT-filen
                        fit_filename = fit_files[0]
                        logger.info(f"Ekstrakterer FIT-fil: {fit_filename}")
                        fit_data = zip_file.read(fit_filename)
                        
                except zipfile.BadZipFile:
                    logger.warning("Kunne ikke åpne som ZIP-fil, prøver som rå FIT-data")
                except Exception as e:
                    logger.error(f"Feil ved ekstraksjon av ZIP-fil: {e}")
                    return None
            
            # Parser FIT-data
            fitfile = FitFile(io.BytesIO(fit_data))
            
            records = []
            for record in fitfile.get_messages("record"):
                parsed_record = {}
                for field in record.fields:
                    value = field.value
                    # Håndter semicircles (lat/lon)
                    if field.name in ['position_lat', 'position_long'] and value is not None:
                        # Konverter fra semicircles til desimalgrader
                        value = value * (180 / (2**31))
                    # Konverter datetime til ISO-string for JSON-serialisering
                    elif hasattr(value, 'isoformat'):
                        value = value.isoformat()
                    parsed_record[field.name] = value
                
                records.append(parsed_record)
            
            logger.info(f"Parsed {len(records)} FIT-records")
            return {"records": records}
            
        except ImportError:
            logger.error("fitparse-biblioteket er ikke installert. Kan ikke parse FIT-data.")
            return None
        except Exception as e:
            logger.warning(f"Kunne ikke parse FIT-data: {e}")
            return None

    def sync_json_to_db(self) -> dict:
        """
        Leser alle aktiviteter fra JSON-filer og synkroniserer dem til databasen.
        """
        logger.info("Starter synkronisering fra JSON-filer til database.")
        
        # 1. Hent alle aktiviteter fra JSON-filene
        json_activities = self.storage.get_activities()
        if not json_activities:
            logger.warning("Fant ingen JSON-filer å synkronisere.")
            return {"status": "Ingen JSON-filer funnet", "added": 0, "skipped": 0}

        # 2. Hent alle eksisterende ID-er fra databasen for å unngå duplikater
        existing_ids = {result[0] for result in self.db.query(Activity.id).all()}
        logger.info(f"Fant {len(existing_ids)} eksisterende aktiviteter i databasen.")
        
        added_count = 0
        skipped_count = 0
        
        # Ordbok for å cache ActivityType-objekter
        activity_type_cache = {}

        for act_data in json_activities:
            activity_id = act_data.get('activityId')
            
            if not activity_id or activity_id in existing_ids:
                skipped_count += 1
                continue
            
            # Håndter ActivityType
            activity_type_key = act_data.get('activityType', {}).get('typeKey')
            activity_type_obj = None
            if activity_type_key:
                if activity_type_key in activity_type_cache:
                    activity_type_obj = activity_type_cache[activity_type_key]
                else:
                    activity_type_obj = self.db.query(ActivityType).filter_by(type_key=activity_type_key).first()
                    if not activity_type_obj:
                        # Opprett ny ActivityType hvis den ikke finnes
                        parent_type_key = act_data.get('activityType', {}).get('parentTypeKey', 'unknown')
                        activity_type_obj = ActivityType(type_key=activity_type_key, parent_type_key=parent_type_key)
                        self.db.add(activity_type_obj)
                        self.db.flush() # Få ID-en før commit
                    activity_type_cache[activity_type_key] = activity_type_obj
            
            # Konverter pace til speed hvis nødvendig
            avg_pace = act_data.get('averagePace')
            avg_speed = act_data.get('averageSpeed', 0)
            if not avg_speed and avg_pace and avg_pace > 0:
                avg_speed = (1000 / (avg_pace * 60))

            new_activity = Activity(
                id=activity_id,
                name=act_data.get('activityName'),
                type=act_data.get('activityType', {}).get('typeKey'), # Lagrer den rå typen
                start_time=datetime.fromisoformat(act_data['startTimeInSeconds']),
                distance=act_data.get('distance'),
                duration=act_data.get('duration'),
                calories=act_data.get('calories'),
                vo2_max=act_data.get('vO2MaxValue'),
                average_hr=act_data.get('averageHR'),
                average_speed=avg_speed,
                average_pace=avg_pace,
                activity_type_id=activity_type_obj.id if activity_type_obj else None,
                average_running_cadence=act_data.get('averageRunningCadenceInStepsPerMinute')
            )
            self.db.add(new_activity)
            added_count += 1
            
        self.db.commit()
        logger.info(f"Synkronisering fullført. La til: {added_count}, hoppet over: {skipped_count}.")
        return {"status": "Fullført", "added": added_count, "skipped": skipped_count}

    def _calculate_missing_periods(
        self,
        start_date_req: datetime,
        end_date_req: datetime,
        max_days_per_request: int = 90
    ) -> List[Tuple[datetime, datetime]]:
        """
        Beregner hvilke tidsperioder som mangler data, basert på ønsket periode
        og eksisterende data. Deler opp i mindre biter.
        """
        min_stored, max_stored = self.storage.get_activity_date_coverage()
        logger.info(f"Ønsket synkroniseringsperiode: {start_date_req} -> {end_date_req}")
        logger.info(f"Eksisterende datadekning: {min_stored} -> {max_stored}")

        periods_to_fetch = []

        # Hvis ingen data finnes, er hele perioden manglende.
        if min_stored is None or max_stored is None:
            logger.info("Ingen eksisterende data. Hele perioden må hentes.")
            periods_to_fetch.append((start_date_req, end_date_req))
        else:
            # 1. Sjekk for manglende data FØR det som allerede er lagret
            if start_date_req < min_stored:
                periods_to_fetch.append((start_date_req, min_stored - timedelta(days=1)))
            
            # 2. Sjekk for manglende data ETTER det som allerede er lagret
            if end_date_req > max_stored:
                periods_to_fetch.append((max_stored + timedelta(days=1), end_date_req))

        if not periods_to_fetch:
            logger.info("Ingen nye tidsperioder å hente. Data er allerede à jour for den forespurte perioden.")
            return []

        # Deler opp de manglende periodene i mindre biter for å unngå for store API-kall
        chunked_periods = []
        for start, end in periods_to_fetch:
            current_start = start
            while current_start <= end:
                chunk_end = min(current_start + timedelta(days=max_days_per_request - 1), end)
                chunked_periods.append((current_start, chunk_end))
                current_start = chunk_end + timedelta(days=1)
        
        logger.info(f"Beregnet {len(chunked_periods)} perioder som skal hentes: {chunked_periods}")
        return chunked_periods

    async def sync_activities_with_fit_data(self, start_date: datetime, end_date: datetime, force_refresh_recent: bool = False, fit_data_limit: int = 100) -> dict:
        """
        Synkroniserer aktiviteter og laster automatisk ned FIT-data for aktiviteter som mangler det.
        
        Args:
            start_date: Startdato for synkronisering
            end_date: Sluttdato for synkronisering  
            force_refresh_recent: Om nylige data skal oppdateres selv om de eksisterer
            fit_data_limit: Maksimalt antall aktiviteter å laste ned FIT-data for
        """
        logger.info(f"Starter utvidet aktivitetssynkronisering med automatisk FIT-data nedlasting")
        
        # Først, gjør vanlig aktivitetssynkronisering
        sync_result = await self.sync_activities(start_date, end_date, force_refresh_recent)
        
        # Så, last ned FIT-data for aktiviteter som mangler det
        fit_result = {"status": "Ikke kjørt", "success_count": 0, "total_count": 0}
        
        try:
            logger.info(f"Starter automatisk FIT-data nedlasting for aktiviteter som mangler data...")
            fit_result = await self.download_fit_data_for_activities(limit=fit_data_limit)
            logger.info(f"FIT-data nedlasting ferdig: {fit_result.get('message', 'Ukjent status')}")
        except Exception as e:
            logger.error(f"Feil under automatisk FIT-data nedlasting: {e}")
            fit_result = {"status": "Feil", "message": str(e), "success_count": 0, "total_count": 0}
        
        # Kombiner resultater
        combined_result = {
            "sync_result": sync_result,
            "fit_data_result": fit_result,
            "status": "Fullført med FIT-data",
            "summary": {
                "activities_synced": sync_result.get("total_fetched", 0),
                "fit_data_downloaded": fit_result.get("success_count", 0),
                "fit_data_attempted": fit_result.get("total_count", 0),
                "sync_status": sync_result.get("status", "Ukjent"),
                "fit_status": fit_result.get("status", "Ukjent")
            }
        }
        
        logger.info(f"Utvidet synkronisering fullført: {combined_result['summary']}")
        return combined_result

    async def sync_activities(self, start_date: datetime, end_date: datetime, force_refresh_recent: bool = False) -> dict:
        """
        Orkestrerer synkronisering av aktiviteter for en gitt tidsperiode og lagrer dem i databasen.
        """
        summary = {"total_fetched": 0, "periods_synced": 0, "status": "Startet"}
        
        try:
            if not await self.garmin_client.initialize():
                logger.error("Kunne ikke initialisere Garmin-klient.")
                summary["status"] = "Feil: Kunne ikke autentisere mot Garmin"
                return summary

            # For nå, la oss bare hente hele perioden uten å sjekke dekning
            # for å sikre at vi får data inn i den nye DB-en.
            logger.info(f"Henter aktiviteter fra Garmin: {start_date.date()} -> {end_date.date()}")
            
            activities_raw = await self.garmin_client.get_activities(start_date, end_date)
            
            # Filtrer bort duplikater basert på 'activityId'
            existing_ids = self.storage.get_existing_activity_ids(self.db)
            
            # Beregn grensen for "nylige" data (siste 2 dager)
            recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)

            activities_to_save = [
                act for act in activities_raw
                if act.get('distance', 0) is not None and act.get('distance', 0) > 0
            ]

            if not activities_to_save:
                summary["status"] = "Fant ingen nye aktiviteter med GPS-data hos Garmin."
                logger.info(summary["status"])
                return summary

            logger.info(f"Fant {len(activities_to_save)} aktiviteter hos Garmin. Lagrer til database.")
            
            activity_type_cache = {}
            added_count = 0
            logged_one = False  # Flagg for å bare logge én gang

            for i, act_data in enumerate(activities_to_save):
                if not logged_one:
                    logger.info(f"DEBUG: Nøkler i første aktivitet: {list(act_data.keys())}")
                    logged_one = True

                activity_id = str(act_data.get('activityId'))
                
                if i < 5: # Logger de 5 første for feilsøking
                    is_in_db = activity_id in existing_ids
                    logger.info(f"DEBUG: Behandler aktivitet {i+1}/{len(activities_to_save)}: ID='{activity_id}', Finnes i DB? {is_in_db}")

                if not activity_id:
                    continue
                    
                # Sjekk om aktiviteten er nylig og om vi skal force refresh
                activity_start_time = datetime.fromisoformat(act_data['startTimeGMT'])
                # Sørg for at begge datetimes har samme timezone-oppsett
                if activity_start_time.tzinfo is None:
                    activity_start_time = activity_start_time.replace(tzinfo=timezone.utc)
                is_recent = activity_start_time >= recent_cutoff
                should_skip = (activity_id in existing_ids and 
                              not (force_refresh_recent and is_recent))
                
                if should_skip:
                    continue
                elif activity_id in existing_ids and force_refresh_recent and is_recent:
                    logger.info(f"Oppdaterer eksisterende aktivitet {activity_id} (force_refresh_recent=True).")
                    # Slett eksisterende aktivitet først
                    existing_activity = self.db.query(Activity).filter_by(id=activity_id).first()
                    if existing_activity:
                        self.db.delete(existing_activity)

                # Hent detaljerte data (FIT-fil)
                details_json = None
                fit_data = await self.garmin_client.get_activity_details(activity_id)
                if fit_data:
                    details_json = self._parse_fit_data(fit_data)
                    
                    # Lagre FIT-data også i parquet-format for decoupling-beregninger
                    if details_json and 'records' in details_json:
                        logger.info(f"Lagrer FIT-data for aktivitet {activity_id} til parquet-fil...")
                        parquet_records = []
                        for record in details_json['records']:
                            # Konverter timestamp til UTC hvis det eksisterer
                            timestamp = record.get('timestamp')
                            if timestamp:
                                if isinstance(timestamp, str):
                                    timestamp = pd.to_datetime(timestamp, utc=True)
                                elif hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is None:
                                    timestamp = pd.to_datetime(timestamp, utc=True)
                                elif not hasattr(timestamp, 'tzinfo'):
                                    timestamp = pd.to_datetime(timestamp, utc=True)
                            
                            parquet_record = {
                                'activity_id': int(activity_id),
                                'timestamp': timestamp,
                                'latitude': self._extract_numeric_value(record.get('position_lat')),
                                'longitude': self._extract_numeric_value(record.get('position_long')),
                                'distance': self._extract_numeric_value(record.get('distance')),
                                'speed': self._extract_numeric_value(record.get('enhanced_speed') or record.get('speed')),
                                'heart_rate': self._extract_numeric_value(record.get('heart_rate')),
                                'cadence': self._extract_numeric_value(record.get('cadence')),
                                'temperature': self._extract_numeric_value(record.get('temperature')),
                                'altitude': self._extract_numeric_value(record.get('enhanced_altitude') or record.get('altitude'))
                            }
                            
                            # Kun legg til record hvis den har nødvendige data
                            if parquet_record['timestamp'] is not None:
                                parquet_records.append(parquet_record)
                        
                        if parquet_records:
                            try:
                                self.storage.save_activity_details(parquet_records)
                                logger.info(f"Lagret {len(parquet_records)} FIT-records for aktivitet {activity_id}")
                            except Exception as e:
                                logger.error(f"Feil ved lagring av FIT-data til parquet for aktivitet {activity_id}: {e}")
                        else:
                            logger.warning(f"Ingen gyldige FIT-records funnet for aktivitet {activity_id}")
                    else:
                        logger.warning(f"Ingen FIT-records tilgjengelig for aktivitet {activity_id}")

                # Håndter ActivityType
                activity_type_key = act_data.get('activityType', {}).get('typeKey')
                activity_type_obj = None
                if activity_type_key:
                    if activity_type_key in activity_type_cache:
                        activity_type_obj = activity_type_cache[activity_type_key]
                    else:
                        activity_type_obj = self.db.query(ActivityType).filter_by(type_key=activity_type_key).first()
                        if not activity_type_obj:
                            parent_type_key = act_data.get('activityType', {}).get('parentTypeKey', 'unknown')
                            activity_type_obj = ActivityType(type_key=activity_type_key, parent_type_key=parent_type_key)
                            self.db.add(activity_type_obj)
                            self.db.flush()
                        activity_type_cache[activity_type_key] = activity_type_obj

                # Konverter pace til speed hvis nødvendig
                avg_pace = act_data.get('averagePace')
                avg_speed = act_data.get('averageSpeed', 0)
                if not avg_speed and avg_pace and avg_pace > 0:
                    avg_speed = (1000 / (avg_pace * 60))

                # Sørg for at start_time har timezone-info
                start_time = datetime.fromisoformat(act_data['startTimeGMT'])
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                
                new_activity = Activity(
                    id=activity_id,
                    name=act_data.get('activityName'),
                    type=activity_type_key,
                    start_time=start_time,
                    distance=act_data.get('distance'),
                    duration=act_data.get('duration'),
                    calories=act_data.get('calories'),
                    vo2_max=act_data.get('vO2MaxValue'),
                    average_hr=act_data.get('averageHR'),
                    average_speed=avg_speed,
                    average_pace=avg_pace,
                    activity_type_id=activity_type_obj.id if activity_type_obj else None,
                    average_running_cadence=act_data.get('averageRunningCadenceInStepsPerMinute'),
                    details=details_json
                )
                self.db.add(new_activity)
                added_count += 1

            self.db.commit()
            summary["total_fetched"] = added_count
            summary["status"] = "Fullført"
            logger.info(f"Synkronisering fra Garmin fullført. La til {added_count} nye aktiviteter i databasen.")

        except Exception as e:
            logger.critical(f"En alvorlig feil oppstod under Garmin-synkronisering: {e}", exc_info=True)
            self.db.rollback()  # Rull tilbake endringer ved feil
            summary["status"] = f"Feil: {e}"
        
        return summary 

    def _normalize_hrv_data(self, hrv_data: dict, calendar_date: str) -> Optional[dict]:
        """Normaliserer HRV-data til en flat struktur for lagring."""
        if not hrv_data or 'hrv_summary' not in hrv_data:
            logger.warning(f"HRV-data mangler eller har ingen 'hrv_summary' for {calendar_date}: {hrv_data}")
            return None
        
        summary = hrv_data['hrv_summary']
        
        # Sjekk om summary er None
        if summary is None:
            logger.warning(f"hrv_summary er None for {calendar_date}")
            return None
        
        # Bruk weekly_avg som fallback for baseline-verdier hvis de ikke finnes
        weekly_avg = summary.get('weekly_avg', 0) if summary else 0
        last_night_avg = summary.get('last_night_avg') if summary else None
        
        # Hopp over hvis vi ikke har noen HRV-verdier
        if not last_night_avg:
            logger.info(f"Ingen last_night_avg verdi for {calendar_date}, hopper over")
            return None
        
        return {
            "date": calendar_date,
            "last_night_avg": last_night_avg,
            "last_night_5_min_high": summary.get('last_night_5_min_high', 0) if summary else 0,
            "baseline_low_upper": summary.get('baseline_low_upper', weekly_avg * 0.8 if weekly_avg else 0) if summary else 0,
            "baseline_balanced_lower": summary.get('baseline_balanced_lower', weekly_avg * 0.9 if weekly_avg else 0) if summary else 0,
            "baseline_balanced_upper": summary.get('baseline_balanced_upper', weekly_avg * 1.1 if weekly_avg else 0) if summary else 0,
            "status": summary.get('status') if summary else None,
        }

    async def sync_health_data(self, start_date: datetime, end_date: datetime, force_refresh_recent: bool = False):
        """Synkroniserer helsedata (HRV, etc.) for en gitt periode."""
        logger.info(f"Starter synkronisering av helsedata fra {start_date.date()} til {end_date.date()}")
        
        if not await self.garmin_client.initialize():
            logger.error("Kunne ikke initialisere Garmin-klient for helsedata-synk.")
            return

        all_hrv_data = []
        
        # Beregn grensen for "nylige" data (siste 2 dager)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        
        # Hent eksisterende HRV-datoer BARE for det ønskede tidsrommet
        try:
            hrv_df = self.storage.get_hrv_data()
            if hrv_df is not None and not hrv_df.empty:
                # Filtrer eksisterende data til kun det ønskede tidsrommet
                start_filter = pd.to_datetime(start_date.date(), utc=True)
                end_filter = pd.to_datetime(end_date.date(), utc=True)
                filtered_hrv_df = hrv_df[(hrv_df.index >= start_filter) & (hrv_df.index <= end_filter)]
                existing_dates = set(filtered_hrv_df.index.to_series().dt.date)
                logger.info(f"Fant {len(existing_dates)} eksisterende HRV-datoer innenfor det ønskede tidsrommet.")
            else:
                existing_dates = set()
                logger.info("Ingen eksisterende HRV-data funnet.")
        except Exception as e:
            logger.warning(f"Kunne ikke lese eksisterende HRV-datoer, fortsetter uten duplikatsjekk. Feil: {e}")
            existing_dates = set()

        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            
            # Sjekk om vi skal hoppe over duplikater
            is_recent = current_date >= recent_cutoff
            should_skip = (current_date.date() in existing_dates and 
                          not (force_refresh_recent and is_recent))
            
            if should_skip:
                logger.info(f"Hopper over HRV-data for {date_str} (finnes allerede).")
                current_date += timedelta(days=1)
                continue
            elif current_date.date() in existing_dates and force_refresh_recent and is_recent:
                logger.info(f"Oppdaterer eksisterende HRV-data for {date_str} (force_refresh_recent=True).")

            try:
                # Hent HRV-data (prøv alternative metode først)
                hrv_data = await self.garmin_client.get_hrv_data_alternative(current_date)
                if hrv_data:
                    normalized_hrv = self._normalize_hrv_data(hrv_data, date_str)
                    if normalized_hrv:
                        all_hrv_data.append(normalized_hrv)
                
                # Liten pause for å unngå rate limiting
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Feil under henting av helsedata for {date_str}: {e}")
            
            current_date += timedelta(days=1)

        if all_hrv_data:
            logger.info(f"Fant {len(all_hrv_data)} nye dager med HRV-data. Lagrer...")
            self.storage.save_hrv_data(all_hrv_data)
        else:
            logger.info("Ingen nye HRV-data å lagre.") 

    async def _download_and_store_fit_file(self, activity_id: int):
        """Hjelpefunksjon for å laste ned og lagre en FIT-fil for en gitt aktivitet."""
        try:
            logger.info(f"Laster ned FIT-data for aktivitet {activity_id}...")
            
            # Hent FIT-data fra Garmin
            fit_data = await self.garmin_client.get_activity_details(activity_id)
            if not fit_data:
                logger.warning(f"Ingen FIT-data tilgjengelig for aktivitet {activity_id}")
                return False
                
            # Parse FIT-data
            details_json = self._parse_fit_data(fit_data)
            if not details_json or 'records' not in details_json:
                logger.warning(f"Kunne ikke parse FIT-data for aktivitet {activity_id}")
                return False
                
            # Lagre til parquet-format
            parquet_records = []
            for record in details_json['records']:
                # Konverter timestamp til UTC hvis det eksisterer
                timestamp = record.get('timestamp')
                if timestamp:
                    if isinstance(timestamp, str):
                        timestamp = pd.to_datetime(timestamp, utc=True)
                    elif hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is None:
                        timestamp = pd.to_datetime(timestamp, utc=True)
                    elif not hasattr(timestamp, 'tzinfo'):
                        timestamp = pd.to_datetime(timestamp, utc=True)
                
                parquet_record = {
                    'activity_id': int(activity_id),
                    'timestamp': timestamp,
                    'latitude': self._extract_numeric_value(record.get('position_lat')),
                    'longitude': self._extract_numeric_value(record.get('position_long')),
                    'distance': self._extract_numeric_value(record.get('distance')),
                    'speed': self._extract_numeric_value(record.get('enhanced_speed') or record.get('speed')),
                    'heart_rate': self._extract_numeric_value(record.get('heart_rate')),
                    'cadence': self._extract_numeric_value(record.get('cadence')),
                    'temperature': self._extract_numeric_value(record.get('temperature')),
                    'altitude': self._extract_numeric_value(record.get('enhanced_altitude') or record.get('altitude'))
                }
                
                # Kun legg til record hvis den har nødvendige data
                if parquet_record['timestamp'] is not None:
                    parquet_records.append(parquet_record)
            
            if parquet_records:
                self.storage.save_activity_details(parquet_records)
                logger.info(f"Lagret {len(parquet_records)} FIT-records for aktivitet {activity_id}")
                
                # Oppdater også database med details_json
                activity = self.db.query(Activity).filter_by(id=activity_id).first()
                if activity:
                    activity.details = details_json
                    self.db.commit()
                    logger.info(f"Oppdaterte database med FIT-data for aktivitet {activity_id}")
                
                return True
            else:
                logger.warning(f"Ingen gyldige FIT-records funnet for aktivitet {activity_id}")
                return False
                
        except Exception as e:
            logger.error(f"Feil ved nedlasting av FIT-data for aktivitet {activity_id}: {e}")
            return False

    async def download_fit_data_for_activities(self, activity_ids: list = None, limit: int = None):
        """Laster ned FIT-data for spesifikke aktiviteter eller alle aktiviteter uten FIT-data."""
        if not await self.garmin_client.initialize():
            logger.error("Kunne ikke initialisere Garmin-klient for FIT-nedlasting.")
            return {"status": "Feil", "message": "Kunne ikke initialisere Garmin-klient"}

        try:
            if activity_ids is None:
                # Finn aktiviteter som ikke har FIT-data i parquet-filen ELLER i database
                try:
                    import pandas as pd
                    existing_parquet_df = pd.read_parquet('data/activity_details.parquet')
                    existing_fit_activity_ids = set(existing_parquet_df['activity_id'].unique())
                except:
                    existing_fit_activity_ids = set()
                
                # Hent alle aktiviteter fra database og sjekk details-felt
                query = self.db.query(Activity.id, Activity.details).order_by(Activity.id.desc())
                if limit:
                    query = query.limit(limit * 3)  # Hent flere siden mange kan mangle FIT-data
                
                all_activities = query.all()
                
                # Finn aktiviteter som mangler FIT-data (enten i parquet eller details)
                activity_ids = []
                for activity in all_activities:
                    activity_id = activity.id
                    has_parquet_data = activity_id in existing_fit_activity_ids
                    has_db_details = activity.details is not None and activity.details != {} and 'records' in str(activity.details)
                    
                    if not (has_parquet_data and has_db_details):
                        activity_ids.append(activity_id)
                        if limit and len(activity_ids) >= limit:
                            break
                
                logger.info(f"Fant {len(activity_ids)} aktiviteter som mangler FIT-data (av totalt {len(all_activities)} sjekket)")
                logger.info(f"Første 10 aktiviteter som mangler data: {activity_ids[:10]}")
            
            if not activity_ids:
                return {"status": "Fullført", "message": "Ingen aktiviteter mangler FIT-data"}
            
            success_count = 0
            total_count = len(activity_ids)
            
            for i, activity_id in enumerate(activity_ids):
                logger.info(f"Prosesserer aktivitet {activity_id} ({i+1}/{total_count})")
                
                if await self._download_and_store_fit_file(activity_id):
                    success_count += 1
                
                # Liten pause for å unngå rate limiting
                await asyncio.sleep(0.5)
            
            message = f"Lastet ned FIT-data for {success_count} av {total_count} aktiviteter"
            logger.info(message)
            
            return {
                "status": "Fullført",
                "message": message,
                "success_count": success_count,
                "total_count": total_count
            }
            
        except Exception as e:
            logger.error(f"Feil under FIT-data nedlasting: {e}")
            return {"status": "Feil", "message": str(e)} 