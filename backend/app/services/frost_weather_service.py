from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import requests


logger = logging.getLogger(__name__)


class FrostWeatherService:
    """Henter historiske observasjoner fra MET Frost."""

    SOURCES_URL = "https://frost.met.no/sources/v0.jsonld"
    OBSERVATIONS_URL = "https://frost.met.no/observations/v0.jsonld"
    ELEMENTS = (
        "air_temperature",
        "wind_speed",
        "wind_from_direction",
        "relative_humidity",
    )

    def __init__(self, client_id: str, timeout_seconds: float = 10.0):
        self.client_id = client_id.strip()
        self.timeout_seconds = timeout_seconds
        self._source_cache: Dict[Tuple[float, float, str], Optional[str]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.client_id)

    async def get_weather_snapshot(
        self,
        *,
        target_time: datetime,
        latitude: float,
        longitude: float,
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None

        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)
        else:
            target_time = target_time.astimezone(timezone.utc)

        source_id = await self._get_nearest_source(latitude, longitude, target_time)
        if not source_id:
            return None

        return await self._get_observations(source_id, target_time)

    async def _get_nearest_source(
        self,
        latitude: float,
        longitude: float,
        target_time: datetime,
    ) -> Optional[str]:
        cache_key = (round(float(latitude), 3), round(float(longitude), 3), target_time.date().isoformat())
        if cache_key in self._source_cache:
            return self._source_cache[cache_key]

        params = {
            "types": "SensorSystem",
            "elements": ",".join(self.ELEMENTS),
            "geometry": f"nearest(POINT({float(longitude):.4f} {float(latitude):.4f}))",
            "nearestmaxcount": "5",
            "validtime": target_time.date().isoformat(),
            "fields": "id,name,geometry,distance,validFrom,validTo",
        }

        def _request() -> Dict[str, Any]:
            response = requests.get(
                self.SOURCES_URL,
                params=params,
                auth=(self.client_id, ""),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

        try:
            payload = await asyncio.to_thread(_request)
        except Exception as exc:
            logger.warning("Frost source lookup feilet for lat=%s lon=%s: %s", latitude, longitude, exc)
            self._source_cache[cache_key] = None
            return None

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or not data:
            self._source_cache[cache_key] = None
            return None

        source_id = data[0].get("id")
        self._source_cache[cache_key] = source_id
        return source_id

    async def _get_observations(
        self,
        source_id: str,
        target_time: datetime,
    ) -> Optional[Dict[str, Any]]:
        start_time = (target_time - timedelta(hours=2)).replace(microsecond=0)
        end_time = (target_time + timedelta(hours=2)).replace(microsecond=0)
        params = {
            "sources": source_id,
            "elements": ",".join(self.ELEMENTS),
            "referencetime": f"{start_time.isoformat()}/{end_time.isoformat()}",
        }

        def _request() -> Dict[str, Any]:
            response = requests.get(
                self.OBSERVATIONS_URL,
                params=params,
                auth=(self.client_id, ""),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

        try:
            payload = await asyncio.to_thread(_request)
        except Exception as exc:
            logger.warning("Frost observations feilet for source=%s: %s", source_id, exc)
            return None

        return self._parse_observations_payload(
            source_id=source_id,
            payload=payload,
            target_time=target_time,
        )

    def _parse_observations_payload(
        self,
        *,
        source_id: str,
        payload: Dict[str, Any],
        target_time: datetime,
    ) -> Optional[Dict[str, Any]]:
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)
        else:
            target_time = target_time.astimezone(timezone.utc)

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or not data:
            return None

        best = None
        best_distance = None
        for item in data:
            if not isinstance(item, dict):
                continue
            raw_time = item.get("referenceTime")
            if not isinstance(raw_time, str):
                continue
            try:
                parsed_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed_time.tzinfo is None:
                parsed_time = parsed_time.replace(tzinfo=timezone.utc)
            distance = abs((parsed_time - target_time).total_seconds())
            if best_distance is None or distance < best_distance:
                best = item
                best_distance = distance

        if best is None:
            return None

        observations = best.get("observations")
        if not isinstance(observations, list):
            return None

        values: Dict[str, Any] = {}
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            element_id = obs.get("elementId")
            value = obs.get("value")
            if element_id and value is not None and element_id not in values:
                values[element_id] = value

        if not any(values.get(field) is not None for field in self.ELEMENTS[:3]):
            return None

        return {
            "temperature": values.get("air_temperature"),
            "wind_speed": values.get("wind_speed"),
            "wind_direction": None if values.get("wind_from_direction") == -3 else values.get("wind_from_direction"),
            "humidity": values.get("relative_humidity"),
            "weather_source": "met_frost",
            "weather_reference_time": best.get("referenceTime"),
            "weather_station_id": source_id,
        }
