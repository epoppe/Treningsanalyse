"""Applikasjonsinnstillinger via pydantic-settings.

Miljøvariabler og `.env` leses av BaseSettings — ikke via manuell os.getenv
på feltene (unngår dobbelt lasting og type-feil).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

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

    # Redis (valgfritt)
    REDIS_ENABLED: bool = True
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

    @field_validator("GARMIN_TOKEN_FILE", "REDIS_PASSWORD", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        if value == "":
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


@lru_cache
def get_settings() -> Settings:
    """Singleton Settings — trygt å bruke som FastAPI-dependency."""
    return Settings()


# Bakoverkompatibel modul-global
settings = get_settings()


def data_path(*parts: str) -> Path:
    """Bygger absolutt sti under konfigurert DATA_DIR."""
    return Path(settings.DATA_DIR).joinpath(*parts)
