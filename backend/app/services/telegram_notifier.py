"""Telegram-varsling for Garmin-synk.

Brukes primært til å varsle når Garmin-autentisering krever manuell re-innlogging
(401/MFA/endret passord). Modulen har ingen harde avhengigheter utover `requests`
og er trygg å bruke uten konfigurasjon (da blir varsling en no-op).
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramNotifier:
    """Sender enkle tekstmeldinger til en Telegram-chat via Bot API.

    - Varsling er en no-op hvis `bot_token`/`chat_id` mangler eller `enabled=False`.
    - Innebygd cooldown hindrer spam når samme feil oppstår gjentatte ganger
      (f.eks. hver dag under en mislykket synk).
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: bool = True,
        cooldown_seconds: int = 1800,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.bot_token = (bot_token or "").strip()
        self.chat_id = (chat_id or "").strip()
        self.enabled = bool(enabled)
        self.cooldown_seconds = max(0, int(cooldown_seconds))
        self.timeout_seconds = timeout_seconds
        self._last_sent_at: dict[str, float] = {}
        self._lock = Lock()

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.bot_token and self.chat_id)

    def _should_send(self, dedupe_key: Optional[str]) -> bool:
        if not dedupe_key or self.cooldown_seconds == 0:
            return True
        now = time.monotonic()
        with self._lock:
            last = self._last_sent_at.get(dedupe_key)
            if last is not None and (now - last) < self.cooldown_seconds:
                return False
            self._last_sent_at[dedupe_key] = now
            return True

    def notify(self, message: str, *, dedupe_key: Optional[str] = None) -> bool:
        """Send en melding. Returnerer True hvis meldingen faktisk ble sendt.

        Kaster aldri – varsling skal aldri velte selve synken.
        """
        if not self.is_configured:
            logger.debug("Telegram-varsling ikke konfigurert – hopper over: %s", message)
            return False

        if not self._should_send(dedupe_key):
            logger.info("Telegram-varsling undertrykt av cooldown (%s)", dedupe_key)
            return False

        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage"
        try:
            response = requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "disable_web_page_preview": True,
                },
                timeout=self.timeout_seconds,
            )
            if response.status_code >= 400:
                logger.warning(
                    "Telegram-varsling feilet (HTTP %s): %s",
                    response.status_code,
                    response.text[:200],
                )
                return False
            logger.info("Telegram-varsling sendt.")
            return True
        except Exception as exc:  # noqa: BLE001 – varsling skal aldri velte synk
            logger.warning("Telegram-varsling kastet unntak: %s", exc)
            return False

    def notify_reauth_required(self, reason: str) -> bool:
        """Varsle om at Garmin-innlogging må fornyes manuelt."""
        message = (
            "\u26a0\ufe0f Treningsanalyse: Garmin-innlogging må fornyes.\n\n"
            f"Årsak: {reason}\n\n"
            "Automatisk synk er satt på pause til ny innlogging (og evt. MFA-kode) "
            "er utført. Kjør innlogging på nytt for å gjenoppta synk."
        )
        return self.notify(message, dedupe_key="garmin_reauth_required")


def build_notifier_from_settings(settings_obj) -> TelegramNotifier:
    """Bygger en TelegramNotifier fra app-innstillinger."""
    return TelegramNotifier(
        bot_token=getattr(settings_obj, "TELEGRAM_BOT_TOKEN", ""),
        chat_id=getattr(settings_obj, "TELEGRAM_CHAT_ID", ""),
        enabled=getattr(settings_obj, "TELEGRAM_ENABLED", True),
        cooldown_seconds=getattr(settings_obj, "TELEGRAM_REAUTH_COOLDOWN_SECONDS", 1800),
    )
