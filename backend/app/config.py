from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
import os
from dotenv import load_dotenv
from typing import Optional

# Få absolutt sti til backend-mappen
BACKEND_DIR = Path(__file__).parent.parent.absolute()
ENV_FILE = BACKEND_DIR / ".env"

# Last miljøvariabler fra riktig sti
load_dotenv(dotenv_path=ENV_FILE)
# print(f"Laster miljøvariabler fra: {ENV_FILE}") # Kan kommenteres ut for produksjon

# Standard data-mappe (relativt til backend-mappen hvis ikke absolutt sti er gitt i .env)
DEFAULT_DATA_DIR = BACKEND_DIR / "data"
# Bruk absolutt sti med forward slashes – fungerer med SQLAlchemy/SQLite på Windows
_db_path = (DEFAULT_DATA_DIR.absolute() / "treningsanalyse.db").resolve()
DEFAULT_DATABASE_URL = "sqlite:///" + str(_db_path).replace("\\", "/")

# Sett opp token-mappe
TOKEN_DIR = BACKEND_DIR / "tokens"
token_dir_str = str(TOKEN_DIR.absolute())
os.makedirs(token_dir_str, exist_ok=True)
# print(f"Token-mappe opprettet: {token_dir_str}") # Kan kommenteres ut for produksjon

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        case_sensitive=True,
    )

    # Database URL
    DATABASE_URL: str = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    
    # Garmin Connect API konfigurasjon
    # VIKTIG: Sett disse som miljøvariabler i .env-filen!
    GARMIN_EMAIL: str = os.getenv("GARMIN_EMAIL", "")
    GARMIN_PASSWORD: str = os.getenv("GARMIN_PASSWORD", "")
    TOKEN_DIR: str = os.getenv("TOKEN_DIR", token_dir_str)
    
    # Lactate threshold speed konfigurasjon (i m/s)
    # Dette kan settes manuelt hvis ikke tilgjengelig via Garmin API
    LACTATE_THRESHOLD_SPEED: Optional[float] = 1000 / (5 * 60 + 22)  # m/s, tilsvarer 5:22 min/km pace
    
    # Data Storage konfigurasjon
    DATA_DIR: str = os.getenv("DATA_DIR", str(DEFAULT_DATA_DIR.absolute()))
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Redis (valgfritt — raskere cache for TSS/power/sammendrag)
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "true").lower() in ("1", "true", "yes")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD") or None

    # MET Weather API
    MET_API_USER_AGENT: str = os.getenv(
        "MET_API_USER_AGENT",
        "Treningsanalyse/1.0 (tim-agent)",
    )
    # Frost API (historisk vær) — https://frost.met.no
    FROST_CLIENT_ID: str = os.getenv("FROST_CLIENT_ID", "")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Følgende print-setninger er nyttige for debugging, men kan fjernes/reduseres i prod.
        # print(f"Innstillinger initialisert med:")
        # print(f"- E-post: {self.GARMIN_EMAIL}")
        # print(f"- Token-mappe: {self.TOKEN_DIR}")
        # print(f"- Min Request Interval: {self.GARMIN_MIN_REQUEST_INTERVAL}")
        # print(f"- Max Retries: {self.GARMIN_MAX_RETRIES}")
        # print(f"- Retry Delay: {self.GARMIN_RETRY_DELAY}")
        # print(f"- Sync Month Delay: {self.GARMIN_SYNC_MONTH_DELAY}")
        
        # Verifiser at token-mappen eksisterer
        token_path = Path(self.TOKEN_DIR)
        token_path.mkdir(parents=True, exist_ok=True)
        # print(f"Token-mappe verifisert: {self.TOKEN_DIR}")
        # Verifiser at data-mappen eksisterer
        Path(self.DATA_DIR).mkdir(parents=True, exist_ok=True)
        # print(f"Storage data-mappe verifisert: {self.DATA_DIR}")

settings = Settings()
# print(f"Innstillinger lastet med token-mappe: {settings.TOKEN_DIR}")
# print(f"Innstillinger lastet med data-mappe: {settings.DATA_DIR}")


def data_path(*parts: str) -> Path:
    """Bygger absolutt sti under konfigurert DATA_DIR."""
    return Path(settings.DATA_DIR).joinpath(*parts)
