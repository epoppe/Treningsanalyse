import asyncio
import logging
import traceback
import uuid
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.config import settings
from app.services.activity_field_extraction import extract_activity_summary_fields
from app.services.hrv_fetch import HrvLiveResult, normalize_garmin_hrv_raw
from app.services.garmin_auth import (
    GarminAuthManager,
    GarminApiError,
    GarminAuthError,
    GarminMFARequiredError,
    GarminNotFoundError,
    GarminRateLimitError,
    GarminReauthRequiredError,
    is_not_found_error,
)
from app.services.telegram_notifier import build_notifier_from_settings
from app.utils.body_battery_timeseries import enrich_body_battery_day_data

# Sett opp logging tidlig så den er tilgjengelig
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


def _merge_garmin_daily_and_sleep_detail(
    daily: Optional[Dict[str, Any]],
    detail: Optional[Dict[str, Any]],
    date_str: str,
) -> Optional[Dict[str, Any]]:
    """Kombinerer DailySleep og SleepData med preferanse for detaljverdier."""
    if not daily and not detail:
        return None
    merged: Dict[str, Any] = {"date": date_str}
    for key in set((daily or {}).keys()) | set((detail or {}).keys()):
        if key == "date":
            continue
        detail_value = detail.get(key) if detail else None
        daily_value = daily.get(key) if daily else None
        merged[key] = detail_value if detail_value is not None else daily_value
    if merged.get("total_sleep") is None:
        deep = merged.get("deep_sleep")
        light = merged.get("light_sleep")
        rem = merged.get("rem_sleep")
        if any(x is not None for x in (deep, light, rem)):
            merged["total_sleep"] = (deep or 0) + (light or 0) + (rem or 0)
    if any(v is not None for k, v in merged.items() if k != "date"):
        return merged
    return None


