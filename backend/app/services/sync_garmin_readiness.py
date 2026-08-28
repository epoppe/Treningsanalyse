"""Garmin-synk readiness — sjekk credentials/tokens før sync startes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..config import settings
from ..services.garmin_auth import LEGACY_GARTH_OAUTH2_FILENAME, NATIVE_TOKEN_FILENAME
from ..services.garmin_client import GarminClient


def _token_dir() -> Path:
    return Path(settings.TOKEN_DIR).expanduser()


def has_garmin_token_cache() -> bool:
    token_dir = _token_dir()
    native = token_dir / NATIVE_TOKEN_FILENAME
    legacy = token_dir / LEGACY_GARTH_OAUTH2_FILENAME
    if settings.GARMIN_TOKEN_FILE:
        return Path(settings.GARMIN_TOKEN_FILE).expanduser().is_file()
    return native.is_file() or legacy.is_file()


def garmin_credentials_configured() -> bool:
    email = (settings.GARMIN_EMAIL or "").strip()
    password = (settings.GARMIN_PASSWORD or "").strip()
    return bool(email and password)


def build_garmin_sync_status(garmin_client: Optional[GarminClient] = None) -> Dict[str, Any]:
    """Returnerer status for UI og pre-flight før synk."""
    email = (settings.GARMIN_EMAIL or "").strip()
    has_tokens = has_garmin_token_cache()
    has_credentials = garmin_credentials_configured()
    user_env = None
    if settings.TRAININGSANALYSE_DATA_DIR:
        user_env = str(
            Path(settings.TRAININGSANALYSE_DATA_DIR).expanduser().resolve() / "config" / ".env"
        )

    ready = has_tokens or has_credentials
    if garmin_client is not None and garmin_client.is_authenticated():
        auth_state = "authenticated"
    elif has_tokens:
        auth_state = "token_cache"
    elif has_credentials:
        auth_state = "credentials_only"
    else:
        auth_state = "missing"

    detail = None
    if not ready:
        if settings.DESKTOP_MODE:
            detail = (
                "Garmin Connect er ikke konfigurert. Åpne Fil → Garmin-innstillinger i desktop-appen "
                "og fyll inn GARMIN_EMAIL og GARMIN_PASSWORD i config/.env under AppData. "
                "Alternativt: kopier tokens/garmin_tokens.json fra tidligere installasjon til tokens/."
            )
        else:
            detail = (
                "Garmin Connect er ikke konfigurert. Sett GARMIN_EMAIL og GARMIN_PASSWORD i backend/.env, "
                "eller legg inn tokens under TOKEN_DIR."
            )

    return {
        "ready": ready,
        "auth_state": auth_state,
        "has_credentials": has_credentials,
        "has_token_cache": has_tokens,
        "email_configured": bool(email),
        "masked_email": settings.masked_garmin_email(),
        "token_dir": str(_token_dir()),
        "desktop_mode": settings.DESKTOP_MODE,
        "config_env_path": user_env,
        "detail": detail,
    }


def assert_garmin_sync_ready(garmin_client: Optional[GarminClient] = None) -> None:
    """Kaster HTTPException(422) når Garmin ikke er konfigurert for synk."""
    from fastapi import HTTPException

    status = build_garmin_sync_status(garmin_client)
    if status["ready"]:
        return
    raise HTTPException(status_code=422, detail=status["detail"])
