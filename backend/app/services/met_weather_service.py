from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import requests


logger = logging.getLogger(__name__)


class MetWeatherService:
    """Henter punktvær fra MET locationforecast."""

    BASE_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"

    def __init__(self, user_agent: str, timeout_seconds: float = 10.0):
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self._forecast_cache: Dict[Tuple[float, float, Optional[int]], Dict[str, Any]] = {}

    async def get_weather_snapshot(
        self,
        *,
        target_time: datetime,
        latitude: float,
        longitude: float,
        altitude: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)
        else:
            target_time = target_time.astimezone(timezone.utc)

        payload = await self._get_location_forecast(latitude, longitude, altitude)
        if not payload:
            return None

        return self._extract_weather_from_payload(payload, target_time)

    async def _get_location_forecast(
        self,
        latitude: float,
        longitude: float,
        altitude: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        altitude_key = int(round(altitude)) if altitude is not None else None
        cache_key = (round(float(latitude), 4), round(float(longitude), 4), altitude_key)
        cached = self._forecast_cache.get(cache_key)
        if cached is not None:
            return cached

        params = {
            "lat": f"{float(latitude):.6f}",
            "lon": f"{float(longitude):.6f}",
        }
        if altitude_key is not None:
            params["altitude"] = str(altitude_key)

        headers = {"User-Agent": self.user_agent}

        def _request() -> Dict[str, Any]:
            response = requests.get(
                self.BASE_URL,
                params=params,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

        try:
            payload = await asyncio.to_thread(_request)
        except Exception as exc:
            logger.warning("MET-værkall feilet for lat=%s lon=%s: %s", latitude, longitude, exc)
            return None

        self._forecast_cache[cache_key] = payload
        return payload

    def _extract_weather_from_payload(
        self,
        payload: Dict[str, Any],
        target_time: datetime,
    ) -> Optional[Dict[str, Any]]:
        properties = payload.get("properties") if isinstance(payload, dict) else None
        timeseries = properties.get("timeseries") if isinstance(properties, dict) else None
        if not isinstance(timeseries, list) or not timeseries:
            return None

        best = None
        best_time = None
        best_distance = None

        for entry in timeseries:
            if not isinstance(entry, dict):
                continue
            raw_time = entry.get("time")
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
                best = entry
                best_time = parsed_time
                best_distance = distance

        if best is None or best_time is None or best_distance is None:
            return None

        # Locationforecast inneholder kun fremtidige tidspunkter — ikke bruk for historiske økter.
        if target_time > best_time + timedelta(hours=1):
            return None

        # Unngå å bruke forecast-punkt som er for langt unna aktivitetstiden.
        if best_distance > timedelta(hours=6).total_seconds():
            return None

        data = best.get("data") if isinstance(best, dict) else None
        instant = data.get("instant") if isinstance(data, dict) else None
        details = instant.get("details") if isinstance(instant, dict) else None
        if not isinstance(details, dict):
            return None

        weather_condition = None
        for key in ("next_1_hours", "next_6_hours", "next_12_hours"):
            period_data = data.get(key) if isinstance(data, dict) else None
            summary = period_data.get("summary") if isinstance(period_data, dict) else None
            symbol_code = summary.get("symbol_code") if isinstance(summary, dict) else None
            if symbol_code:
                weather_condition = symbol_code
                break

        if not any(
            details.get(field) is not None
            for field in ("air_temperature", "wind_speed", "wind_from_direction", "relative_humidity")
        ):
            return None

        return {
            "temperature": details.get("air_temperature"),
            "wind_speed": details.get("wind_speed"),
            "wind_direction": details.get("wind_from_direction"),
            "humidity": details.get("relative_humidity"),
            "weather_condition": weather_condition,
            "weather_source": "met_locationforecast",
            "weather_reference_time": best_time.isoformat(),
        }
