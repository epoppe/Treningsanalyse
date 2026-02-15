from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional
import asyncio
import logging
from sqlalchemy.orm import Session
import json
import fitparse
from io import BytesIO
from fitparse.utils import FitHeaderError
import polars as pl
from dateutil import parser as date_parser

from .garmin_client import GarminClient
from .analysis_service import AnalysisService
from ..storage import DataStorage, DateTimeEncoder
from ..database.models.activity import Activity, ActivityType
from ..database.models.sync_state import SyncState
from ..database.models.health_data_missing import HealthDataMissing

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
        self.analysis_service = AnalysisService(storage)

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
            total_ascent = None
            total_descent = None
            
            # Hent elevation gain fra session-meldingen
            for message in fitfile.get_messages("session"):
                for field in message.fields:
                    if field.name == 'total_ascent':
                        total_ascent = field.value
                    elif field.name == 'total_descent':
                        total_descent = field.value
            
            # Hent records
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
            
            result = {"records": records}
            if total_ascent is not None:
                result["total_ascent"] = total_ascent
            if total_descent is not None:
                result["total_descent"] = total_descent
            
            logger.info(f"Parsed {len(records)} FIT-records, total_ascent={total_ascent}, total_descent={total_descent}")
            return result
            
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

            # Hent lactate threshold speed fra Garmin-klienten
            lactate_threshold_speed = None
            try:
                # Bruk asyncio.run for å kjøre async funksjon i sync kontekst
                import asyncio
                lactate_threshold_speed = asyncio.run(self.garmin_client.get_lactate_threshold_speed())
            except Exception as e:
                logger.warning(f"Kunne ikke hente lactate threshold speed: {e}")

            new_activity = Activity(
                activity_id=activity_id,
                activity_name=act_data.get('activityName'),
                start_time=datetime.fromisoformat(act_data['startTimeInSeconds']),
                distance=act_data.get('distance'),
                duration=act_data.get('duration'),
                calories=act_data.get('calories'),
                vo2_max=act_data.get('vO2MaxValue'),
                average_heart_rate=act_data.get('averageHR'),
                average_speed=avg_speed,
                average_pace=avg_pace,
                activity_type_id=activity_type_obj.id if activity_type_obj else None,
                average_running_cadence=act_data.get('averageRunningCadenceInStepsPerMinute'),
                total_training_effect=act_data.get('trainingEffect'),
                total_anaerobic_training_effect=act_data.get('anaerobicTrainingEffect'),
                lactate_threshold_speed=lactate_threshold_speed  # Lactate threshold speed
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

    async def sync_activities_with_fit_data(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
        fit_data_limit: int = 100,
        ignore_sync_state: bool = False,
        fit_download_mode: str = "chunked",
    ) -> dict:
        """
        Synkroniserer aktiviteter og laster automatisk ned FIT-data, HRV-data og Training Effect for aktiviteter som mangler det.
        
        Args:
            start_date: Startdato for synkronisering
            end_date: Sluttdato for synkronisering  
            force_refresh_recent: Om nylige data skal oppdateres selv om de eksisterer
            fit_data_limit: Maksimalt antall aktiviteter å laste ned FIT-data for
        """
        logger.info(f"Starter utvidet aktivitetssynkronisering med automatisk FIT-data, HRV og Training Effect nedlasting")
        
        # Først, gjør vanlig aktivitetssynkronisering
        sync_result = await self.sync_activities(start_date, end_date, force_refresh_recent, ignore_sync_state)
        
        # Så, last ned FIT-data for aktiviteter som mangler det (kun for aktiviteter i det valgte tidsrommet)
        fit_result = {"status": "Ikke kjørt", "success_count": 0, "total_count": 0}
        
        # Last ned FIT-data
        days_diff = (end_date - start_date).days
        try:
            if days_diff <= 7 or fit_download_mode == "auto":
                logger.info(f"Starter automatisk FIT-data nedlasting for aktiviteter i perioden {start_date.date()} til {end_date.date()}...")
                fit_result = await self.download_fit_data_for_period(start_date, end_date)
                logger.info(f"FIT-data nedlasting ferdig: {fit_result.get('message', 'Ukjent status')}")
            else:
                # chunked modus for lange perioder
                logger.info(f"Starter chunket FIT-data nedlasting for periode på {days_diff} dager")
                chunk_success = 0
                chunk_total = 0
                metrics_agg = {"negative_split": 0, "decoupling": 0, "hrv_available": 0}
                chunk_start = start_date
                while chunk_start <= end_date:
                    chunk_end = min(chunk_start + timedelta(days=6), end_date)
                    logger.info(f"FIT-chunk: {chunk_start.date()} -> {chunk_end.date()}")
                    chunk_res = await self.download_fit_data_for_period(chunk_start, chunk_end)
                    chunk_success += int(chunk_res.get("success_count", 0))
                    chunk_total += int(chunk_res.get("total_count", 0))
                    m = chunk_res.get("metrics_calculated", {})
                    metrics_agg["negative_split"] += int(m.get("negative_split", 0))
                    metrics_agg["decoupling"] += int(m.get("decoupling", 0))
                    metrics_agg["hrv_available"] += int(m.get("hrv_available", 0))
                    chunk_start = chunk_end + timedelta(days=1)
                fit_result = {
                    "status": "Fullført",
                    "message": f"Chunket FIT-data nedlasting fullført for periode {start_date.date()} til {end_date.date()}",
                    "success_count": chunk_success,
                    "total_count": chunk_total,
                    "metrics_calculated": metrics_agg,
                }
        except Exception as e:
            logger.error(f"Feil under automatisk FIT-data nedlasting: {e}")
            fit_result = {"status": "Feil", "message": str(e), "success_count": 0, "total_count": 0}
        
        # Synkroniser HRV-data for samme periode
        hrv_result = {"status": "Ikke kjørt", "message": "Ikke kjørt"}
        try:
            logger.info(f"Starter automatisk HRV-synkronisering for perioden {start_date.date()} til {end_date.date()}...")
            await self.sync_health_data(start_date, end_date, force_refresh_recent)
            hrv_result = {"status": "Fullført", "message": "HRV-data synkronisert"}
            logger.info("HRV-synkronisering fullført")
        except Exception as e:
            logger.error(f"Feil under HRV-synkronisering: {e}")
            hrv_result = {"status": "Feil", "message": str(e)}
        
        # Synkroniser Training Effect data for samme periode
        te_result = {"status": "Ikke kjørt", "message": "Ikke kjørt"}
        try:
            logger.info(f"Starter automatisk Training Effect synkronisering for perioden {start_date.date()} til {end_date.date()}...")
            te_result = await self.sync_training_effect_data(start_date, end_date, force_refresh_recent)
            logger.info(f"Training Effect synkronisering fullført: {te_result.get('message', 'Ukjent status')}")
        except Exception as e:
            logger.error(f"Feil under Training Effect synkronisering: {e}")
            te_result = {"status": "Feil", "message": str(e)}
        
        # Oppdater sammendragstabeller automatisk hvis nye aktiviteter ble synkronisert
        summary_result = {"status": "Ikke kjørt", "message": "Ingen nye aktiviteter"}
        if sync_result.get("total_fetched", 0) > 0:
            try:
                logger.info("Starter automatisk oppdatering av sammendragstabeller...")
                from ..services.summary_service import SummaryService
                summary_service = SummaryService()
                
                # Oppdater sammendrag for perioden som ble synkronisert
                summary_service.bulk_update_summaries(start_date.date(), end_date.date())
                
                # Oppdater også alle månedlige sammendrag for å sikre at de er à jour
                logger.info("Oppdaterer alle månedlige sammendrag...")
                monthly_count = summary_service.calculate_monthly_summaries()
                logger.info(f"Oppdatert {monthly_count} månedlige sammendrag")
                
                summary_result = {
                    "status": "Fullført", 
                    "message": f"Sammendrag oppdatert for perioden {start_date.date()} til {end_date.date()}, {monthly_count} månedlige sammendrag oppdatert"
                }
                logger.info("Sammendragstabeller oppdatert automatisk")
            except Exception as e:
                logger.error(f"Feil under automatisk oppdatering av sammendrag: {e}")
                summary_result = {"status": "Feil", "message": str(e)}
        
        # Kombiner resultater
        combined_result = {
            "sync_result": sync_result,
            "fit_data_result": fit_result,
            "hrv_result": hrv_result,
            "te_result": te_result,
            "summary_result": summary_result,
            "status": "Fullført med FIT-data, HRV, Training Effect og sammendrag",
            "summary": {
                "activities_synced": sync_result.get("total_fetched", 0),
                "fit_data_downloaded": fit_result.get("success_count", 0),
                "fit_data_attempted": fit_result.get("total_count", 0),
                "hrv_synced": hrv_result.get("status") == "Fullført",
                "te_synced": te_result.get("status") == "Fullført",
                "summaries_updated": summary_result.get("status") == "Fullført",
                "metrics_calculated": {
                    "from_sync": sync_result.get("metrics_calculated", {}),
                    "from_fit_data": fit_result.get("metrics_calculated", {})
                },
                "sync_status": sync_result.get("status", "Ukjent"),
                "fit_status": fit_result.get("status", "Ukjent"),
                "hrv_status": hrv_result.get("status", "Ukjent"),
                "te_status": te_result.get("status", "Ukjent"),
                "summary_status": summary_result.get("status", "Ukjent")
            }
        }
        
        logger.info(f"Utvidet synkronisering fullført: {combined_result['summary']}")
        return combined_result

    async def sync_activities(self, start_date: datetime, end_date: datetime, force_refresh_recent: bool = False, ignore_sync_state: bool = False) -> dict:
        """
        Orkestrerer synkronisering av aktiviteter for en gitt tidsperiode og lagrer dem i databasen.
        """
        summary = {"total_fetched": 0, "periods_synced": 0, "status": "Startet"}
        
        try:
            if not await self.garmin_client.initialize():
                logger.error("Kunne ikke initialisere Garmin-klient.")
                summary["status"] = "Feil: Kunne ikke autentisere mot Garmin"
                return summary

            # Inkrementell startdato basert på SyncState, med mulighet for å ignorere
            effective_start = start_date
            if not ignore_sync_state:
                try:
                    act_state = self.db.query(SyncState).filter_by(key="activities").first()
                    if act_state and act_state.last_synced_date and not force_refresh_recent:
                        effective_start = max(
                            effective_start,
                            datetime.combine(act_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
                        )
                except Exception as e:
                    logger.debug(f"Kunne ikke lese SyncState for activities: {e}")

            logger.info(f"Henter aktiviteter fra Garmin: {effective_start.date()} -> {end_date.date()}")
            
            activities_raw = await self.garmin_client.get_activities(effective_start, end_date)
            
            # Filtrer bort duplikater basert på 'activityId'
            existing_ids = self.storage.get_existing_activity_ids(self.db)
            
            # Beregn grensen for "nylige" data (siste 2 dager)
            recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)

            # Inkluder alle aktiviteter, ikke bare de med GPS-data
            # Dette sikrer at styrketrening, indoor cycling, svømming etc. også synkroniseres
            activities_to_save = [
                act for act in activities_raw
                if act.get('activityId') is not None  # Bare sørg for at vi har en gyldig ID
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
                    # Log alle Training Effect-relaterte felter
                    training_fields = [f"{k}: {v}" for k, v in act_data.items() if 'training' in k.lower() or 'effect' in k.lower()]
                    logger.info(f"DEBUG: Training Effect-felter: {training_fields}")
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
                
                # Hvis ignore_sync_state er True (brukt ved manuell synk av valgt periode),
                # skal vi alltid overskrive eksisterende aktiviteter i perioden
                if ignore_sync_state:
                    should_skip = False
                    if activity_id in existing_ids:
                        logger.info(f"Oppdaterer eksisterende aktivitet {activity_id} (ignore_sync_state=True, overskriver alltid).")
                        existing_activity = self.db.query(Activity).filter_by(activity_id=activity_id).first()
                        if existing_activity:
                            self.db.delete(existing_activity)
                else:
                    # Normal logikk: hopp over hvis ikke nylig, eller oppdater hvis force_refresh_recent
                    should_skip = (activity_id in existing_ids and 
                                  not (force_refresh_recent and is_recent))
                    
                    if activity_id in existing_ids and force_refresh_recent and is_recent:
                        logger.info(f"Oppdaterer eksisterende aktivitet {activity_id} (force_refresh_recent=True).")
                        # Slett eksisterende aktivitet først
                        existing_activity = self.db.query(Activity).filter_by(activity_id=activity_id).first()
                        if existing_activity:
                            self.db.delete(existing_activity)
                
                if should_skip:
                    continue

                # Hent detaljerte data (FIT-fil) - kun for nylige aktiviteter for å unngå timeout
                details_json = None
                if is_recent:  # Kun last ned FIT-data for nylige aktiviteter
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
                                        timestamp = date_parser.parse(timestamp)
                                        if timestamp.tzinfo is None:
                                            timestamp = timestamp.replace(tzinfo=timezone.utc)
                                    elif hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is None:
                                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                                    elif not hasattr(timestamp, 'tzinfo'):
                                        timestamp = datetime.fromisoformat(str(timestamp)).replace(tzinfo=timezone.utc)
                                
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
                else:
                    logger.info(f"Hopper over FIT-data nedlasting for aktivitet {activity_id} (ikke nylig)")

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
                
                # Hent lactate threshold speed fra Garmin-klienten
                lactate_threshold_speed = None
                try:
                    lactate_threshold_speed = await self.garmin_client.get_lactate_threshold_speed()
                except Exception as e:
                    logger.warning(f"Kunne ikke hente lactate threshold speed: {e}")

                # Hent elevation gain fra Garmin API (kan være i ulike felter)
                elevation_gain = (
                    act_data.get('elevationGain') or 
                    act_data.get('totalElevationGain') or 
                    act_data.get('elevationGainMeters') or
                    None
                )
                elevation_loss = (
                    act_data.get('elevationLoss') or 
                    act_data.get('totalElevationLoss') or 
                    act_data.get('elevationLossMeters') or
                    None
                )
                
                # Hvis elevation gain ikke er i aktivitetslisten, prøv å hente fra FIT-data
                if elevation_gain is None and details_json:
                    elevation_gain = details_json.get('total_ascent') or details_json.get('elevation_gain')
                if elevation_loss is None and details_json:
                    elevation_loss = details_json.get('total_descent') or details_json.get('elevation_loss')
                
                # Hvis elevation gain fortsatt mangler, prøv å hente fra activity-service
                if elevation_gain is None and is_recent:
                    try:
                        epoc_data = await self.garmin_client.get_activity_epoc_data(activity_id)
                        if epoc_data:
                            elevation_gain = epoc_data.get('elevation_gain')
                            elevation_loss = elevation_loss or epoc_data.get('elevation_loss')
                    except Exception as e:
                        logger.debug(f"Kunne ikke hente elevation gain fra activity-service for {activity_id}: {e}")

                new_activity = Activity(
                    activity_id=activity_id,
                    activity_name=act_data.get('activityName'),
                    start_time=start_time,
                    distance=act_data.get('distance'),
                    duration=act_data.get('duration'),
                    calories=act_data.get('calories'),
                    vo2_max=act_data.get('vO2MaxValue'),
                    average_heart_rate=act_data.get('averageHR'),
                    average_speed=avg_speed,
                    average_pace=avg_pace,
                    activity_type_id=activity_type_obj.id if activity_type_obj else None,
                    average_running_cadence=act_data.get('averageRunningCadenceInStepsPerMinute'),
                    total_training_effect=act_data.get('trainingEffect'),
                    total_anaerobic_training_effect=act_data.get('anaerobicTrainingEffect'),
                    epoc=act_data.get('activityTrainingLoad'),  # EPOC data
                    lactate_threshold_speed=lactate_threshold_speed,  # Lactate threshold speed
                    total_ascent=elevation_gain,  # Elevation gain i meter
                    total_descent=elevation_loss,  # Elevation loss i meter
                    detailed_metrics=details_json
                )
                self.db.add(new_activity)
                added_count += 1

            self.db.commit()

            # Oppdater lactate threshold for alle løpeaktiviteter hvis det er en ny verdi
            try:
                await self._update_lactate_threshold_for_all_running_activities()
            except Exception as e:
                logger.warning(f"Feil ved oppdatering av lactate threshold for løpeaktiviteter: {e}")

            # Oppdater SyncState for aktiviteter
            try:
                if added_count > 0:
                    # Sett siste synketdato til sluttdatoen vi nettopp ba om, eller siste aktivitet sin dato
                    last_date = end_date.date()
                    try:
                        latest = max(
                            datetime.fromisoformat(a.get('startTimeGMT')).date()
                            for a in activities_to_save if a.get('startTimeGMT')
                        )
                        last_date = latest
                    except Exception:
                        pass
                    act_state = self.db.query(SyncState).filter_by(key="activities").first()
                    if not act_state:
                        act_state = SyncState(key="activities")
                        self.db.add(act_state)
                    act_state.last_synced_date = last_date
                    act_state.last_synced_at = datetime.utcnow()
                    self.db.commit()
            except Exception as e:
                logger.warning(f"Kunne ikke oppdatere SyncState for activities: {e}")
            
            # Beregn ALLE metrics for nye aktiviteter
            logger.info("Starter beregning av alle metrics for nye aktiviteter...")
            metrics_results = []
            for act_data in activities_to_save:
                activity_id = str(act_data.get('activityId'))
                if activity_id and activity_id not in existing_ids:
                    metrics_result = self._calculate_metrics_for_new_activity(activity_id)
                    metrics_results.append(metrics_result)
            
            # Logg resultater
            successful_tss = sum(1 for r in metrics_results if r["tss_calculated"])
            successful_power = sum(1 for r in metrics_results if r["power_calculated"])
            successful_running_economy = sum(1 for r in metrics_results if r["running_economy_calculated"])
            successful_negative_splits = sum(1 for r in metrics_results if r["negative_split_calculated"])
            successful_decouplings = sum(1 for r in metrics_results if r["decoupling_calculated"])
            successful_hrv = sum(1 for r in metrics_results if r["hrv_calculated"])
            
            logger.info(f"📊 Metrics-beregning fullført:")
            logger.info(f"  - TSS: {successful_tss}/{len(metrics_results)}")
            logger.info(f"  - Power: {successful_power}/{len(metrics_results)}")
            logger.info(f"  - Løpsøkonomi: {successful_running_economy}/{len(metrics_results)}")
            logger.info(f"  - Negative split: {successful_negative_splits}/{len(metrics_results)}")
            logger.info(f"  - Decoupling: {successful_decouplings}/{len(metrics_results)}")
            logger.info(f"  - HRV tilgjengelig: {successful_hrv}/{len(metrics_results)}")
            
            summary["total_fetched"] = added_count
            summary["metrics_calculated"] = {
                "tss": successful_tss,
                "power": successful_power,
                "running_economy": successful_running_economy,
                "negative_split": successful_negative_splits,
                "decoupling": successful_decouplings,
                "hrv_available": successful_hrv,
                "total_activities": len(metrics_results)
            }
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
        """Synkroniserer helsedata (HRV, Body Battery) for en gitt periode, inkrementelt."""
        # HRV-data er kun tilgjengelig fra 2023 og fremover
        hrv_start_date = max(start_date, datetime(2023, 1, 1, tzinfo=timezone.utc))
        
        if hrv_start_date > end_date:
            logger.info(f"HRV-synkronisering hoppes over - perioden {start_date.date()} til {end_date.date()} er før 2023")
            return
        
        logger.info(f"Starter synkronisering av helsedata fra {hrv_start_date.date()} til {end_date.date()} (HRV fra 2023)")
        
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
                start_filter = datetime.combine(start_date.date(), datetime.min.time()).replace(tzinfo=timezone.utc)
                end_filter = datetime.combine(end_date.date(), datetime.min.time()).replace(tzinfo=timezone.utc)
                filtered_hrv_df = hrv_df[(hrv_df.index >= start_filter) & (hrv_df.index <= end_filter)]
                existing_dates = set(filtered_hrv_df.index.to_series().dt.date)
                logger.info(f"Fant {len(existing_dates)} eksisterende HRV-datoer innenfor det ønskede tidsrommet.")
            else:
                existing_dates = set()
                logger.info("Ingen eksisterende HRV-data funnet.")
        except Exception as e:
            logger.warning(f"Kunne ikke lese eksisterende HRV-datoer, fortsetter uten duplikatsjekk. Feil: {e}")
            existing_dates = set()

        # Les sist synket dato for HRV for inkrementell henting
        try:
            hrv_state = self.db.query(SyncState).filter_by(key="hrv").first()
            if hrv_state and hrv_state.last_synced_date:
                # Start neste dag etter sist synket, med mindre force_refresh_recent
                hrv_start_effective = datetime.combine(hrv_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc)
                if not force_refresh_recent:
                    hrv_start_date = max(hrv_start_date, hrv_start_effective + timedelta(days=1))
        except Exception:
            pass

        # Hent datoer vi allerede vet ikke har HRV-data (sparer Garmin-kall)
        hrv_missing_dates = {
            r.missing_date for r in self.db.query(HealthDataMissing.missing_date).filter(
                HealthDataMissing.data_type == "hrv",
                HealthDataMissing.missing_date >= hrv_start_date.date(),
                HealthDataMissing.missing_date <= end_date.date()
            ).all()
        }

        current_date = hrv_start_date
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
            if current_date.date() in hrv_missing_dates:
                logger.info(f"Hopper over HRV-data for {date_str} (ingen data sist gang).")
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
                    # (Ikke lagre som manglende – vi fant data)
                else:
                    # Lagre at vi prøvde og fant ingenting
                    try:
                        existing = self.db.query(HealthDataMissing).filter_by(data_type="hrv", missing_date=current_date.date()).first()
                        if not existing:
                            self.db.add(HealthDataMissing(data_type="hrv", missing_date=current_date.date()))
                            self.db.commit()
                        hrv_missing_dates.add(current_date.date())
                    except Exception as add_e:
                        logger.debug(f"Kunne ikke lagre HRV manglende dato {date_str}: {add_e}")
                
                # Liten pause for å unngå rate limiting
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Feil under henting av helsedata for {date_str}: {e}")
            
            current_date += timedelta(days=1)

        if all_hrv_data:
            logger.info(f"Fant {len(all_hrv_data)} nye dager med HRV-data. Lagrer...")
            self.storage.save_hrv_data(all_hrv_data)
            # Oppdater sync state
            try:
                last_date = max(datetime.strptime(d["date"], "%Y-%m-%d").date() for d in all_hrv_data)
                if not 'hrv_state' in locals():
                    hrv_state = self.db.query(SyncState).filter_by(key="hrv").first()
                if not hrv_state:
                    hrv_state = SyncState(key="hrv")
                    self.db.add(hrv_state)
                hrv_state.last_synced_date = last_date
                hrv_state.last_synced_at = datetime.utcnow()
                self.db.commit()
            except Exception as e:
                logger.warning(f"Kunne ikke oppdatere HRV sync state: {e}")
        else:
            logger.info("Ingen nye HRV-data å lagre.") 

        # Body Battery inkrementell synk via database
        try:
            from .body_battery_service import BodyBatteryService
            bb_service = BodyBatteryService(self.garmin_client)
            # Finn startdato for BB (inkrementell)
            bb_state = self.db.query(SyncState).filter_by(key="body_battery").first()
            bb_start_date = hrv_start_date
            if bb_state and bb_state.last_synced_date:
                bb_start_date = max(bb_start_date, datetime.combine(bb_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1))
            bb_start_str = bb_start_date.strftime('%Y-%m-%d')
            bb_end_str = end_date.strftime('%Y-%m-%d')
            logger.info(f"Synkroniserer Body Battery inkrementelt: {bb_start_str} -> {bb_end_str}")
            bb_result = await bb_service.sync_body_battery_data_to_database(self.db, bb_start_str, bb_end_str)
            if (bb_result.get("synced_records", 0) + bb_result.get("updated_records", 0)) > 0:
                # Oppdater sync state
                try:
                    if not bb_state:
                        bb_state = SyncState(key="body_battery")
                        self.db.add(bb_state)
                    bb_state.last_synced_date = datetime.strptime(bb_end_str, '%Y-%m-%d').date()
                    bb_state.last_synced_at = datetime.utcnow()
                    self.db.commit()
                except Exception as e:
                    logger.warning(f"Kunne ikke oppdatere Body Battery sync state: {e}")
        except Exception as e:
            logger.warning(f"Body Battery synk feilet, fortsetter: {e}")

        # Søvn inkrementell synk via database
        try:
            from ..database.models.sleep import Sleep
            sleep_state = self.db.query(SyncState).filter_by(key="sleep").first()
            sleep_start_date = hrv_start_date
            if sleep_state and sleep_state.last_synced_date:
                sleep_start_date = max(sleep_start_date, datetime.combine(sleep_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1))

            existing_sleep_dates = {s.sleep_date for s in self.db.query(Sleep.sleep_date).filter(
                Sleep.sleep_date >= sleep_start_date.date(),
                Sleep.sleep_date <= end_date.date()
            ).all()}
            sleep_missing_dates = {
                r.missing_date for r in self.db.query(HealthDataMissing.missing_date).filter(
                    HealthDataMissing.data_type == "sleep",
                    HealthDataMissing.missing_date >= sleep_start_date.date(),
                    HealthDataMissing.missing_date <= end_date.date()
                ).all()
            }

            logger.info(f"Starter søvn-synk: {sleep_start_date.date()} -> {end_date.date()}")
            current_date = sleep_start_date
            saved = 0
            while current_date <= end_date:
                if current_date.date() in existing_sleep_dates:
                    current_date += timedelta(days=1)
                    continue
                if current_date.date() in sleep_missing_dates:
                    current_date += timedelta(days=1)
                    continue
                try:
                    data = await self.garmin_client.get_sleep_data(current_date)
                    if data and any(data.get(k) for k in ["sleep_time","total_sleep","deep_sleep","light_sleep","rem_sleep","sleep_score"]):
                        # Oppdater/sett i DB
                        sleep_date = current_date.date()
                        row = self.db.query(Sleep).filter_by(sleep_date=sleep_date).first()
                        if not row:
                            from sqlalchemy.sql import func
                            from ..database.models.sleep import Sleep as SleepModel
                            row = SleepModel(sleep_date=sleep_date, created_at=func.now(), updated_at=func.now())
                            self.db.add(row)
                        # lagre i sekunder
                        def to_sec(hours_or_min):
                            if hours_or_min is None:
                                return None
                            # data feltene er i minutter i vår klient; konverter til sekunder
                            return float(hours_or_min) * 60.0
                        row.total_sleep_time = to_sec(data.get("sleep_time")) or to_sec(data.get("total_sleep"))
                        row.deep_sleep_time = to_sec(data.get("deep_sleep"))
                        row.light_sleep_time = to_sec(data.get("light_sleep"))
                        row.rem_sleep_time = to_sec(data.get("rem_sleep"))
                        row.awake_time = to_sec(data.get("awake_time"))
                        row.sleep_score = data.get("sleep_score")
                        from sqlalchemy.sql import func
                        row.updated_at = func.now()
                        saved += 1
                    else:
                        try:
                            existing = self.db.query(HealthDataMissing).filter_by(data_type="sleep", missing_date=current_date.date()).first()
                            if not existing:
                                self.db.add(HealthDataMissing(data_type="sleep", missing_date=current_date.date()))
                                self.db.commit()
                            sleep_missing_dates.add(current_date.date())
                        except Exception as add_e:
                            logger.debug(f"Kunne ikke lagre søvn manglende dato {current_date.date()}: {add_e}")
                except Exception as e:
                    logger.debug(f"Søvn-dag feilet {current_date.date()}: {e}")
                current_date += timedelta(days=1)

            if saved > 0:
                self.db.commit()
                # oppdater sync state
                if not sleep_state:
                    sleep_state = SyncState(key="sleep")
                    self.db.add(sleep_state)
                sleep_state.last_synced_date = end_date.date()
                sleep_state.last_synced_at = datetime.utcnow()
                self.db.commit()
                logger.info(f"Søvn-synk lagret {saved} dager")
        except Exception as e:
            logger.warning(f"Søvn synk feilet: {e}")

        # Stress inkrementell synk til database (for rask grafvisning)
        try:
            from ..database.models import Stress
            stress_state = self.db.query(SyncState).filter_by(key="stress").first()
            stress_start_date = max(start_date, datetime(2020, 1, 1, tzinfo=timezone.utc))
            if stress_state and stress_state.last_synced_date:
                stress_start_date = max(stress_start_date, datetime.combine(stress_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1))

            existing_stress_dates = {s.stress_date for s in self.db.query(Stress.stress_date).filter(
                Stress.stress_date >= stress_start_date.date(),
                Stress.stress_date <= end_date.date()
            ).all()}
            stress_missing_dates = {
                r.missing_date for r in self.db.query(HealthDataMissing.missing_date).filter(
                    HealthDataMissing.data_type == "stress",
                    HealthDataMissing.missing_date >= stress_start_date.date(),
                    HealthDataMissing.missing_date <= end_date.date()
                ).all()
            }

            logger.info(f"Starter stress-synk: {stress_start_date.date()} -> {end_date.date()} (mangler {max(0, (end_date - stress_start_date).days + 1 - len(existing_stress_dates) - len(stress_missing_dates))} dager)")
            current_date = stress_start_date
            saved = 0
            while current_date <= end_date:
                if current_date.date() in existing_stress_dates:
                    current_date += timedelta(days=1)
                    continue
                if current_date.date() in stress_missing_dates:
                    current_date += timedelta(days=1)
                    continue
                try:
                    stress_data = await self.garmin_client.get_stress_data(current_date)
                    if stress_data and (stress_data.get('stress_time') or stress_data.get('rest_time')):
                        def to_sec(m):
                            if m is None: return None
                            return float(m) * 60.0
                        row = Stress(
                            stress_date=current_date.date(),
                            stress_level=stress_data.get('stress_level'),
                            total_time=to_sec(stress_data.get('total_time')),
                            stress_time=to_sec(stress_data.get('stress_time')),
                            rest_time=to_sec(stress_data.get('rest_time')),
                            low_stress_time=to_sec(stress_data.get('low_stress_time')),
                            medium_stress_time=to_sec(stress_data.get('medium_stress_time')),
                            high_stress_time=to_sec(stress_data.get('high_stress_time')),
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                        )
                        self.db.add(row)
                        saved += 1
                    else:
                        try:
                            existing = self.db.query(HealthDataMissing).filter_by(data_type="stress", missing_date=current_date.date()).first()
                            if not existing:
                                self.db.add(HealthDataMissing(data_type="stress", missing_date=current_date.date()))
                                self.db.commit()
                            stress_missing_dates.add(current_date.date())
                        except Exception as add_e:
                            logger.debug(f"Kunne ikke lagre stress manglende dato {current_date.date()}: {add_e}")
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.debug(f"Stress-dag feilet {current_date.date()}: {e}")
                current_date += timedelta(days=1)

            if saved > 0:
                self.db.commit()
                if not stress_state:
                    stress_state = SyncState(key="stress")
                    self.db.add(stress_state)
                stress_state.last_synced_date = end_date.date()
                stress_state.last_synced_at = datetime.utcnow()
                self.db.commit()
                logger.info(f"Stress-synk lagret {saved} dager")
        except Exception as e:
            logger.warning(f"Stress synk feilet: {e}")

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
                        timestamp = date_parser.parse(timestamp)
                        if timestamp.tzinfo is None:
                            timestamp = timestamp.replace(tzinfo=timezone.utc)
                    elif hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    elif not hasattr(timestamp, 'tzinfo'):
                        timestamp = datetime.fromisoformat(str(timestamp)).replace(tzinfo=timezone.utc)
                
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
                activity = self.db.query(Activity).filter_by(activity_id=activity_id).first()
                if activity:
                    activity.detailed_metrics = details_json
                    self.db.commit()
                    logger.info(f"Oppdaterte database med FIT-data for aktivitet {activity_id}")
                    
                    # Beregn metrics for aktiviteten siden vi nå har FIT-data
                    logger.info(f"Beregner metrics for aktivitet {activity_id} etter FIT-data nedlasting...")
                    metrics_result = self._calculate_metrics_for_new_activity(str(activity_id))
                    logger.info(f"Metrics-beregning for aktivitet {activity_id}: Negative split={metrics_result['negative_split_calculated']}, Decoupling={metrics_result['decoupling_calculated']}")
                
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
                    existing_parquet_df = pl.read_parquet('data/activity_details.parquet')
                    existing_fit_activity_ids = set(existing_parquet_df['activity_id'].unique())
                except:
                    existing_fit_activity_ids = set()
                
                # Hent alle aktiviteter fra database og sjekk details-felt
                query = self.db.query(Activity.activity_id, Activity.detailed_metrics).order_by(Activity.activity_id.desc())
                if limit:
                    query = query.limit(limit * 3)  # Hent flere siden mange kan mangle FIT-data
                
                all_activities = query.all()
                
                # Finn aktiviteter som mangler FIT-data (enten i parquet eller details)
                activity_ids = []
                for activity in all_activities:
                    activity_id = activity.activity_id
                    has_parquet_data = activity_id in existing_fit_activity_ids
                    has_db_details = activity.detailed_metrics is not None and activity.detailed_metrics != {} and 'records' in str(activity.detailed_metrics)
                    
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
            metrics_calculated = {"negative_split": 0, "decoupling": 0, "hrv_available": 0}
            
            for i, activity_id in enumerate(activity_ids):
                logger.info(f"Prosesserer aktivitet {activity_id} ({i+1}/{total_count})")
                
                if await self._download_and_store_fit_file(activity_id):
                    success_count += 1
                    
                    # Sjekk om metrics ble beregnet for denne aktiviteten
                    try:
                        metrics_result = self._calculate_metrics_for_new_activity(str(activity_id))
                        if metrics_result["negative_split_calculated"]:
                            metrics_calculated["negative_split"] += 1
                        if metrics_result["decoupling_calculated"]:
                            metrics_calculated["decoupling"] += 1
                        if metrics_result["hrv_calculated"]:
                            metrics_calculated["hrv_available"] += 1
                    except Exception as e:
                        logger.warning(f"Kunne ikke sjekke metrics for aktivitet {activity_id}: {e}")
                
                # Liten pause for å unngå rate limiting
                await asyncio.sleep(0.5)
            
            message = f"Lastet ned FIT-data for {success_count} av {total_count} aktiviteter"
            logger.info(message)
            logger.info(f"📊 Metrics beregnet: Negative split={metrics_calculated['negative_split']}, Decoupling={metrics_calculated['decoupling']}, HRV={metrics_calculated['hrv_available']}")
            
            return {
                "status": "Fullført",
                "message": message,
                "success_count": success_count,
                "total_count": total_count,
                "metrics_calculated": metrics_calculated
            }
            
        except Exception as e:
            logger.error(f"Feil under FIT-data nedlasting: {e}")
            return {"status": "Feil", "message": str(e)}

    async def download_fit_data_for_period(self, start_date: datetime, end_date: datetime):
        """Laster ned FIT-data for aktiviteter i en spesifikk periode."""
        if not await self.garmin_client.initialize():
            logger.error("Kunne ikke initialisere Garmin-klient for FIT-nedlasting.")
            return {"status": "Feil", "message": "Kunne ikke initialisere Garmin-klient"}

        try:
            # Finn eksisterende FIT-data
            try:
                existing_parquet_df = pl.read_parquet('data/activity_details.parquet')
                existing_fit_activity_ids = set(existing_parquet_df['activity_id'].unique())
            except:
                existing_fit_activity_ids = set()
            
            # Hent aktiviteter i perioden fra database
            from sqlalchemy import and_
            activities_in_period = self.db.query(Activity.activity_id, Activity.start_time, Activity.activity_name).filter(
                and_(
                    Activity.start_time >= start_date,
                    Activity.start_time <= end_date
                )
            ).order_by(Activity.start_time.desc()).all()
            
            logger.info(f"Fant {len(activities_in_period)} aktiviteter i perioden {start_date.date()} til {end_date.date()}")
            
            # Finn aktiviteter som mangler FIT-data (enten i parquet eller details)
            missing_fit_activities = []
            for activity in activities_in_period:
                has_parquet_data = activity.activity_id in existing_fit_activity_ids
                
                # Sjekk også om aktiviteten har details i database
                db_activity = self.db.query(Activity.detailed_metrics).filter_by(activity_id=activity.activity_id).first()
                has_db_details = db_activity and db_activity.detailed_metrics is not None and db_activity.detailed_metrics != {} and 'records' in str(db_activity.detailed_metrics)
                
                if not (has_parquet_data and has_db_details):
                    missing_fit_activities.append(activity)
            
            logger.info(f"Av disse mangler {len(missing_fit_activities)} aktiviteter FIT-data")
            
            if not missing_fit_activities:
                return {"status": "Fullført", "message": "Alle aktiviteter i perioden har allerede FIT-data"}
            
            success_count = 0
            total_count = len(missing_fit_activities)
            metrics_calculated = {"negative_split": 0, "decoupling": 0, "hrv_available": 0}
            
            for i, activity in enumerate(missing_fit_activities):
                logger.info(f"Prosesserer aktivitet {activity.activity_id} ({i+1}/{total_count}) - {activity.start_time.strftime('%Y-%m-%d')} - {activity.activity_name}")
                
                if await self._download_and_store_fit_file(activity.activity_id):
                    success_count += 1
                    
                    # Sjekk om metrics ble beregnet for denne aktiviteten
                    try:
                        metrics_result = self._calculate_metrics_for_new_activity(str(activity.activity_id))
                        if metrics_result["negative_split_calculated"]:
                            metrics_calculated["negative_split"] += 1
                        if metrics_result["decoupling_calculated"]:
                            metrics_calculated["decoupling"] += 1
                        if metrics_result["hrv_calculated"]:
                            metrics_calculated["hrv_available"] += 1
                    except Exception as e:
                        logger.warning(f"Kunne ikke sjekke metrics for aktivitet {activity.activity_id}: {e}")
                
                # Liten pause for å unngå rate limiting
                await asyncio.sleep(1)
            
            message = f"Lastet ned FIT-data for {success_count} av {total_count} aktiviteter i perioden {start_date.date()} til {end_date.date()}"
            logger.info(message)
            logger.info(f"📊 Metrics beregnet: Negative split={metrics_calculated['negative_split']}, Decoupling={metrics_calculated['decoupling']}, HRV={metrics_calculated['hrv_available']}")
            
            return {
                "status": "Fullført", 
                "message": message,
                "success_count": success_count,
                "total_count": total_count,
                "period": f"{start_date.date()} til {end_date.date()}",
                "metrics_calculated": metrics_calculated
            }
            
        except Exception as e:
            logger.error(f"Feil under FIT-data nedlasting for periode: {e}")
            return {"status": "Feil", "message": str(e)} 

    async def sync_training_effect_data(
        self,
        start_date: datetime,
        end_date: datetime,
        force_refresh_recent: bool = False,
        ignore_sync_state: bool = False,
    ) -> dict:
        """
        Synkroniserer Training Effect data for aktiviteter i en gitt periode.

        Args:
            start_date: Startdato for synkronisering
            end_date: Sluttdato for synkronisering
            force_refresh_recent: Om nylige data skal oppdateres selv om de eksisterer
            ignore_sync_state: Bruk hele perioden (ikke inkrementell), viktig ved full resync
        """
        effective_start = start_date
        if not ignore_sync_state:
            try:
                te_state = self.db.query(SyncState).filter_by(key="training_effect").first()
                if te_state and te_state.last_synced_date and not force_refresh_recent:
                    effective_start = max(
                        effective_start,
                        datetime.combine(te_state.last_synced_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
                    )
            except Exception as e:
                logger.debug(f"Kunne ikke lese SyncState for training_effect: {e}")

        logger.info(f"Starter Training Effect synkronisering for perioden {effective_start.date()} til {end_date.date()}")
        
        try:
            if not await self.garmin_client.initialize():
                logger.error("Kunne ikke initialisere Garmin-klient for Training Effect synkronisering.")
                return {"status": "Feil", "message": "Kunne ikke autentisere mot Garmin"}
            
            # Finn alltid siste aktivitet (globalt) og tving oppdatering for den,
            # uavhengig av valgt periode. Dette sikrer komplette verdier på nyeste økt.
            latest_activity = self.db.query(Activity).order_by(Activity.start_time.desc()).first()
            latest_activity_id = str(latest_activity.activity_id) if latest_activity else None

            # Hent aktiviteter fra databasen i den gitte perioden
            activities = self.db.query(Activity).filter(
                Activity.start_time >= effective_start,
                Activity.start_time <= end_date
            ).order_by(Activity.start_time.desc()).all()
            
            logger.info(f"Fant {len(activities)} aktiviteter i perioden {start_date.date()} til {end_date.date()}")
            
            # Beregn grensen for "nylige" data (siste 2 dager)
            recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)
            
            updated_count = 0
            skipped_count = 0
            failed_count = 0
            
            for i, activity in enumerate(activities, 1):
                activity_id = str(activity.activity_id)
                activity_start_time = activity.start_time
                
                # Sjekk om aktiviteten er nylig og om vi skal force refresh
                # Sørg for at begge datetimes har samme timezone-oppsett
                if activity_start_time.tzinfo is None:
                    activity_start_time = activity_start_time.replace(tzinfo=timezone.utc)
                is_recent = activity_start_time >= recent_cutoff
                # Ikke hopp over hvis dette er aller siste aktivitet (skal alltid oppdateres)
                is_latest = (latest_activity_id is not None and activity_id == latest_activity_id)
                # Behandle 0 som manglende – gyldig TE er 1.0–5.0
                has_valid_te = (
                    (activity.total_training_effect is not None and activity.total_training_effect > 0) or
                    (activity.total_anaerobic_training_effect is not None and activity.total_anaerobic_training_effect > 0)
                )
                # Skip hvis aktiviteten har gyldig TE og ikke er nylig og ikke er siste aktivitet
                if has_valid_te and not (force_refresh_recent and is_recent) and not is_latest:
                    skipped_count += 1
                    continue
                
                logger.info(f"Prosesserer Training Effect for aktivitet {activity_id} ({i}/{len(activities)}) - {activity.activity_name}")
                
                try:
                    # Hent Training Effect data
                    te_data = await self.garmin_client.get_activity_training_effect(activity_id)
                    if te_data:
                        activity.total_training_effect = te_data.get('aerobic_training_effect')
                        activity.total_anaerobic_training_effect = te_data.get('anaerobic_training_effect')
                    
                    # Hent EPOC data
                    epoc_data = await self.garmin_client.get_activity_epoc_data(activity_id)
                    if epoc_data:
                        activity.epoc = epoc_data.get('activity_training_load')
                    
                    # Oppdater databasen
                    logger.info(f"✅ Oppdatert Training Effect for aktivitet {activity_id}: "
                              f"Aerobic={activity.total_training_effect}, "
                              f"Anaerobic={activity.total_anaerobic_training_effect}")
                    
                    updated_count += 1
                except Exception as e:
                    logger.error(f"❌ Feil ved henting av Training Effect for aktivitet {activity_id}: {e}")
                    failed_count += 1
            
            # Lagre endringene til databasen
            self.db.commit()

            # Oppdater SyncState for training_effect
            try:
                if updated_count > 0:
                    te_state = self.db.query(SyncState).filter_by(key="training_effect").first()
                    if not te_state:
                        te_state = SyncState(key="training_effect")
                        self.db.add(te_state)
                    te_state.last_synced_date = end_date.date()
                    te_state.last_synced_at = datetime.utcnow()
                    self.db.commit()
            except Exception as e:
                logger.warning(f"Kunne ikke oppdatere SyncState for training_effect: {e}")
            
            result = {
                "status": "Fullført",
                "message": f"Training Effect synkronisering fullført: {updated_count} oppdatert, {skipped_count} hoppet over, {failed_count} feilet",
                "updated_count": updated_count,
                "skipped_count": skipped_count,
                "failed_count": failed_count,
                "total_processed": len(activities)
            }
            
            logger.info(f"Training Effect synkronisering fullført: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Feil under Training Effect synkronisering: {e}")
            return {"status": "Feil", "message": str(e)}

    async def sync_training_effect_for_missing(self, force: bool = False) -> dict:
        """
        Henter Training Effect fra Garmin for aktiviteter som mangler eller har 0.
        Gyldig TE er 1.0–5.0. Brukes for å fikse aktiviteter som viser 0 i frontend.
        """
        from sqlalchemy import or_, desc
        try:
            if not await self.garmin_client.initialize():
                return {"status": "Feil", "message": "Kunne ikke autentisere mot Garmin"}
            if force:
                activities = self.db.query(Activity).order_by(desc(Activity.start_time)).all()
            else:
                activities = self.db.query(Activity).filter(
                    or_(
                        or_(
                            Activity.total_training_effect.is_(None),
                            Activity.total_training_effect <= 0,
                        ),
                        or_(
                            Activity.total_anaerobic_training_effect.is_(None),
                            Activity.total_anaerobic_training_effect <= 0,
                        ),
                    )
                ).order_by(desc(Activity.start_time)).all()
            updated = 0
            failed = 0
            for i, act in enumerate(activities, 1):
                try:
                    te_data = await self.garmin_client.get_activity_training_effect(str(act.activity_id))
                    if te_data:
                        act.total_training_effect = te_data.get("aerobic_training_effect")
                        act.total_anaerobic_training_effect = te_data.get("anaerobic_training_effect")
                        updated += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning(f"TE feil for {act.activity_id}: {e}")
                    failed += 1
            self.db.commit()
            return {
                "status": "Fullført",
                "message": f"{updated} oppdatert, {failed} feilet",
                "updated_count": updated,
                "failed_count": failed,
                "total_processed": len(activities),
            }
        except Exception as e:
            logger.error(f"Feil ved TE-for-missing sync: {e}", exc_info=True)
            return {"status": "Feil", "message": str(e)}

    def _calculate_metrics_for_new_activity(self, activity_id: str) -> dict:
        """
        Beregner og lagrer ALLE beregnede verdier for en ny aktivitet.
        Sjekker først om verdier allerede finnes i databasen for å unngå unødvendige beregninger.
        Returnerer en ordbok med resultater.
        """
        results = {
            "activity_id": activity_id,
            "tss_calculated": False,
            "power_calculated": False,
            "running_economy_calculated": False,
            "negative_split_calculated": False,
            "decoupling_calculated": False,
            "hrv_calculated": False,
            "errors": []
        }
        
        try:
            activity_id_int = int(activity_id)
            
            # Hent aktiviteten fra databasen
            activity = self.db.query(Activity).filter_by(activity_id=activity_id).first()
            if not activity:
                results["errors"].append("Aktivitet ikke funnet i database")
                return results
            
            # 1. TSS (Training Stress Score) - sjekk om det allerede finnes
            if activity.training_stress_score is None:
                try:
                    from ..services.training_stress_service import TrainingStressService
                    tss_service = TrainingStressService(self.db)
                    tss = tss_service.calculate_tss_for_activity(activity)
                    if tss is not None:
                        activity.training_stress_score = tss
                        results["tss_calculated"] = True
                        logger.info(f"✅ Beregnet TSS for aktivitet {activity_id}: {tss}")
                except Exception as e:
                    logger.warning(f"Feil ved beregning av TSS for aktivitet {activity_id}: {e}")
                    results["errors"].append(f"TSS feil: {str(e)}")
            else:
                logger.debug(f"TSS finnes allerede for aktivitet {activity_id}: {activity.training_stress_score}")
            
            # 2. Power (kun for løpeaktiviteter) - sjekk om det allerede finnes
            if activity.activity_type and activity.activity_type.type_key == 'running':
                if activity.average_power is None:
                    try:
                        from ..services.power_service import PowerService
                        power_service = PowerService(self.storage)
                        power_data = power_service.calculate_activity_power(activity_id_int, self.db)
                        if power_data:
                            # Power lagres automatisk i calculate_activity_power
                            results["power_calculated"] = True
                            logger.info(f"✅ Beregnet power for aktivitet {activity_id}: {power_data.get('average_power_watts')}W")
                    except Exception as e:
                        logger.warning(f"Feil ved beregning av power for aktivitet {activity_id}: {e}")
                        results["errors"].append(f"Power feil: {str(e)}")
                else:
                    logger.debug(f"Power finnes allerede for aktivitet {activity_id}: {activity.average_power}W")
            
            # 3. Running Economy (hastighet/puls-forhold)
            if activity.activity_type and 'running' in activity.activity_type.type_key:
                if activity.running_economy is None:
                    try:
                        if activity.average_speed and activity.average_heart_rate and activity.average_speed > 0 and activity.average_heart_rate > 0:
                            # Running economy = (speed in km/h / HR) * 100
                            speed_kmh = activity.average_speed * 3.6
                            running_economy = (speed_kmh / activity.average_heart_rate) * 100
                            activity.running_economy = round(running_economy, 2)
                            results["running_economy_calculated"] = True
                            logger.info(f"✅ Beregnet løpsøkonomi for aktivitet {activity_id}: {running_economy}")
                    except Exception as e:
                        logger.warning(f"Feil ved beregning av løpsøkonomi for aktivitet {activity_id}: {e}")
                        results["errors"].append(f"Running economy feil: {str(e)}")
                else:
                    logger.debug(f"Løpsøkonomi finnes allerede for aktivitet {activity_id}: {activity.running_economy}")
            
            # 4. Negative split (fra FIT-data hvis tilgjengelig)
            if activity.negative_split_percent is None:
                try:
                    negative_split_result = self.analysis_service.calculate_negative_split(activity_id_int, self.db)
                    if negative_split_result and 'negative_split_percent' in negative_split_result:
                        results["negative_split_calculated"] = True
                        logger.info(f"✅ Beregnet negative split for aktivitet {activity_id}: {negative_split_result.get('negative_split_percent')}%")
                except Exception as e:
                    logger.debug(f"Kunne ikke beregne negative split for aktivitet {activity_id}: {e}")
            else:
                logger.debug(f"Negative split finnes allerede for aktivitet {activity_id}: {activity.negative_split_percent}%")
            
            # 5. Decoupling (fra FIT-data hvis tilgjengelig)
            if activity.decoupling_percent is None:
                try:
                    decoupling_result = self.analysis_service.calculate_decoupling(activity_id_int, self.db)
                    if decoupling_result and 'decoupling_percent' in decoupling_result:
                        results["decoupling_calculated"] = True
                        logger.info(f"✅ Beregnet decoupling for aktivitet {activity_id}: {decoupling_result.get('decoupling_percent')}%")
                except Exception as e:
                    logger.debug(f"Kunne ikke beregne decoupling for aktivitet {activity_id}: {e}")
            else:
                logger.debug(f"Decoupling finnes allerede for aktivitet {activity_id}: {activity.decoupling_percent}%")
            
            # 6. HRV-sjekk (HRV hentes separat via sync_health_data)
            try:
                if activity.start_time:
                    # HRV-data er kun tilgjengelig fra 2023
                    if activity.start_time.year >= 2023:
                        hrv_data = self.analysis_service.get_hrv_for_activity_date(activity_id_int, self.db)
                        if hrv_data and hrv_data.get('last_night_avg'):
                            results["hrv_calculated"] = True
                            logger.debug(f"HRV-data tilgjengelig for aktivitet {activity_id}: {hrv_data.get('last_night_avg')}ms")
            except Exception as e:
                logger.debug(f"HRV-sjekk for aktivitet {activity_id}: {e}")
            
            # Commit alle endringer til databasen
            try:
                self.db.commit()
                logger.info(f"💾 Lagret alle beregnede verdier for aktivitet {activity_id}")
            except Exception as e:
                self.db.rollback()
                logger.error(f"Feil ved lagring av beregnede verdier for aktivitet {activity_id}: {e}")
                results["errors"].append(f"Lagringsfeil: {str(e)}")
            
        except Exception as e:
            logger.error(f"Generell feil ved beregning av metrics for aktivitet {activity_id}: {e}")
            results["errors"].append(f"Generell feil: {str(e)}")
        
        return results

    async def _update_lactate_threshold_for_all_running_activities(self):
        """
        Oppdaterer lactate threshold for alle løpeaktiviteter når en ny verdi oppdages.
        Hvis det er en ny verdi fra Garmin, oppdateres alle løpeaktiviteter som mangler eller har en annen verdi.
        """
        try:
            # Hent den nåværende lactate threshold verdien fra Garmin
            current_lactate_threshold = await self.garmin_client.get_lactate_threshold_speed()
            
            if current_lactate_threshold is None:
                logger.debug("Ingen lactate threshold verdi tilgjengelig fra Garmin, hopper over oppdatering")
                return
            
            logger.info(f"🔍 Sjekker lactate threshold oppdatering. Nåværende verdi fra Garmin: {current_lactate_threshold} m/s")
            
            # Finn alle løpeaktiviteter (inkluderer running, treadmill_running, trail_running, etc.)
            from sqlalchemy import or_
            running_activities = self.db.query(Activity).join(ActivityType).filter(
                or_(
                    ActivityType.type_key == 'running',
                    ActivityType.type_key == 'treadmill_running',
                    ActivityType.type_key == 'trail_running',
                    ActivityType.type_key == 'street_running',
                    ActivityType.parent_type_key == 'running'
                )
            ).all()
            
            if not running_activities:
                logger.debug("Ingen løpeaktiviteter funnet")
                return
            
            # Finn aktiviteter som mangler lactate threshold eller har en annen verdi
            activities_to_update = []
            for activity in running_activities:
                if activity.lactate_threshold_speed is None:
                    activities_to_update.append(activity)
                elif abs(activity.lactate_threshold_speed - current_lactate_threshold) > 0.0001:
                    # Verdi er forskjellig (med en liten toleranse for flyttall)
                    activities_to_update.append(activity)
            
            if not activities_to_update:
                logger.debug(f"Alle {len(running_activities)} løpeaktiviteter har allerede riktig lactate threshold verdi ({current_lactate_threshold} m/s)")
                return
            
            logger.info(f"📝 Oppdaterer lactate threshold for {len(activities_to_update)} løpeaktiviteter til {current_lactate_threshold} m/s")
            
            # Oppdater alle aktiviteter
            updated_count = 0
            for activity in activities_to_update:
                old_value = activity.lactate_threshold_speed
                activity.lactate_threshold_speed = current_lactate_threshold
                updated_count += 1
                
                if updated_count <= 5:  # Logg de første 5 for debugging
                    logger.info(f"  - Aktivitet {activity.activity_id} ({activity.start_time.date()}): {old_value} -> {current_lactate_threshold} m/s")
            
            # Commit endringene
            self.db.commit()
            logger.info(f"✅ Oppdatert lactate threshold for {updated_count} løpeaktiviteter til {current_lactate_threshold} m/s")
            
        except Exception as e:
            logger.error(f"Feil ved oppdatering av lactate threshold for løpeaktiviteter: {e}", exc_info=True)
            self.db.rollback()
            raise 