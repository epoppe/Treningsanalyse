"""Applikasjonsinnstillinger via pydantic-settings.

Miljøvariabler og `.env` leses av BaseSettings — ikke via manuell os.getenv
på feltene (unngår dobbelt lasting og type-feil).

Desktop-modus: sett TRAININGSANALYSE_DATA_DIR (AppData) før prosess-start.
Da utledes DATA_DIR / TOKEN_DIR / FIT / cache / logs / backups under den roten
med mindre eksplisitte overrides er satt.

Viktig: Denne modulen må ikke skrive til filsystemet ved import.
Program Files / PyInstaller resources er read-only — mkdir skjer først når
Settings er ferdig resolvert (typisk under AppData).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolutt sti til backend-mappen (kilde / utviklingslayout / PyInstaller _internal).
# Kun for default-verdier og lesing av .env — aldri for mutable runtime-data.
BACKEND_DIR = Path(__file__).parent.parent.absolute()
ENV_FILE = BACKEND_DIR / ".env"

# Last .env tidlig slik at annen kode som leser os.environ også ser verdiene.
# Desktop/Electron setter miljøvariabler før oppstart — de vinner over .env.
# load_dotenv leser bare; den oppretter ikke filer.
load_dotenv(dotenv_path=ENV_FILE, override=False)

# Konseptuelle defaults (ingen mkdir ved import)
DEFAULT_DATA_DIR = BACKEND_DIR / "data"
DEFAULT_TOKEN_DIR = str((BACKEND_DIR / "tokens").absolute())
_db_path = (DEFAULT_DATA_DIR.absolute() / "treningsanalyse.db").resolve()
DEFAULT_DATABASE_URL = "sqlite:///" + str(_db_path).replace("\\", "/")

# Standard LTHR-pace 5:22 min/km → m/s
_DEFAULT_LTHR_SPEED = 1000 / (5 * 60 + 22)


def sqlite_url_for_path(db_path: Path | str) -> str:
    """Bygg SQLAlchemy SQLite-URL fra filsti (Windows-sikkert)."""
    resolved = Path(db_path).expanduser().resolve()
    return "sqlite:///" + str(resolved).replace("\\", "/")


def path_from_sqlite_url(url: str) -> Optional[Path]:
    """Hent filsti fra sqlite:///…-URL. Returnerer None for :memory: eller ikke-sqlite."""
    if not url.startswith("sqlite"):
        return None
    if ":memory:" in url:
        return None
    # Prefer absolute forms produced by sqlite_url_for_path:
    #   sqlite:////abs/path     (Unix)
    #   sqlite:///C:/abs/path   (Windows)
    marker = ":///"
    idx = url.find(marker)
    if idx < 0:
        return None
    raw = url[idx + len(marker) :]
    return Path(raw)


