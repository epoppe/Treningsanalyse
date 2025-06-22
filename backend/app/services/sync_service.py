from datetime import datetime, timedelta
from typing import List, Tuple, Optional
import asyncio
import logging
from sqlalchemy.orm import Session

from .garmin_client import GarminClient
from ..storage import DataStorage
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
                activity_type_id=activity_type_obj.id if activity_type_obj else None
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

    async def sync_activities(self, start_date: datetime, end_date: datetime) -> dict:
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
            seen_ids = set()
            unique_activities = []
            for act in activities_raw:
                act_id = act.get('activityId')
                if act_id and act_id not in seen_ids:
                    unique_activities.append(act)
                    seen_ids.add(act_id)

            activities_to_save = [
                act for act in unique_activities
                if act.get('distance', 0) is not None and act.get('distance', 0) > 0
            ]

            if not activities_to_save:
                summary["status"] = "Fant ingen nye aktiviteter med GPS-data hos Garmin."
                logger.info(summary["status"])
                return summary

            logger.info(f"Fant {len(activities_to_save)} aktiviteter hos Garmin. Lagrer til database.")
            
            existing_ids = {result[0] for result in self.db.query(Activity.id).all()}
            logger.info(f"DEBUG: Fant {len(existing_ids)} eksisterende ID-er i DB. Sample: {list(existing_ids)[:5]}")

            activity_type_cache = {}
            added_count = 0

            for i, act_data in enumerate(activities_to_save):
                activity_id = str(act_data.get('activityId'))
                
                if i < 5: # Logger de 5 første for feilsøking
                    is_in_db = activity_id in existing_ids
                    logger.info(f"DEBUG: Behandler aktivitet {i+1}/{len(activities_to_save)}: ID='{activity_id}', Finnes i DB? {is_in_db}")

                if not activity_id or activity_id in existing_ids:
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

                new_activity = Activity(
                    id=activity_id,
                    name=act_data.get('activityName'),
                    type=activity_type_key,
                    start_time=datetime.fromisoformat(act_data['startTimeGMT']),
                    distance=act_data.get('distance'),
                    duration=act_data.get('duration'),
                    calories=act_data.get('calories'),
                    vo2_max=act_data.get('vO2MaxValue'),
                    average_hr=act_data.get('averageHR'),
                    average_speed=avg_speed,
                    average_pace=avg_pace,
                    activity_type_id=activity_type_obj.id if activity_type_obj else None
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