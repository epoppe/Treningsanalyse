"""Applikasjonsinnstillinger via pydantic-settings.

Miljøvariabler og `.env` leses av BaseSettings — ikke via manuell os.getenv
på feltene (unngår dobbelt lasting og type-feil).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolutt sti til backend-mappen
BACKEND_DIR = Path(__file__).parent.parent.absolute()
ENV_FILE = BACKEND_DIR / ".env"

# Last .env tidlig slik at annen kode som leser os.environ også ser verdiene.
load_dotenv(dotenv_path=ENV_FILE)

DEFAULT_DATA_DIR = BACKEND_DIR / "data"
_db_path = (DEFAULT_DATA_DIR.absolute() / "treningsanalyse.db").resolve()
DEFAULT_DATABASE_URL = "sqlite:///" + str(_db_path).replace("\\", "/")

TOKEN_DIR = BACKEND_DIR / "tokens"
TOKEN_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_TOKEN_DIR = str(TOKEN_DIR.absolute())

# Standard LTHR-pace 5:22 min/km → m/s
_DEFAULT_LTHR_SPEED = 1000 / (5 * 60 + 22)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = DEFAULT_DATABASE_URL

    # Garmin Connect
    GARMIN_EMAIL: str = ""
    GARMIN_PASSWORD: str = ""
    TOKEN_DIR: str = DEFAULT_TOKEN_DIR
    # Tom => <TOKEN_DIR>/garmin_tokens.json
    GARMIN_TOKEN_FILE: Optional[str] = None
    GARMIN_IS_CN: bool = False

    # Lactate threshold (m/s) — manuell fallback hvis Garmin mangler verdi
    LACTATE_THRESHOLD_SPEED: Optional[float] = _DEFAULT_LTHR_SPEED

    # Data storage
    DATA_DIR: str = str(DEFAULT_DATA_DIR.absolute())

    # Logging
    LOG_LEVEL: str = "INFO"

    # Redis (valgfritt — default av for lokal boot uten Redis)
    REDIS_ENABLED: bool = False
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # MET / Frost vær
    MET_API_USER_AGENT: str = "Treningsanalyse/1.0 (tim-agent)"
    FROST_CLIENT_ID: str = ""
    FROST_CLIENT_SECRET: str = ""

    # Telegram re-auth varsling
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_ENABLED: bool = True
    TELEGRAM_REAUTH_COOLDOWN_SECONDS: int = 1800

    # Sikkerhet / CORS
    # Komma-separert liste, f.eks. "http://localhost:3000,https://app.example.com"
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002"
    )
    # Tom = TrustedHostMiddleware av. Eksempel: "localhost,127.0.0.1,treningsanalyse.local"
    ALLOWED_HOSTS: str = ""
    # Eksponer /api/debug/* når true
    DEBUG: bool = False
    # local | production — påvirker logging/hints, ikke coaching
    ENVIRONMENT: str = "local"
    # Hopp over Garmin-innlogging ved app-oppstart (dev/test)
    SKIP_GARMIN_INIT: bool = False

    # Valgfritt løpsmål for Adaptive Coaching Engine v4 (ingen DB-krav)
    ATHLETE_GOAL_TYPE: Optional[str] = None
    ATHLETE_GOAL_EVENT: Optional[str] = None
    ATHLETE_GOAL_TARGET_DATE: Optional[str] = None
    ATHLETE_GOAL_TARGET_TIME_SEC: Optional[int] = None
    ATHLETE_GOAL_PRIORITY: str = "A"
    ATHLETE_AVAILABILITY_JSON: Optional[str] = None

    @field_validator(
        "GARMIN_TOKEN_FILE",
        "REDIS_PASSWORD",
        "ATHLETE_GOAL_TYPE",
        "ATHLETE_GOAL_EVENT",
        "ATHLETE_GOAL_TARGET_DATE",
        "ATHLETE_AVAILABILITY_JSON",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("ATHLETE_GOAL_TARGET_TIME_SEC", mode="before")
    @classmethod
    def empty_int_to_none(cls, value: object) -> object:
        if value == "" or value is None:
            return None
        return value

    @field_validator("FROST_CLIENT_SECRET", "FROST_CLIENT_ID", mode="before")
    @classmethod
    def none_to_empty_string(cls, value: object) -> object:
        if value is None:
            return ""
        return value

    def model_post_init(self, __context: object) -> None:
        Path(self.TOKEN_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.DATA_DIR).mkdir(parents=True, exist_ok=True)

    def cors_origin_list(self) -> List[str]:
        """Parse CORS_ORIGINS til liste uten tomme elementer."""
        return [part.strip() for part in self.CORS_ORIGINS.split(",") if part.strip()]

    def allowed_host_list(self) -> List[str]:
        """Parse ALLOWED_HOSTS. Tom liste = middleware ikke aktiv."""
        return [part.strip() for part in self.ALLOWED_HOSTS.split(",") if part.strip()]

    def masked_garmin_email(self) -> str:
        """Maskert e-post for logger (aldri full adresse)."""
        email = (self.GARMIN_EMAIL or "").strip()
        if not email:
            return "(ikke satt)"
        if "@" not in email:
            return email[:2] + "***" if len(email) > 2 else "***"
        local, _, domain = email.partition("@")
        if len(local) <= 2:
            masked_local = "*" * len(local)
        else:
            masked_local = local[:2] + "***"
        return f"{masked_local}@{domain}"


@lru_cache
def get_settings() -> Settings:
    """Singleton Settings — trygt å bruke som FastAPI-dependency."""
    return Settings()


# Bakoverkompatibel modul-global
settings = get_settings()


def data_path(*parts: str) -> Path:
    """Bygger absolutt sti under konfigurert DATA_DIR."""
    return Path(settings.DATA_DIR).joinpath(*parts)