def _garmin_to_serializable(value: Any, depth: int = 3) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if depth <= 0:
        return str(value)
    if isinstance(value, dict):
        return {str(k): _garmin_to_serializable(v, depth - 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_garmin_to_serializable(v, depth - 1) for v in value]
    if hasattr(value, "to_dict"):
        try:
            return _garmin_to_serializable(value.to_dict(), depth - 1)
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            return _garmin_to_serializable(value.dict(), depth - 1)
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return {
                str(k): _garmin_to_serializable(v, depth - 1)
                for k, v in vars(value).items()
                if not str(k).startswith("_")
            }
        except Exception:
            pass
    return str(value)


def _garmin_first_value(data: Dict[str, Any], candidates: List[str]) -> Any:
    for key in candidates:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _garmin_first_float(data: Dict[str, Any], candidates: List[str]) -> Optional[float]:
    value = _garmin_first_value(data, candidates)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _garmin_first_int(data: Dict[str, Any], candidates: List[str]) -> Optional[int]:
    value = _garmin_first_value(data, candidates)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _garmin_first_datetime(data: Dict[str, Any], candidates: List[str]) -> Optional[str]:
    value = _garmin_first_value(data, candidates)
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    elif isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1_000_000_000_000:
            numeric /= 1000.0
        try:
            parsed = datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _garmin_sleep_quality(overall_score: Optional[float], sleep_score: Optional[float]) -> Optional[str]:
    score = overall_score if overall_score is not None else sleep_score
    if score is None:
        return None
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 55:
        return "fair"
    return "poor"


def _extract_sleep_scores_nested(data: Dict[str, Any]) -> Dict[str, Any]:
    """Hent score/prosent fra Garmin DailySleepDTO sleep_scores."""
    scores = data.get("sleep_scores") or data.get("sleepScores")
    if not isinstance(scores, dict):
        return {}

    def block_value(key: str) -> Optional[float]:
        block = scores.get(key)
        if not isinstance(block, dict):
            return None
        value = block.get("value")
        if isinstance(value, (int, float)):
            return float(value)
        return None

    result: Dict[str, Any] = {}
    overall = block_value("overall")
    if overall is not None:
        result["overall_score"] = overall
    for score_key, attr in (
        ("deep_percentage", "deep_sleep_percent"),
        ("light_percentage", "light_sleep_percent"),
        ("rem_percentage", "rem_sleep_percent"),
    ):
        value = block_value(score_key)
        if value is not None:
            result[attr] = value
    return result


def _extract_sleep_detail_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    nested_scores = _extract_sleep_scores_nested(data)
    overall_score = _garmin_first_float(data, ["overall_score", "overallScore"]) or nested_scores.get("overall_score")
    sleep_score = _garmin_first_float(data, ["sleep_score", "sleepScore", "score"]) or overall_score
    sleep_latency = _garmin_first_float(
        data,
        [
            "sleepLatencyInSeconds",
            "sleepLatencySeconds",
            "timeToFallAsleepSeconds",
            "sleep_latency",
            "sleepLatency",
            "timeToFallAsleep",
        ],
    )
    result = {
        "overall_score": overall_score,
        "sleep_score": sleep_score,
        "bedtime": _garmin_first_datetime(
            data,
            [
                "bedtime",
                "bedTime",
                "sleepStartTimestampGMT",
                "sleepStartTimeGMT",
                "sleepStartTimestampLocal",
                "sleepStartTimeLocal",
                "sleep_start_timestamp_gmt",
                "sleep_start_timestamp_local",
            ],
        ),
        "wake_time": _garmin_first_datetime(
            data,
            [
                "wake_time",
                "wakeTime",
                "sleepEndTimestampGMT",
                "sleepEndTimeGMT",
                "sleepEndTimestampLocal",
                "sleepEndTimeLocal",
                "sleep_end_timestamp_gmt",
                "sleep_end_timestamp_local",
            ],
        ),
        "sleep_efficiency": _garmin_first_float(data, ["sleep_efficiency", "sleepEfficiency", "efficiency"]),
        "sleep_latency": sleep_latency,
        "wake_episodes": _garmin_first_int(
            data,
            ["wake_episodes", "wakeEpisodes", "numberOfWakeEvents", "awake_count", "awakeCount"],
        ),
        "average_heart_rate": _garmin_first_float(
            data,
            [
                "average_heart_rate",
                "averageHeartRate",
                "avgHeartRate",
                "average_sp_o2_hr_sleep",
                "averageSpO2HrSleep",
            ],
        ),
        "lowest_heart_rate": _garmin_first_float(data, ["lowest_heart_rate", "lowestHeartRate", "minHeartRate"]),
        "highest_heart_rate": _garmin_first_float(data, ["highest_heart_rate", "highestHeartRate", "maxHeartRate"]),
        "heart_rate_variability": _garmin_first_float(
            data,
            ["heart_rate_variability", "heartRateVariability", "averageHrv", "average_hrv"],
        ),
        "average_spo2": _garmin_first_float(
            data,
            ["average_spo2", "averageSpo2", "avgSpo2", "average_sp_o2_value", "averageSpo2Value"],
        ),
        "lowest_spo2": _garmin_first_float(
            data,
            ["lowest_spo2", "lowestSpo2", "minSpo2", "lowest_sp_o2_value", "lowestSpo2Value"],
        ),
        "average_respiration_rate": _garmin_first_float(
            data,
            [
                "average_respiration_rate",
                "averageRespirationRate",
                "averageRespiration",
                "avgRespirationRate",
                "average_respiration_value",
                "averageRespirationValue",
            ],
        ),
        "stress_score": _garmin_first_float(data, ["stress_score", "stressScore", "avg_sleep_stress", "avgSleepStress"]),
        "recovery_score": _garmin_first_float(data, ["recovery_score", "recoveryScore"]),
        "movement_score": _garmin_first_float(data, ["movement_score", "movementScore"]),
        "restless_moments": _garmin_first_int(data, ["restless_moments", "restlessMoments", "restlessMomentCount"]),
        "deep_sleep_percent": _garmin_first_float(data, ["deep_sleep_percent", "deepSleepPercent", "deepSleepPercentage"])
        or nested_scores.get("deep_sleep_percent"),
        "light_sleep_percent": _garmin_first_float(data, ["light_sleep_percent", "lightSleepPercent", "lightSleepPercentage"])
        or nested_scores.get("light_sleep_percent"),
        "rem_sleep_percent": _garmin_first_float(data, ["rem_sleep_percent", "remSleepPercent", "remSleepPercentage"])
        or nested_scores.get("rem_sleep_percent"),
        "awake_percent": _garmin_first_float(data, ["awake_percent", "awakePercent", "awakePercentage"]),
        "sleep_quality": _garmin_first_value(data, ["sleep_quality", "sleepQuality"]) or _garmin_sleep_quality(overall_score, sleep_score),
        "device_name": _garmin_first_value(data, ["device_name", "deviceName"]),
        "detailed_sleep_data": _garmin_to_serializable(data),
    }

    sleep_seconds = _garmin_first_float(data, ["sleep_time_seconds", "sleepTimeSeconds"])
    awake_seconds = _garmin_first_float(data, ["awake_sleep_seconds", "awakeSleepSeconds"])
    if result["sleep_efficiency"] is None and sleep_seconds is not None and awake_seconds is not None:
        time_in_bed = sleep_seconds + awake_seconds
        if time_in_bed > 0:
            result["sleep_efficiency"] = round(sleep_seconds / time_in_bed * 100.0, 1)

    if result["overall_score"] is None and nested_scores.get("overall_score") is not None:
        result["overall_score"] = nested_scores["overall_score"]

    return result


class GarminClient:
    """Garmin Connect-klient basert på python-garminconnect.

    All innlogging og token-fornyelse går via `GarminAuthManager` (garminconnect).
    garth brukes ikke for auth; en eksisterende garth-token behandles kun som en
    midlertidig legacy fallback (se GarminAuthManager).
    """

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
        self.notifier = build_notifier_from_settings(settings)
        self.auth = GarminAuthManager(
            email=email,
            password=password,
            token_dir=str(token_dir),
            token_file=getattr(settings, "GARMIN_TOKEN_FILE", None),
            notifier=self.notifier,
            is_cn=getattr(settings, "GARMIN_IS_CN", False),
        )
        logger.info(
            f"GarminClient instance {self.client_id} __init__. Token directory: {self.token_dir}. "
            "Auth-backend: python-garminconnect."
        )

    async def initialize(self) -> bool:
        """Initialiserer Garmin-klienten via garminconnect.

        Bruker lagret token/session når den finnes, ellers full innlogging.
        Ved MFA/401/endret pålogging feiler vi kontrollert (returnerer False),
        og GarminAuthManager varsler i Telegram at re-innlogging kreves.
        """
        logger.info(
            f"GarminClient instance {self.client_id} initialize. Initialiserer Garmin Client for {self.email}..."
        )
        try:
            await asyncio.to_thread(self.auth.authenticate)
            self._initialized = True
            logger.info("Garmin-klient initialisert (garminconnect).")
            return True
        except GarminMFARequiredError as exc:
            logger.error("Garmin krever MFA – kontrollert stopp: %s", exc)
            self._initialized = False
            return False
        except GarminReauthRequiredError as exc:
            logger.error("Garmin krever ny innlogging – kontrollert stopp: %s", exc)
            self._initialized = False
            return False
        except GarminRateLimitError as exc:
            logger.error("Garmin rate limit ved innlogging: %s", exc)
            self._initialized = False
            return False
        except Exception as exc:
            logger.error(f"Uventet feil ved Garmin-innlogging: {exc}")
            logger.error(traceback.format_exc())
            self._initialized = False
            return False

    def is_authenticated(self) -> bool:
        """Sjekker om klienten har en gyldig (innlogget) session."""
        return self.auth.is_authenticated

    # ------------------------------------------------------------------ #
    #  Transport-hjelpere (auto-refresh + typede unntak)                 #
    # ------------------------------------------------------------------ #

    async def _connect_api(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """GET mot Garmin connectapi. Fornyer token før kall ved behov."""
        if params is not None:
            return await asyncio.to_thread(self.auth.connectapi, path, params=params)
        return await asyncio.to_thread(self.auth.connectapi, path)

    async def _download(self, path: str) -> bytes:
        """Nedlasting (FIT-fil) via garminconnect med auto-refresh."""
        return await asyncio.to_thread(self.auth.download, path)

    def _username(self) -> Optional[str]:
        """Garmin display_name (tilsvarer garth client.username)."""
        return self.auth.display_name

    async def get_activities(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Henter aktiviteter for en gitt periode."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente aktiviteter.")
            return []

        try:
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")

            logger.info(f"Henter aktiviteter fra Garmin API: {start_str} til {end_str}")

            activities = await self._connect_api(
                f"/activitylist-service/activities/search/activities?startDate={start_str}&endDate={end_str}"
            )

            if isinstance(activities, list):
                logger.info(f"Hentet {len(activities)} aktiviteter fra Garmin")
                return activities
            else:
                logger.warning("Uventet respons fra Garmin API - ikke en liste")
                return []

        except GarminReauthRequiredError:
            raise
        except GarminNotFoundError:
            return []
        except (GarminRateLimitError, GarminApiError) as e:
            logger.error(f"API-feil ved henting av aktiviteter: {e}")
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

            fit_data = await self._download(
                f"/download-service/files/activity/{activity_id}"
            )

            if isinstance(fit_data, bytes):
                logger.info(f"Hentet FIT-data for aktivitet {activity_id} ({len(fit_data)} bytes)")
                return fit_data
            else:
                logger.warning(f"Uventet respons ved henting av FIT-data for aktivitet {activity_id}")
                return None

        except GarminReauthRequiredError:
            raise
        except GarminNotFoundError:
            logger.info(f"Ingen FIT-data funnet for aktivitet {activity_id}")
            return None
        except (GarminRateLimitError, GarminApiError) as e:
            logger.error(f"API-feil ved henting av FIT-data for aktivitet {activity_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Feil ved henting av FIT-data for aktivitet {activity_id}: {e}")
            logger.error(traceback.format_exc())
            return None

    async def get_hrv_data_alternative(self, date: datetime) -> Optional[Dict[str, Any]]:
        """Bakoverkompatibel wrapper rundt fetch_hrv_live."""
        live_result = await self.fetch_hrv_live(date)
        return live_result.data

    async def fetch_hrv_live(self, date: datetime) -> HrvLiveResult:
        """Henter HRV direkte fra Garmin med eksplisitt live-status."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente HRV-data.")
            return HrvLiveResult(
                data=None,
                live_status="not_authenticated",
                message="Garmin-klienten er ikke autentisert.",
            )

        date_str = date.strftime("%Y-%m-%d")
        logger.debug(f"Henter live HRV-data for {date_str}")

        saw_not_found = False
        raw_hrv: Any = None

        try:
            try:
                raw_hrv = await self._connect_api(f"/hrv-service/hrv/daily/{date_str}")
            except GarminReauthRequiredError:
                raise
            except GarminNotFoundError:
                saw_not_found = True
                raw_hrv, alt_not_found = await self._fetch_hrv_from_alternative_endpoints(date_str)
                saw_not_found = saw_not_found or alt_not_found
                if raw_hrv is None and saw_not_found:
                    return HrvLiveResult(
                        data=None,
                        live_status="not_found",
                        message=f"Ingen live HRV hos Garmin for {date_str}.",
                    )
            except (GarminRateLimitError, GarminApiError) as api_error:
                logger.debug(
                    "Standard HRV API feilet for %s, prøver alternative endepunkter: %s",
                    date_str,
                    api_error,
                )
                raw_hrv, alt_not_found = await self._fetch_hrv_from_alternative_endpoints(date_str)
                saw_not_found = saw_not_found or alt_not_found
                if raw_hrv is None and saw_not_found:
                    return HrvLiveResult(
                        data=None,
                        live_status="not_found",
                        message=f"Ingen live HRV hos Garmin for {date_str}.",
                    )

            if raw_hrv in (None, {}, []):
                return HrvLiveResult(
                    data=None,
                    live_status="empty",
                    message=f"Tomt HRV-svar fra Garmin for {date_str}.",
                )

            normalized = normalize_garmin_hrv_raw(raw_hrv, HRVData.model_validate)
            if normalized:
                logger.debug(f"Validerte live HRV-data for {date_str}")
                return HrvLiveResult(data=normalized, live_status="ok")

            return HrvLiveResult(
                data=None,
                live_status="empty",
                message=f"Garmin returnerte HRV uten brukbar last_night_avg for {date_str}.",
            )
        except GarminReauthRequiredError:
            raise
        except Exception as exc:
            logger.error(f"En uventet feil oppstod under henting av HRV-data for {date_str}: {exc}")
            logger.error(traceback.format_exc())
            return HrvLiveResult(data=None, live_status="error", message=str(exc))

    async def _fetch_hrv_from_alternative_endpoints(
        self,
        date_str: str,
    ) -> tuple[Optional[Any], bool]:
        saw_not_found = False
        username = self._username()
        alternative_endpoints = [
            (f"/usersummary-service/stats/hrv/daily/{date_str}", {}),
            (
                f"/usersummary-service/usersummary/daily/{username}",
                {"calendarDate": date_str},
            ),
            (
                f"/wellness-service/wellness/dailyHRV/{username}",
                {"date": date_str},
            ),
        ]

        for endpoint, params in alternative_endpoints:
            try:
                alt_data = await self._connect_api(endpoint, params=params)
                normalized = normalize_garmin_hrv_raw(alt_data, HRVData.model_validate)
                if normalized:
                    logger.debug("HRV hentet fra alternativt endepunkt for %s", date_str)
                    return normalized, saw_not_found
            except GarminReauthRequiredError:
                raise
            except GarminNotFoundError:
                saw_not_found = True
                logger.debug(f"Alternativt endepunkt {endpoint} ga 404")
            except Exception as alt_error:
                logger.debug(f"Alternativt endepunkt {endpoint} feilet: {alt_error}")

        return None, saw_not_found

    async def get_hrv_data(self, date: datetime) -> Optional[Dict[str, Any]]:
        """Henter HRV-data for en spesifikk dato."""
        live_result = await self.fetch_hrv_live(date)
        return live_result.data

    async def get_resting_heart_rate_data(
        self, target_date: date | datetime | str
    ) -> Optional[Dict[str, Any]]:
        """Henter hvilepuls fra Garmin dailyHeartRate-endepunktet."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente hvilepuls.")
            return None

        if isinstance(target_date, datetime):
            date_str = target_date.strftime("%Y-%m-%d")
        elif isinstance(target_date, date):
            date_str = target_date.strftime("%Y-%m-%d")
        else:
            date_str = str(target_date)

        try:
            logger.info(f"Henter hvilepuls for {date_str}")
            data = await self._connect_api(
                f"/wellness-service/wellness/dailyHeartRate/{self._username()}",
                params={"date": date_str},
            )
            if not isinstance(data, dict):
                logger.info(f"Uventet hvilepuls-respons for {date_str}: {type(data).__name__}")
                return None

            resting = data.get("restingHeartRate")
            if resting is None:
                logger.info(f"Ingen hvilepulsverdi tilgjengelig for {date_str}")
                return None

            return {
                "date": date_str,
                "resting_heart_rate": resting,
                "min_heart_rate": data.get("minHeartRate"),
                "max_heart_rate": data.get("maxHeartRate"),
                "last_seven_days_avg_resting_heart_rate": data.get("lastSevenDaysAvgRestingHeartRate"),
                "measurement_method": "automatic",
            }
        except GarminReauthRequiredError:
            raise
        except GarminNotFoundError:
            logger.info(f"Ingen hvilepulsdata funnet for {date_str}")
            return None
        except (GarminRateLimitError, GarminApiError) as e:
            logger.error(f"API-feil ved henting av hvilepuls for {date_str}: {e}")
            return None
        except Exception as e:
            logger.error(f"Feil ved henting av hvilepuls for {date_str}: {e}")
            logger.error(traceback.format_exc())
            return None

    async def get_activity_epoc_data(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """Henter EPOC (Exercise Post Oxygen Consumption) data for en aktivitet."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente EPOC-data.")
            return None

        try:
            logger.info(f"Henter EPOC data for aktivitet {activity_id}")

            activity_data = await self._connect_api(
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

        except GarminReauthRequiredError:
            raise
        except GarminNotFoundError:
            logger.info(f"Ingen EPOC data funnet for aktivitet {activity_id}")
            return None
        except (GarminRateLimitError, GarminApiError) as e:
            logger.error(f"API-feil ved henting av EPOC data for aktivitet {activity_id}: {e}")
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

            activity_data = await self._connect_api(
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

        except GarminReauthRequiredError:
            raise
        except GarminNotFoundError:
            logger.info(f"Ingen detaljerte data funnet for aktivitet {activity_id}")
            return None
        except (GarminRateLimitError, GarminApiError) as e:
            logger.error(f"API-feil ved henting av Training Effect for aktivitet {activity_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Feil ved henting av Training Effect for aktivitet {activity_id}: {e}")
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def _extract_grade_adjusted_speed_mps(activity_data: Dict[str, Any], summary: Dict[str, Any]) -> Optional[float]:
        """Hent avgGradeAdjustedSpeed fra summaryDTO, rot-nivå eller alternative Garmin-nøkler."""
        candidate_keys = (
            "avgGradeAdjustedSpeed",
            "averageGradeAdjustedSpeed",
            "gradeAdjustedSpeed",
            "avgGradeAdjustedSpeedMps",
        )
        for source in (summary, activity_data):
            if not isinstance(source, dict):
                continue
            for key in candidate_keys:
                value = source.get(key)
                if value is not None:
                    try:
                        numeric = float(value)
                    except (TypeError, ValueError):
                        continue
                    if numeric > 0:
                        return numeric
        return None

    @staticmethod
    def _extract_activity_recovery_time_minutes(
        activity_data: Dict[str, Any],
        summary: Dict[str, Any],
    ) -> Optional[int]:
        """
        Hent anbefalt recovery time fra activity-service (minutter).

        Garmin bruker varierende nøkler; feltet finnes sjelden i activitylist.
        """
        candidate_keys = (
            "recoveryTime",
            "timeToRecover",
            "recommendedRecoveryTime",
            "postActivityRecoveryTime",
        )
        for source in (summary, activity_data):
            if not isinstance(source, dict):
                continue
            for key in candidate_keys:
                value = source.get(key)
                if value is None:
                    continue
                try:
                    minutes = int(round(float(value)))
                except (TypeError, ValueError):
                    continue
                if minutes > 0:
                    return minutes
        return None

    def _extract_activity_summary_metrics(self, activity_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normaliserer nyttige summaryDTO-felter fra activity-service."""
        if not isinstance(activity_data, dict):
            return None
        summary = activity_data.get("summaryDTO")
        if not isinstance(summary, dict):
            return None

        summary_fields = extract_activity_summary_fields(summary)

        return {
            "vo2_max": summary.get("vO2MaxValue"),
            "vo2_max_precise": summary.get("vO2MaxPreciseValue"),
            "average_heart_rate": summary.get("averageHR"),
            "max_heart_rate": summary.get("maxHR"),
            "min_heart_rate": summary.get("minHR"),
            "average_moving_speed": summary.get("averageMovingSpeed"),
            "avg_grade_adjusted_speed": self._extract_grade_adjusted_speed_mps(activity_data, summary),
            "ground_contact_time": summary.get("groundContactTime"),
            "stride_length": summary.get("strideLength"),
            "vertical_oscillation": summary.get("verticalOscillation"),
            "vertical_ratio": summary.get("verticalRatio"),
            "begin_potential_stamina": summary.get("beginPotentialStamina"),
            "end_potential_stamina": summary.get("endPotentialStamina"),
            "min_available_stamina": summary.get("minAvailableStamina"),
            "recovery_time": self._extract_activity_recovery_time_minutes(activity_data, summary),
            "activity_body_battery_delta": summary.get("differenceBodyBattery"),
            "training_load": summary.get("activityTrainingLoad"),
            "aerobic_training_effect": summary.get("aerobicTrainingEffect") or summary.get("trainingEffect"),
            "anaerobic_training_effect": summary.get("anaerobicTrainingEffect"),
            "training_effect_label": summary.get("trainingEffectLabel"),
            "aerobic_training_effect_message": summary.get("aerobicTrainingEffectMessage"),
            "anaerobic_training_effect_message": summary.get("anaerobicTrainingEffectMessage"),
            "elevation_gain": summary.get("elevationGain") or summary.get("totalElevationGain"),
            "elevation_loss": summary.get("elevationLoss") or summary.get("totalElevationLoss"),
            "total_steps": summary_fields["total_steps"],
            "max_running_cadence": summary_fields["max_running_cadence"],
            **summary_fields,
        }

    async def get_activity_summary_metrics(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """Henter utvidede aktivitetsfelter fra Garmin activity-service."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente activity summary metrics.")
            return None

        try:
            activity_data = await self._connect_api(
                f"/activity-service/activity/{activity_id}",
            )
            metrics = self._extract_activity_summary_metrics(activity_data)
            if metrics:
                logger.info(f"Hentet utvidede activity summary metrics for {activity_id}")
            return metrics
        except GarminReauthRequiredError:
            raise
        except GarminNotFoundError:
            logger.info(f"Ingen activity summary metrics funnet for aktivitet {activity_id}")
            return None
        except (GarminRateLimitError, GarminApiError) as e:
            logger.error(f"API-feil ved henting av activity summary metrics for {activity_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Feil ved henting av activity summary metrics for {activity_id}: {e}")
            logger.error(traceback.format_exc())
            return None

    def _first_primary_map_value(self, data: Optional[Dict[str, Any]], map_key: str) -> Optional[Dict[str, Any]]:
        if not isinstance(data, dict):
            return None
        value_map = data.get(map_key)
        if not isinstance(value_map, dict):
            return None
        fallback = None
        for value in value_map.values():
            if isinstance(value, dict):
                if fallback is None:
                    fallback = value
                if value.get("primaryTrainingDevice"):
                    return value
        return fallback

    def _extract_daily_garmin_performance_metrics(
        self,
        date_str: str,
        maxmet: Optional[Dict[str, Any]],
        load_balance: Optional[Dict[str, Any]],
        training_status: Optional[Dict[str, Any]],
        endurance_score: Optional[Dict[str, Any]],
        hill_score: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        generic = maxmet.get("generic", {}) if isinstance(maxmet, dict) else {}
        heat_altitude = maxmet.get("heatAltitudeAcclimation", {}) if isinstance(maxmet, dict) else {}
        load = self._first_primary_map_value(load_balance, "metricsTrainingLoadBalanceDTOMap") or {}
        status = dict(self._first_primary_map_value(training_status, "latestTrainingStatusData") or {})
        acute_load = status.pop("acuteTrainingLoadDTO", None) if isinstance(status, dict) else None
        if isinstance(acute_load, dict):
            status = {**status, **acute_load}

        return {
            "date": date_str,
            "vo2_max": generic.get("vo2MaxValue"),
            "vo2_max_precise": generic.get("vo2MaxPreciseValue"),
            "fitness_age": generic.get("fitnessAge"),
            "max_met_category": generic.get("maxMetCategory"),
            "altitude_acclimation": heat_altitude.get("altitudeAcclimation"),
            "previous_altitude_acclimation": heat_altitude.get("previousAltitudeAcclimation"),
            "heat_acclimation_percentage": heat_altitude.get("heatAcclimationPercentage"),
            "previous_heat_acclimation_percentage": heat_altitude.get("previousHeatAcclimationPercentage"),
            "current_altitude": heat_altitude.get("currentAltitude"),
            "heat_trend": heat_altitude.get("heatTrend"),
            "altitude_trend": heat_altitude.get("altitudeTrend"),
            "monthly_load_aerobic_low": load.get("monthlyLoadAerobicLow"),
            "monthly_load_aerobic_high": load.get("monthlyLoadAerobicHigh"),
            "monthly_load_anaerobic": load.get("monthlyLoadAnaerobic"),
            "monthly_load_aerobic_low_target_min": load.get("monthlyLoadAerobicLowTargetMin"),
            "monthly_load_aerobic_low_target_max": load.get("monthlyLoadAerobicLowTargetMax"),
            "monthly_load_aerobic_high_target_min": load.get("monthlyLoadAerobicHighTargetMin"),
            "monthly_load_aerobic_high_target_max": load.get("monthlyLoadAerobicHighTargetMax"),
            "monthly_load_anaerobic_target_min": load.get("monthlyLoadAnaerobicTargetMin"),
            "monthly_load_anaerobic_target_max": load.get("monthlyLoadAnaerobicTargetMax"),
            "training_balance_feedback_phrase": load.get("trainingBalanceFeedbackPhrase"),
            "training_status": status.get("trainingStatus"),
            "training_status_feedback_phrase": status.get("trainingStatusFeedbackPhrase"),
            "sport": status.get("sport"),
            "sub_sport": status.get("subSport"),
            "fitness_trend": status.get("fitnessTrend"),
            "fitness_trend_sport": status.get("fitnessTrendSport"),
            "acwr_percent": status.get("acwrPercent"),
            "acwr_status": status.get("acwrStatus"),
            "acwr_status_feedback": status.get("acwrStatusFeedback"),
            "daily_training_load_acute": status.get("dailyTrainingLoadAcute"),
            "daily_training_load_chronic": status.get("dailyTrainingLoadChronic"),
            "daily_acute_chronic_workload_ratio": status.get("dailyAcuteChronicWorkloadRatio"),
            "load_tunnel_min": status.get("loadTunnelMin"),
            "load_tunnel_max": status.get("loadTunnelMax"),
            "endurance_score": endurance_score.get("overallScore") if isinstance(endurance_score, dict) else None,
            "endurance_classification": endurance_score.get("classification") if isinstance(endurance_score, dict) else None,
            "hill_score": hill_score.get("overallScore") if isinstance(hill_score, dict) else None,
            "hill_endurance_score": hill_score.get("enduranceScore") if isinstance(hill_score, dict) else None,
            "hill_strength_score": hill_score.get("strengthScore") if isinstance(hill_score, dict) else None,
            "raw_maxmet": maxmet,
            "raw_training_load_balance": load_balance,
            "raw_training_status": training_status,
            "raw_endurance_score": endurance_score,
            "raw_hill_score": hill_score,
        }

    async def get_daily_garmin_performance_metrics(self, target_date: date | datetime | str) -> Dict[str, Any]:
        """Henter dagsbaserte Garmin performance-metrikker."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente Garmin performance metrics.")
            return {}

        if isinstance(target_date, datetime):
            date_str = target_date.strftime("%Y-%m-%d")
        elif isinstance(target_date, date):
            date_str = target_date.strftime("%Y-%m-%d")
        else:
            date_str = str(target_date)

        async def _fetch(name: str, endpoint: str, params: Optional[Dict[str, Any]] = None):
            try:
                data = await self._connect_api(endpoint, params=params)
                return name, data
            except GarminReauthRequiredError:
                raise
            except GarminNotFoundError:
                logger.info(f"Ingen Garmin performance-data fra {endpoint} for {date_str}")
                return name, None
            except Exception as exc:
                logger.warning(f"Kunne ikke hente {endpoint} for {date_str}: {exc}")
                return name, None

        results = await asyncio.gather(
            _fetch("maxmet", f"/metrics-service/metrics/maxmet/latest/{date_str}"),
            _fetch("load_balance", f"/metrics-service/metrics/trainingloadbalance/latest/{date_str}"),
            _fetch("training_status", f"/metrics-service/metrics/trainingstatus/daily/{date_str}"),
            _fetch("endurance_score", "/metrics-service/metrics/endurancescore", {"calendarDate": date_str}),
            _fetch("hill_score", "/metrics-service/metrics/hillscore", {"calendarDate": date_str}),
        )
        data = {name: value for name, value in results}
        return self._extract_daily_garmin_performance_metrics(
            date_str,
            data.get("maxmet"),
            data.get("load_balance"),
            data.get("training_status"),
            data.get("endurance_score"),
            data.get("hill_score"),
        )

    async def get_training_status(self) -> Optional[Dict[str, Any]]:
        """Henter treningstatus fra Garmin Connect."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente treningstatus.")
            return None

        try:
            logger.info("Henter treningstatus...")

            stats_data = await self._connect_api(
                "/userstats-service/stats"
            )

            if isinstance(stats_data, dict):
                logger.info(f"Hentet treningstatus-data med {len(stats_data)} nøkler")
                return stats_data
            else:
                logger.warning(f"Uventet data-type: {type(stats_data)}")
                return None

        except GarminReauthRequiredError:
            raise
        except GarminNotFoundError:
            logger.info("Ingen treningstatus-data funnet (404)")
            return None
        except (GarminRateLimitError, GarminApiError) as e:
            logger.error(f"API-feil ved henting av treningstatus: {e}")
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

            username = self._username()
            endpoints = [
                (f"/usersummary-service/usersummary/daily/{username}", {"calendarDate": date_str}),
                (f"/wellness-service/wellness/dailyBodyBattery/{username}", {"date": date_str}),
            ]

            body_battery_data = None
            for endpoint, params in endpoints:
                try:
                    logger.info(f"Prøver body battery-endepunkt: {endpoint} med params: {params}")
                    data = await self._connect_api(endpoint, params=params)
                    logger.debug(f"Body battery-endepunkt {endpoint} returnerte: {data}")

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
                            body_battery_data = enrich_body_battery_day_data(result)
                            break
                        elif 'bodyBattery' in data:
                            result = enrich_body_battery_day_data(data['bodyBattery'])
                            logger.info(f"Hentet body battery data fra bodyBattery for {date_str}: {result}")
                            body_battery_data = result
                            break

                except GarminReauthRequiredError:
                    raise
                except Exception as e:
                    logger.debug(f"Body battery-endepunkt {endpoint} feilet: {e}")
                    continue

            if not body_battery_data:
                logger.info(f"Ingen body battery data funnet for {date_str}")
                return None

            return body_battery_data

        except GarminReauthRequiredError:
            raise
        except Exception as e:
            logger.error(f"Feil ved henting av body battery data for {date_str}: {e}")
            return None

    async def get_body_battery_range(self, start_date, end_date) -> List[Dict[str, Any]]:
        """Henter body battery data for en datoperiode."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente body battery data.")
            return []

        try:
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

        except GarminReauthRequiredError:
            raise
        except Exception as e:
            logger.error(f"Feil ved henting av body battery range: {e}")
            return []

    async def get_sleep_data(self, date: datetime) -> Optional[Dict[str, Any]]:
        """Henter søvndata for en spesifikk dato via wellness-/usersummary-endepunkter."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente søvndata.")
            return None

        try:
            date_str = date.strftime("%Y-%m-%d")
            logger.info(f"Henter søvndata for {date_str}")
            username = self._username()

            # 1) Prøv usersummary allMetrics
            try:
                sleep_data = await self._connect_api(
                    f"/usersummary-service/usersummary/daily/{username}",
                    params={"calendarDate": date_str},
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
                    result.update(_extract_sleep_detail_metrics(metrics))
                    if any(v is not None for k, v in result.items() if k != 'date'):
                        logger.info(f"Hentet søvndata (usersummary) for {date_str}")
                        return result
            except GarminReauthRequiredError:
                raise
            except Exception as e:
                logger.debug(f"usersummary sleep feilet {date_str}: {e}")

            # 2) Prøv wellness-service dailySleepData rå-endepunkt
            for params in ({"date": date_str}, {"calendarDate": date_str}):
                try:
                    data = await self._connect_api(
                        f"/wellness-service/wellness/dailySleepData/{username}",
                        params=params,
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

                        to_min = lambda s: (s / 60.0) if isinstance(s, (int, float)) else None
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
                        result.update(_extract_sleep_detail_metrics(summary))
                        if any(v is not None for k, v in result.items() if k != 'date'):
                            logger.info(f"Hentet søvndata (wellness dailySleepData) for {date_str}")
                            return result
                except GarminReauthRequiredError:
                    raise
                except Exception as e:
                    logger.debug(f"wellness dailySleepData feilet {date_str}: {e}")

            logger.info(f"Ingen søvndata funnet for {date_str}")
            return None

        except GarminReauthRequiredError:
            raise
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

        except GarminReauthRequiredError:
            raise
        except Exception as e:
            logger.error(f"Feil ved henting av søvndata range: {e}")
            return []

    async def get_stress_data(self, date_input) -> Optional[Dict[str, Any]]:
        """Henter stressdata for en spesifikk dato via usersummary-endepunktet."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente stressdata.")
            return None

        try:
            if isinstance(date_input, datetime):
                date_obj = date_input.date()
            elif isinstance(date_input, date):
                date_obj = date_input
            else:
                date_obj = date_input.date() if hasattr(date_input, 'date') else date_input

            date_str = date_obj.strftime("%Y-%m-%d") if hasattr(date_obj, 'strftime') else str(date_obj)
            logger.info(f"Henter stressdata for {date_str}")

            stress_data = await self._connect_api(
                f"/usersummary-service/usersummary/daily/{self._username()}",
                params={"calendarDate": date_str},
            )

            if isinstance(stress_data, dict) and 'allMetrics' in stress_data:
                metrics = stress_data.get('allMetrics', {}).get('metricsMap', {})

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

        except GarminReauthRequiredError:
            raise
        except GarminNotFoundError:
            logger.info(f"Ingen stressdata funnet for {date_str}")
            return None
        except (GarminRateLimitError, GarminApiError) as e:
            logger.error(f"API-feil ved henting av stressdata for {date_str}: {e}")
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

        except GarminReauthRequiredError:
            raise
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

        except GarminReauthRequiredError:
            raise
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

            summary_data = await self._connect_api(
                f"/usersummary-service/usersummary/daily/{self._username()}",
                params={"calendarDate": date_str},
            )

            if isinstance(summary_data, dict) and 'allMetrics' in summary_data:
                metrics = summary_data.get('allMetrics', {}).get('metricsMap', {})

                result = {
                    "date": date_str,
                    "metrics": {}
                }

                for metric_name, metric_data in metrics.items():
                    if isinstance(metric_data, dict) and 'value' in metric_data:
                        result["metrics"][metric_name] = metric_data['value']

                logger.info(f"Hentet metrics sammendrag for {date_str} med {len(result['metrics'])} metrics")
                return result
            else:
                logger.info(f"Ingen metrics sammendrag funnet for {date_str}")
                return {"date": date_str, "metrics": {}}

        except GarminReauthRequiredError:
            raise
        except GarminNotFoundError:
            logger.info(f"Ingen metrics sammendrag funnet for {date_str}")
            return {"date": date_str, "metrics": {}}
        except (GarminRateLimitError, GarminApiError) as e:
            logger.error(f"API-feil ved henting av metrics sammendrag for {date_str}: {e}")
            return {"date": date_str, "metrics": {}}
        except Exception as e:
            logger.error(f"Feil ved henting av metrics sammendrag for {date_str}: {e}")
            return {"date": date_str, "metrics": {}}

    async def get_lactate_threshold_info(self) -> Optional[Dict[str, Any]]:
        """Henter terskelinfo fra Garmin, med fallback til konfigurasjon ved behov."""
        try:
            raw_speed = None
            heart_rate = None

            if self.is_authenticated():
                logger.info("Henter lactate threshold speed fra Garmin Connect")

                try:
                    user_settings = await self._connect_api(
                        "/userprofile-service/userprofile/user-settings"
                    )
                    user_data = user_settings.get("userData") if isinstance(user_settings, dict) else None

                    if isinstance(user_data, dict):
                        raw_speed = user_data.get("lactateThresholdSpeed")
                        heart_rate = user_data.get("lactateThresholdHeartRate")
                        if raw_speed is not None:
                            logger.info(f"Lactate threshold speed hentet fra Garmin: {raw_speed} (råverdi)")
                            normalized_speed = self._normalize_lactate_threshold_speed(raw_speed)
                            if normalized_speed is not None:
                                logger.info(
                                    f"Lactate threshold speed normalisert fra Garmin-råverdi {raw_speed} "
                                    f"til {normalized_speed} m/s"
                                )
                                return {
                                    "speed_mps": normalized_speed,
                                    "heart_rate_bpm": heart_rate,
                                    "raw_speed_mps": raw_speed,
                                    "source": "garmin_connect",
                                    "is_fallback": False,
                                }
                            logger.warning(
                                f"Lactate threshold speed {raw_speed} fra Garmin kunne ikke normaliseres "
                                "til et forventet m/s-område. Bruker fallback fra konfigurasjon."
                            )
                        else:
                            logger.warning("Lactate threshold speed ikke tilgjengelig i user_data")
                    else:
                        logger.warning("user_data ikke tilgjengelig")

                except GarminReauthRequiredError:
                    raise
                except Exception as e:
                    logger.warning(f"Kunne ikke hente lactate threshold speed via user-settings: {e}")
            else:
                logger.warning("Garmin-klient ikke autentisert")

            if settings.LACTATE_THRESHOLD_SPEED is not None:
                logger.info(f"Bruker konfigurert lactate threshold speed: {settings.LACTATE_THRESHOLD_SPEED} m/s")
                return {
                    "speed_mps": settings.LACTATE_THRESHOLD_SPEED,
                    "heart_rate_bpm": heart_rate,
                    "raw_speed_mps": raw_speed,
                    "source": "config_fallback",
                    "is_fallback": True,
                }

            logger.info("Ingen lactate threshold speed tilgjengelig fra Garmin eller konfigurasjon")
            return None

        except GarminReauthRequiredError:
            raise
        except Exception as e:
            logger.error(f"Uventet feil ved henting av lactate threshold speed: {e}")
            return None

    async def get_lactate_threshold_speed(self) -> Optional[float]:
        """
        Henter lactate threshold speed fra Garmin Connect eller konfigurasjon.

        Returns:
            Optional[float]: Lactate threshold speed i m/s, eller None hvis ikke tilgjengelig
        """
        info = await self.get_lactate_threshold_info()
        return info.get("speed_mps") if info else None

    @staticmethod
    def _normalize_lactate_threshold_speed(raw_speed: Any) -> Optional[float]:
        """Normaliserer Garmin-råverdi for terskelfart til m/s."""
        try:
            speed = float(raw_speed)
        except (TypeError, ValueError):
            return None

        if speed <= 0:
            return None

        if 2.0 <= speed <= 6.0:
            return speed

        # Garmin user-settings kan returnere terskelfart i en komprimert desimalform
        # som må skaleres opp til m/s for å samsvare med pace i Garmin UI.
        if 0.2 <= speed <= 0.7:
            normalized_speed = speed * 10.0
            if 2.0 <= normalized_speed <= 6.0:
                return normalized_speed

        return None
