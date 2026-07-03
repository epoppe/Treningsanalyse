"""Garmin-autentisering og token-cache basert på python-garminconnect.

Denne modulen erstatter garth for innlogging og token-fornyelse. garth brukes
IKKE lenger for ny innlogging eller token-renewal – en eksisterende garth-token
behandles kun som en midlertidig legacy fallback (leses én gang og migreres inn
i garminconnect sin token-cache).

Ansvar:
- Innlogging med lagret token/session når den finnes.
- Auto-refresh av token før API-kall (garminconnect fornyer DI-token internt før
  hvert kall når det er nær utløp; `ensure_session()` gjør dette eksplisitt og
  testbart).
- Kontrollert feiling ved 401 / MFA / endret pålogging (typede unntak).
- Telegram-varsling når manuell re-innlogging kreves.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from garminconnect import Garmin
from garminconnect.exceptions import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

logger = logging.getLogger(__name__)

# Filnavn for garminconnect sin native token-cache (di_token/di_refresh_token).
NATIVE_TOKEN_FILENAME = "garmin_tokens.json"
# Legacy garth-token (kun lest som midlertidig fallback, aldri skrevet/fornyet).
LEGACY_GARTH_OAUTH2_FILENAME = "oauth2_token.json"


# --------------------------------------------------------------------------- #
#  Typede unntak for kontrollert feilhåndtering                                #
# --------------------------------------------------------------------------- #


class GarminAuthError(Exception):
    """Basisklasse for kontrollerte Garmin-autentiseringsfeil."""


class GarminReauthRequiredError(GarminAuthError):
    """Kastes ved 401 / ugyldige tokens / endret pålogging – krever ny innlogging."""


class GarminMFARequiredError(GarminReauthRequiredError):
    """Kastes når Garmin krever MFA/2FA-kode for å fullføre innlogging."""


class GarminRateLimitError(Exception):
    """Kastes ved HTTP 429 (rate limiting) fra Garmin."""


class GarminNotFoundError(Exception):
    """Kastes ved HTTP 404 / manglende data for en ressurs."""


class GarminApiError(Exception):
    """Kastes ved øvrige API-/nettverksfeil mot Garmin."""


def is_not_found_error(error: Exception) -> bool:
    """Sjekker om et unntak representerer 'ingen data' (404/not found)."""
    if isinstance(error, GarminNotFoundError):
        return True
    text = str(error).lower()
    return "404" in str(error) or "not found" in text or "no data" in text


# --------------------------------------------------------------------------- #
#  Auth-manager                                                                #
# --------------------------------------------------------------------------- #


class GarminAuthManager:
    """Håndterer innlogging, token-cache og auto-refresh mot Garmin Connect."""

    def __init__(
        self,
        email: str,
        password: str,
        token_dir: str,
        token_file: Optional[str] = None,
        notifier: Any = None,
        is_cn: bool = False,
    ) -> None:
        self.email = email
        self.password = password
        self.token_dir = Path(token_dir)
        self._token_file = token_file
        self.notifier = notifier
        self.is_cn = is_cn
        self._garmin: Optional[Garmin] = None
        self._authenticated = False

    # ------------------------------------------------------------------ #
    #  Stier                                                             #
    # ------------------------------------------------------------------ #

    @property
    def token_path(self) -> str:
        """Sti til garminconnect sin native token-cache."""
        if self._token_file:
            return str(Path(self._token_file).expanduser())
        return str(self.token_dir / NATIVE_TOKEN_FILENAME)

    @property
    def legacy_garth_oauth2_path(self) -> Path:
        return self.token_dir / LEGACY_GARTH_OAUTH2_FILENAME

    def _native_token_exists(self) -> bool:
        return Path(self.token_path).is_file()

    # ------------------------------------------------------------------ #
    #  Klient-oppsett                                                    #
    # ------------------------------------------------------------------ #

    def _build_garmin(self) -> Garmin:
        # return_on_mfa=True: vi kjører hodeløst (server). Krever Garmin MFA,
        # feiler vi kontrollert i stedet for å blokkere på interaktiv prompt.
        return Garmin(
            email=self.email,
            password=self.password,
            is_cn=self.is_cn,
            return_on_mfa=True,
        )

    @property
    def client(self) -> Garmin:
        if self._garmin is None:
            self._garmin = self._build_garmin()
        return self._garmin

    @property
    def display_name(self) -> Optional[str]:
        if self._garmin is None:
            return None
        return getattr(self._garmin, "display_name", None)

    @property
    def is_authenticated(self) -> bool:
        if self._garmin is None:
            return False
        client = getattr(self._garmin, "client", None)
        return bool(self._authenticated and client is not None and client.is_authenticated)

    # ------------------------------------------------------------------ #
    #  Legacy garth-token → native migrering (kun lest, aldri fornyet)   #
    # ------------------------------------------------------------------ #

    def _maybe_migrate_legacy_garth_token(self) -> bool:
        """Migrerer en eksisterende garth oauth2-token til native cache én gang.

        Leser kun JSON-filen garth tidligere skrev; garth-biblioteket brukes ikke.
        Returnerer True hvis en native token-cache ble opprettet fra legacy.
        """
        if self._native_token_exists():
            return False
        legacy_path = self.legacy_garth_oauth2_path
        if not legacy_path.is_file():
            return False

        try:
            legacy = json.loads(legacy_path.read_text())
        except Exception as exc:
            logger.warning("Kunne ikke lese legacy garth-token (%s): %s", legacy_path, exc)
            return False

        access_token = legacy.get("access_token")
        refresh_token = legacy.get("refresh_token")
        if not access_token or not refresh_token:
            logger.info("Legacy garth-token mangler access/refresh – hopper over migrering.")
            return False

        native_payload = {
            "di_token": access_token,
            "di_refresh_token": refresh_token,
            # di_client_id utledes fra JWT av garminconnect ved behov.
            "di_client_id": None,
        }
        try:
            native_path = Path(self.token_path)
            native_path.parent.mkdir(parents=True, exist_ok=True)
            native_path.write_text(json.dumps(native_payload))
            logger.info(
                "Migrerte legacy garth-token til native garminconnect-cache (%s). "
                "garth brukes ikke for videre fornyelse.",
                native_path,
            )
            return True
        except Exception as exc:
            logger.warning("Kunne ikke skrive native token-cache fra legacy: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    #  Innlogging / session                                             #
    # ------------------------------------------------------------------ #

    def authenticate(self, force_relogin: bool = False) -> bool:
        """Logger inn mot Garmin. Bruker lagret token når mulig, ellers credentials.

        Rekkefølge:
        1. Bruk native token-cache (auto-refresh av DI-token skjer i garminconnect).
        2. Ellers: migrer evt. legacy garth-token inn i native cache og bruk den.
        3. Ellers: full credential-innlogging (native garminconnect auth).

        Kaster:
            GarminMFARequiredError: Garmin krever MFA-kode (kontrollert stopp).
            GarminReauthRequiredError: 401 / ugyldige tokens / endret pålogging.
            GarminRateLimitError: HTTP 429.
            GarminApiError: øvrige feil.
        """
        self._garmin = self._build_garmin()

        if force_relogin:
            try:
                Path(self.token_path).unlink(missing_ok=True)
            except Exception:
                pass

        # Bootstrap fra legacy garth-token hvis native cache mangler.
        self._maybe_migrate_legacy_garth_token()

        try:
            # login(tokenstore=...) laster lagret token og auto-refresher DI-token
            # proaktivt før bruk. Uten lagret token gjøres credential-innlogging,
            # og tokens skrives til `tokenstore` for neste kjøring.
            result = self.client.login(self.token_path)
            mfa_status = result[0] if isinstance(result, tuple) else None

            if mfa_status == "needs_mfa":
                self._authenticated = False
                reason = "Garmin krever MFA/2FA-kode for innlogging."
                self._notify_reauth(reason)
                raise GarminMFARequiredError(reason)

            self._authenticated = bool(self.client.client.is_authenticated)
            if not self._authenticated:
                reason = "Innlogging returnerte ingen gyldig token."
                self._notify_reauth(reason)
                raise GarminReauthRequiredError(reason)

            logger.info("Garmin-innlogging OK (display_name=%s).", self.display_name)
            return True

        except GarminMFARequiredError:
            raise
        except GarminConnectAuthenticationError as exc:
            self._authenticated = False
            reason = f"Autentisering feilet (401/ugyldige tokens eller endret pålogging): {exc}"
            self._notify_reauth(reason)
            raise GarminReauthRequiredError(reason) from exc
        except GarminConnectTooManyRequestsError as exc:
            self._authenticated = False
            raise GarminRateLimitError(f"Garmin rate limit ved innlogging: {exc}") from exc
        except GarminConnectConnectionError as exc:
            self._authenticated = False
            raise GarminApiError(f"Kunne ikke koble til Garmin ved innlogging: {exc}") from exc

    def ensure_session(self) -> None:
        """Sikrer gyldig session og auto-refresher token før API-kall.

        garminconnect fornyer DI-token internt før hvert kall når det nærmer seg
        utløp; her gjør vi det eksplisitt (og testbart) i tillegg, slik at en
        utløpt session oppdages og fornyes før selve dataforespørselen.
        """
        if not self.is_authenticated:
            # Ikke autentisert (eller session tapt) → forsøk full autentisering.
            self.authenticate()
            return

        client = self.client.client
        try:
            expires_soon = getattr(client, "_token_expires_soon", None)
            if callable(expires_soon) and expires_soon():
                logger.info("Garmin-token nær utløp – fornyer proaktivt før API-kall.")
                refresh = getattr(client, "_refresh_session", None)
                if callable(refresh):
                    refresh()
        except Exception as exc:
            logger.debug("Proaktiv token-refresh feilet (fortsetter): %s", exc)

    # ------------------------------------------------------------------ #
    #  API-kall med feiloversettelse                                    #
    # ------------------------------------------------------------------ #

    def _translate_error(self, exc: Exception) -> Exception:
        if isinstance(exc, GarminConnectAuthenticationError):
            reason = f"Garmin avviste forespørsel (401/auth): {exc}"
            self._notify_reauth(reason)
            self._authenticated = False
            return GarminReauthRequiredError(reason)
        if isinstance(exc, GarminConnectTooManyRequestsError):
            return GarminRateLimitError(str(exc))
        if isinstance(exc, GarminConnectConnectionError):
            if is_not_found_error(exc):
                return GarminNotFoundError(str(exc))
            return GarminApiError(str(exc))
        return GarminApiError(str(exc))

    def connectapi(self, path: str, **kwargs: Any) -> Any:
        """GET mot Garmin connectapi med auto-refresh og typede unntak."""
        self.ensure_session()
        try:
            return self.client.connectapi(path, **kwargs)
        except (
            GarminConnectAuthenticationError,
            GarminConnectTooManyRequestsError,
            GarminConnectConnectionError,
        ) as exc:
            raise self._translate_error(exc) from exc

    def download(self, path: str, **kwargs: Any) -> bytes:
        """Nedlasting (f.eks. FIT-fil) med auto-refresh og typede unntak."""
        self.ensure_session()
        try:
            return self.client.download(path, **kwargs)
        except (
            GarminConnectAuthenticationError,
            GarminConnectTooManyRequestsError,
            GarminConnectConnectionError,
        ) as exc:
            raise self._translate_error(exc) from exc

    # ------------------------------------------------------------------ #
    #  Hjelpere                                                          #
    # ------------------------------------------------------------------ #

    def _notify_reauth(self, reason: str) -> None:
        if self.notifier is None:
            return
        try:
            self.notifier.notify_reauth_required(reason)
        except Exception as exc:
            logger.debug("Telegram-varsling feilet: %s", exc)
