from datetime import datetime, timedelta
from typing import List, Tuple, Optional
import asyncio
import logging

from .garmin_client import GarminClient
from ..storage import DataStorage

logger = logging.getLogger(__name__)

class SyncService:
    def __init__(self, garmin_client: GarminClient, storage: DataStorage):
        self.garmin_client = garmin_client
        self.storage = storage

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
        Orkestrerer synkronisering av aktiviteter for en gitt tidsperiode.
        """
        summary = {"total_fetched": 0, "periods_synced": 0, "status": "Startet"}
        
        try:
            # 1. Sjekk om Garmin-klienten er klar
            if not await self.garmin_client.initialize():
                logger.error("Kunne ikke initialisere Garmin-klient. Avbryter synkronisering.")
                summary["status"] = "Feil: Kunne ikke autentisere mot Garmin"
                return summary

            # 2. Beregn manglende perioder
            periods_to_fetch = self._calculate_missing_periods(start_date, end_date)
            if not periods_to_fetch:
                summary["status"] = "Allerede à jour"
                return summary

            # 3. Hent og lagre data for hver periode
            for i, (start, end) in enumerate(periods_to_fetch):
                logger.info(f"Henter periode {i+1}/{len(periods_to_fetch)}: {start.date()} -> {end.date()}")
                
                activities = await self.garmin_client.get_activities(start, end)
                
                if activities:
                    logger.info(f"Fant {len(activities)} aktiviteter i perioden.")
                    self.storage.save_activities(activities)
                    summary["total_fetched"] += len(activities)
                else:
                    logger.info("Ingen aktiviteter funnet i denne perioden.")
                
                summary["periods_synced"] += 1
            
            summary["status"] = "Fullført"
            logger.info(f"Synkronisering fullført. Hentet totalt {summary['total_fetched']} nye aktiviteter.")

        except Exception as e:
            logger.critical(f"En alvorlig feil oppstod under synkronisering: {e}", exc_info=True)
            summary["status"] = f"Feil: {e}"
        
        return summary 