def ensure_runtime_directories(settings: "Settings") -> None:
    """Opprett mutable kataloger etter at Settings er ferdig resolvert.

    Kalles fra apply_data_root — aldri ved module import.
    """
    for path in (
        settings.TOKEN_DIR,
        settings.DATA_DIR,
        settings.FIT_DATA_DIR,
        settings.CACHE_DIR,
        settings.LOG_DIR,
        settings.BACKUP_DIR,
        settings.EXPORT_DIR,
    ):
        if path:
            Path(path).mkdir(parents=True, exist_ok=True)


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _assert_desktop_paths_writable(settings: "Settings", root: Path) -> None:
    """I desktop-modus skal ingen mutable sti ligge under pakke-/BACKEND_DIR."""
    package_roots = [BACKEND_DIR]
    # PyInstaller extract dir when frozen
    import sys

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        package_roots.append(Path(meipass))

    candidates = [
        ("TOKEN_DIR", settings.TOKEN_DIR),
        ("DATA_DIR", settings.DATA_DIR),
        ("FIT_DATA_DIR", settings.FIT_DATA_DIR),
        ("CACHE_DIR", settings.CACHE_DIR),
        ("LOG_DIR", settings.LOG_DIR),
        ("BACKUP_DIR", settings.BACKUP_DIR),
        ("EXPORT_DIR", settings.EXPORT_DIR),
    ]
    for name, raw in candidates:
        if not raw:
            continue
        path = Path(raw)
        if not _is_under(path, root):
            raise RuntimeError(
                f"Desktop mode: {name}={path} must be under TRAININGSANALYSE_DATA_DIR={root}"
            )
        for pkg in package_roots:
            if _is_under(path, pkg):
                raise RuntimeError(
                    f"Desktop mode: {name}={path} must not resolve under package dir {pkg}"
                )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Desktop / portable data root (Electron AppData). Når satt, utledes undermapper.
    TRAININGSANALYSE_DATA_DIR: Optional[str] = None

    # Database — overstyr med full URL (sqlite:///… eller postgresql+psycopg://…)
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

    # Mutable storage roots
    DATA_DIR: str = str(DEFAULT_DATA_DIR.absolute())
    FIT_DATA_DIR: Optional[str] = None
    CACHE_DIR: Optional[str] = None
    LOG_DIR: Optional[str] = None
    BACKUP_DIR: Optional[str] = None
    EXPORT_DIR: Optional[str] = None

    # Desktop shell flag (Electron setter true)
    DESKTOP_MODE: bool = False

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
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002"
    )
    ALLOWED_HOSTS: str = ""
    DEBUG: bool = False
    ENVIRONMENT: str = "local"
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
        "TRAININGSANALYSE_DATA_DIR",
        "FIT_DATA_DIR",
        "CACHE_DIR",
        "LOG_DIR",
        "BACKUP_DIR",
        "EXPORT_DIR",
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

    @model_validator(mode="after")
    def apply_data_root(self) -> "Settings":
        """Når TRAININGSANALYSE_DATA_DIR er satt, utled undermapper / default DB."""
        root_raw = self.TRAININGSANALYSE_DATA_DIR
        if self.DESKTOP_MODE and not root_raw:
            raise RuntimeError(
                "DESKTOP_MODE=true krever TRAININGSANALYSE_DATA_DIR "
                "(Electron AppData). Mutable data kan ikke lagres under Program Files."
            )

        if root_raw:
            root = Path(root_raw).expanduser().resolve()
            # Kun overstyr hvis felt fortsatt er default / unset
            default_data = str(DEFAULT_DATA_DIR.absolute())
            if self.DATA_DIR == default_data or not self.DATA_DIR:
                object.__setattr__(self, "DATA_DIR", str(root / "data"))
            if self.TOKEN_DIR == DEFAULT_TOKEN_DIR:
                object.__setattr__(self, "TOKEN_DIR", str(root / "tokens"))
            if self.FIT_DATA_DIR is None:
                object.__setattr__(self, "FIT_DATA_DIR", str(root / "fit"))
            if self.CACHE_DIR is None:
                object.__setattr__(self, "CACHE_DIR", str(root / "cache"))
            if self.LOG_DIR is None:
                object.__setattr__(self, "LOG_DIR", str(root / "logs"))
            if self.BACKUP_DIR is None:
                object.__setattr__(self, "BACKUP_DIR", str(root / "backups"))
            if self.EXPORT_DIR is None:
                object.__setattr__(self, "EXPORT_DIR", str(root / "exports"))
            # DATABASE_URL: overstyr kun hvis fortsatt default repo-DB
            if self.DATABASE_URL == DEFAULT_DATABASE_URL:
                object.__setattr__(
                    self,
                    "DATABASE_URL",
                    sqlite_url_for_path(Path(self.DATA_DIR) / "treningsanalyse.db"),
                )
            if self.DESKTOP_MODE:
                _assert_desktop_paths_writable(self, root)
        else:
            # Dev defaults for optional dirs under DATA_DIR
            data = Path(self.DATA_DIR)
            if self.FIT_DATA_DIR is None:
                object.__setattr__(self, "FIT_DATA_DIR", str(data / "fit"))
            if self.CACHE_DIR is None:
                object.__setattr__(self, "CACHE_DIR", str(data / "cache"))
            if self.LOG_DIR is None:
                object.__setattr__(self, "LOG_DIR", str(data / "logs"))
            if self.BACKUP_DIR is None:
                object.__setattr__(self, "BACKUP_DIR", str(data / "backups"))
            if self.EXPORT_DIR is None:
                object.__setattr__(self, "EXPORT_DIR", str(data / "exports"))

        ensure_runtime_directories(self)
        return self

    def model_post_init(self, __context: object) -> None:
        # Directories are ensured in apply_data_root (after validation).
        return

    @property
    def database_url(self) -> str:
        """Alias for klarere API — samme som DATABASE_URL."""
        return self.DATABASE_URL

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def sqlite_db_path(self) -> Optional[Path]:
        return path_from_sqlite_url(self.DATABASE_URL)

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


def reset_settings_cache() -> None:
    """For tester / desktop — tøm Settings-singleton før re-init med nye env-verdier."""
    get_settings.cache_clear()


def __getattr__(name: str):
    """Lazy `settings` — unngår filsystemskriving ved `import app.config`."""
    if name == "settings":
        return get_settings()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted([*globals().keys(), "settings"])


def data_path(*parts: str) -> Path:
    """Bygger absolutt sti under konfigurert DATA_DIR."""
    return Path(get_settings().DATA_DIR).joinpath(*parts)
