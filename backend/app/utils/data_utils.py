from datetime import datetime, timezone, timedelta
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)

def convert_timestamps_to_datetime(timestamp_data: Any) -> Optional[datetime]:
    """
    Forsøker å konvertere ulike tidsstempelformater til et UTC datetime-objekt.
    Håndterer:
    - ISO 8601 strenger (med eller uten 'Z', med eller uten millisekunder)
    - Unix timestamps (heltall eller flyttall)
    - Eksisterende datetime-objekter (konverterer til UTC om naivt eller annet tz)
    """
    if timestamp_data is None:
        return None

    if isinstance(timestamp_data, datetime):
        if timestamp_data.tzinfo is None:
            return timestamp_data.replace(tzinfo=timezone.utc)
        return timestamp_data.astimezone(timezone.utc)

    if isinstance(timestamp_data, (int, float)):
        try:
            # Anta at det er et Unix-tidsstempel (sekunder siden epoch)
            return datetime.fromtimestamp(timestamp_data, tz=timezone.utc)
        except (OSError, OverflowError, ValueError) as e:
            logger.debug(f"Kunne ikke konvertere tall {timestamp_data} til datetime (som Unix timestamp): {e}")
            pass # Prøv andre metoder hvis dette feiler

    if isinstance(timestamp_data, str):
        # Prøv ISO 8601 format, inkludert de med 'Z'
        formats_to_try = [
            "%Y-%m-%dT%H:%M:%S.%fZ",  # Med millisekunder og Z
            "%Y-%m-%dT%H:%M:%SZ",    # Uten millisekunder og Z
            "%Y-%m-%dT%H:%M:%S.%f",   # Med millisekunder, uten Z (anta UTC)
            "%Y-%m-%dT%H:%M:%S",     # Uten millisekunder, uten Z (anta UTC)
            "%Y-%m-%d %H:%M:%S.%f",  # Med mellomrom og millisekunder
            "%Y-%m-%d %H:%M:%S"       # Med mellomrom, uten millisekunder
        ]
        for fmt in formats_to_try:
            try:
                dt_obj = datetime.strptime(timestamp_data, fmt)
                # Hvis formatet ikke inkluderer tidssoneinfo (som 'Z' eller %z), anta UTC
                if dt_obj.tzinfo is None:
                     # Hvis formatet slutter på Z, har strptime noen ganger problemer.
                     # Hvis den originale strengen slutter på Z, og dt_obj er naivt, sett UTC.
                    if timestamp_data.endswith('Z'):
                        return dt_obj.replace(tzinfo=timezone.utc)
                    # Ellers, hvis det er en standard format uten Z, og vi antar UTC for disse:
                    if not ('%z' in fmt or '%Z' in fmt):
                         return dt_obj.replace(tzinfo=timezone.utc)
                return dt_obj.astimezone(timezone.utc) # Konverter til UTC hvis det har en annen tidssone
            except ValueError:
                continue
        logger.warning(f"Kunne ikke parse streng '{timestamp_data}' til datetime med kjente formater.")
        return None

    logger.warning(f"Ugyldig type for tidsstempelkonvertering: {type(timestamp_data)}. Data: {timestamp_data}")
    return None


def is_data_fresh(timestamp: Optional[datetime], max_age_seconds: int = 3600) -> bool:
    """
    Sjekker om et gitt UTC datetime-objekt er 'ferskt' basert på max_age_seconds.
    Returnerer True hvis timestamp er nyere enn (nåværende UTC tid - max_age_seconds).
    Returnerer False hvis timestamp er None, eller eldre.
    """
    if not timestamp:
        return False
    
    # Sørg for at timestamp er UTC
    if timestamp.tzinfo is None or timestamp.tzinfo.utcoffset(timestamp) != timezone.utc:
        logger.warning(f"is_data_fresh mottok et ikke-UTC datetime: {timestamp}. Behandler som ikke-fersk.")
        # Strengt tatt bør dette ikke skje hvis convert_timestamps_to_datetime brukes korrekt.
        # Vurder å konvertere her, eller bare returnere False. For nå, False.
        return False

    current_utc_time = datetime.now(timezone.utc)
    allowed_age = timedelta(seconds=max_age_seconds)
    
    return (current_utc_time - timestamp) < allowed_age 