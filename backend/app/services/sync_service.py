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

    def _parse_fit_data(self, fit_data: bytes) -> Optional[dict]:
        """Parser FIT-data og konverterer det til en JSON-serialiserbar ordbok."""
        try:
            fitfile = fitparse.FitFile(BytesIO(fit_data))
            records = []
            for record in fitfile.get_messages('record'):
                record_data = {}
                for data in record:
                    if data.value is not None and not isinstance(data.value, str):
                        # Konverterer enheter til strenger for å unngå serialiseringsfeil
                        value = f"{data.value} {data.units}" if data.units else data.value
                        record_data[data.name] = value
                if record_data:
                    records.append(record_data)
            return {"records": records}
        except FitHeaderError:
            # Dette er en forventet feil for aktiviteter uten gyldig datafil.
            logger.warning(f"Kunne ikke parse filen da den mangler gyldig FIT-header. Dette skjer ofte med manuelle aktiviteter. Innhold (start): {fit_data[:100]}")
            return None
        except Exception as e:
            logger.error(f"En uventet feil oppstod under parsing av FIT-fil: {e}", exc_info=True)
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
            
            # Beregn grensen for "nylige" data (siste 30 dager)
            recent_cutoff = datetime.now(timezone.utc) - timedelta(days=30)

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
            return None
        
        summary = hrv_data['hrv_summary']
        
        # Bruk weekly_avg som fallback for baseline-verdier hvis de ikke finnes
        weekly_avg = summary.get('weekly_avg', 0)
        
        return {
            "date": calendar_date,
            "last_night_avg": summary.get('last_night_avg'),
            "last_night_5_min_high": summary.get('last_night_5_min_high', 0),
            "baseline_low_upper": summary.get('baseline_low_upper', weekly_avg * 0.8 if weekly_avg else 0),
            "baseline_balanced_lower": summary.get('baseline_balanced_lower', weekly_avg * 0.9 if weekly_avg else 0),
            "baseline_balanced_upper": summary.get('baseline_balanced_upper', weekly_avg * 1.1 if weekly_avg else 0),
            "status": summary.get('status'),
        }

    async def sync_health_data(self, start_date: datetime, end_date: datetime, force_refresh_recent: bool = False):
        """Synkroniserer helsedata (HRV, etc.) for en gitt periode."""
        logger.info(f"Starter synkronisering av helsedata fra {start_date.date()} til {end_date.date()}")
        
        if not await self.garmin_client.initialize():
            logger.error("Kunne ikke initialisere Garmin-klient for helsedata-synk.")
            return

        all_hrv_data = []
        
        # Beregn grensen for "nylige" data (siste 30 dager)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        
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
                # Hent HRV-data
                hrv_data = await self.garmin_client.get_hrv_data(current_date)
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
        # Implementer funksjonen her 