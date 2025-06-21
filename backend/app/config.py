from pydantic_settings import BaseSettings
from pathlib import Path
import os
from dotenv import load_dotenv

# Få absolutt sti til backend-mappen
BACKEND_DIR = Path(__file__).parent.parent.absolute()
ENV_FILE = BACKEND_DIR / ".env"

# Last miljøvariabler fra riktig sti
load_dotenv(dotenv_path=ENV_FILE)
# print(f"Laster miljøvariabler fra: {ENV_FILE}") # Kan kommenteres ut for produksjon

# Standard data-mappe (relativt til backend-mappen hvis ikke absolutt sti er gitt i .env)
DEFAULT_DATA_DIR = BACKEND_DIR / "data"

# Sett opp token-mappe
TOKEN_DIR = BACKEND_DIR / "tokens"
token_dir_str = str(TOKEN_DIR.absolute())
os.makedirs(token_dir_str, exist_ok=True)
# print(f"Token-mappe opprettet: {token_dir_str}") # Kan kommenteres ut for produksjon

class Settings(BaseSettings):
    # Garmin Connect konfigurasjon
    GARMIN_EMAIL: str = os.getenv("GARMIN_EMAIL", "").strip('"')
    GARMIN_PASSWORD: str = os.getenv("GARMIN_PASSWORD", "").strip('"')
    
    # Token lagring
    TOKEN_DIR: str = token_dir_str
    
    # Data Storage konfigurasjon
    DATA_DIR: str = os.getenv("DATA_DIR", str(DEFAULT_DATA_DIR.absolute()))
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        env_file = str(ENV_FILE)
        case_sensitive = True

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
