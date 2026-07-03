"""Tester for garminconnect-basert Garmin-auth, token-cache, auto-refresh,
kontrollert feiling (401/MFA) og Telegram-varsling."""

import json
import tempfile
import unittest
from pathlib import Path

from garminconnect.exceptions import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from app.services.garmin_auth import (
    GarminApiError,
    GarminAuthManager,
    GarminMFARequiredError,
    GarminNotFoundError,
    GarminRateLimitError,
    GarminReauthRequiredError,
    NATIVE_TOKEN_FILENAME,
    LEGACY_GARTH_OAUTH2_FILENAME,
)


class FakeInnerClient:
    """Etterligner garminconnect.client.Client sin relevante overflate."""

    def __init__(self):
        self.is_authenticated = False
        self.expires_soon = False
        self.refresh_count = 0
        self._tokenstore_path = None
        self.dump_count = 0

    def _token_expires_soon(self):
        return self.expires_soon

    def _refresh_session(self):
        self.refresh_count += 1
        self.expires_soon = False

    def dump(self, path):
        self.dump_count += 1
        p = Path(path)
        if p.is_dir() or not p.name.endswith(".json"):
            p = p / "garmin_tokens.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        # Ekte dump skriver gjeldende (allerede lastede) tokens. For testene bevarer
        # vi eksisterende cache-innhold og skriver kun ny fil ved fersk login.
        if not p.is_file():
            p.write_text(json.dumps({"di_token": "fresh", "di_refresh_token": "fresh-r", "di_client_id": None}))


class FakeGarmin:
    """Etterligner garminconnect.Garmin sin relevante overflate."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.return_on_mfa = kwargs.get("return_on_mfa", False)
        self.display_name = None
        self.client = FakeInnerClient()

        # Testkonfigurerbar oppførsel
        self.login_result = (None, None)
        self.login_exc = None
        self.authed_after_login = True
        self.login_calls = []
        self.connectapi_hook = None
        self.download_hook = None

    def login(self, tokenstore=None):
        self.login_calls.append(tokenstore)
        if self.login_exc is not None:
            raise self.login_exc
        if self.login_result and self.login_result[0] == "needs_mfa":
            return self.login_result
        if self.authed_after_login:
            self.client.is_authenticated = True
            # Speiler garminconnect: profil (display_name) lastes kun når tokens
            # lastes fra cache. Ved fersk credential-login (return_on_mfa) forblir
            # display_name None inntil GarminAuthManager._finalize_after_login kaller
            # _load_profile_and_settings().
            if tokenstore and Path(tokenstore).is_file():
                self.display_name = "fake-display-name"
        return self.login_result

    def _load_profile_and_settings(self):
        self.display_name = "fake-display-name"

    def connectapi(self, path, **kwargs):
        if self.connectapi_hook is not None:
            return self.connectapi_hook(path, **kwargs)
        return {"path": path, "kwargs": kwargs}

    def download(self, path, **kwargs):
        if self.download_hook is not None:
            return self.download_hook(path, **kwargs)
        return b"fit-bytes"


class RecordingNotifier:
    def __init__(self):
        self.reauth_reasons = []

    def notify_reauth_required(self, reason):
        self.reauth_reasons.append(reason)
        return True


def build_manager(tmpdir, fake, notifier=None):
    mgr = GarminAuthManager(
        email="user@example.com",
        password="secret",
        token_dir=tmpdir,
        notifier=notifier,
    )
    # Injiser fake garminconnect.Garmin
    mgr._build_garmin = lambda: fake
    return mgr


class GarminAuthManagerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _write_native_token(self):
        Path(self.tmpdir, NATIVE_TOKEN_FILENAME).write_text(
            json.dumps({"di_token": "t", "di_refresh_token": "r", "di_client_id": "c"})
        )

    # 1) Bruke lagret token/session
    def test_authenticate_uses_saved_token(self):
        self._write_native_token()
        fake = FakeGarmin()
        notifier = RecordingNotifier()
        mgr = build_manager(self.tmpdir, fake, notifier)

        self.assertTrue(mgr.authenticate())
        self.assertTrue(mgr.is_authenticated)
        self.assertEqual(mgr.display_name, "fake-display-name")
        # login skal ha fått token-cache-stien
        self.assertEqual(fake.login_calls[-1], mgr.token_path)
        self.assertEqual(notifier.reauth_reasons, [])

    def test_authenticate_credential_login_when_no_token(self):
        fake = FakeGarmin()
        mgr = build_manager(self.tmpdir, fake)
        self.assertTrue(mgr.authenticate())
        self.assertTrue(mgr.is_authenticated)

    def test_fresh_login_persists_token_cache_and_loads_profile(self):
        """Fersk credential-login skal lagre token-cache og sette display_name."""
        fake = FakeGarmin()
        mgr = build_manager(self.tmpdir, fake)
        self.assertTrue(mgr.authenticate())
        # Token-cache skal være skrevet for gjenbruk neste kjøring
        self.assertTrue(Path(mgr.token_path).is_file())
        self.assertGreaterEqual(fake.client.dump_count, 1)
        # display_name skal være lastet via _load_profile_and_settings
        self.assertEqual(mgr.display_name, "fake-display-name")
        # Fremtidige refresher skal peke på samme cache
        self.assertEqual(fake.client._tokenstore_path, mgr.token_path)

    # 3) Kontrollert feiling ved MFA
    def test_authenticate_mfa_raises_and_notifies(self):
        fake = FakeGarmin()
        fake.login_result = ("needs_mfa", None)
        notifier = RecordingNotifier()
        mgr = build_manager(self.tmpdir, fake, notifier)

        with self.assertRaises(GarminMFARequiredError):
            mgr.authenticate()
        self.assertFalse(mgr.is_authenticated)
        self.assertEqual(len(notifier.reauth_reasons), 1)
        self.assertIn("MFA", notifier.reauth_reasons[0])

    # 3) Kontrollert feiling ved 401 / endret pålogging
    def test_authenticate_401_raises_reauth_and_notifies(self):
        fake = FakeGarmin()
        fake.login_exc = GarminConnectAuthenticationError("401 Unauthorized")
        notifier = RecordingNotifier()
        mgr = build_manager(self.tmpdir, fake, notifier)

        with self.assertRaises(GarminReauthRequiredError):
            mgr.authenticate()
        self.assertFalse(mgr.is_authenticated)
        self.assertEqual(len(notifier.reauth_reasons), 1)

    def test_authenticate_rate_limit_does_not_notify_reauth(self):
        fake = FakeGarmin()
        fake.login_exc = GarminConnectTooManyRequestsError("429")
        notifier = RecordingNotifier()
        mgr = build_manager(self.tmpdir, fake, notifier)

        with self.assertRaises(GarminRateLimitError):
            mgr.authenticate()
        self.assertEqual(notifier.reauth_reasons, [])

    def test_authenticate_connection_error_maps_to_api_error(self):
        fake = FakeGarmin()
        fake.login_exc = GarminConnectConnectionError("boom")
        mgr = build_manager(self.tmpdir, fake)
        with self.assertRaises(GarminApiError):
            mgr.authenticate()

    # 2) Auto-refresh før API-kall
    def test_ensure_session_refreshes_when_token_expiring(self):
        self._write_native_token()
        fake = FakeGarmin()
        mgr = build_manager(self.tmpdir, fake)
        mgr.authenticate()

        fake.client.expires_soon = True
        mgr.ensure_session()
        self.assertEqual(fake.client.refresh_count, 1)

    def test_ensure_session_reauthenticates_when_session_lost(self):
        fake = FakeGarmin()
        mgr = build_manager(self.tmpdir, fake)
        # Ikke autentisert ennå -> ensure_session skal logge inn
        mgr.ensure_session()
        self.assertTrue(mgr.is_authenticated)

    # connectapi feiloversettelse
    def test_connectapi_success_calls_ensure_session_then_returns(self):
        self._write_native_token()
        fake = FakeGarmin()
        mgr = build_manager(self.tmpdir, fake)
        mgr.authenticate()
        fake.client.expires_soon = True
        result = mgr.connectapi("/some/endpoint", params={"a": 1})
        # auto-refresh skjedde før kallet
        self.assertEqual(fake.client.refresh_count, 1)
        self.assertEqual(result["path"], "/some/endpoint")

    def test_connectapi_401_translates_to_reauth_and_notifies(self):
        self._write_native_token()
        fake = FakeGarmin()
        notifier = RecordingNotifier()
        mgr = build_manager(self.tmpdir, fake, notifier)
        mgr.authenticate()

        def hook(path, **kwargs):
            raise GarminConnectAuthenticationError("401 Unauthorized")

        fake.connectapi_hook = hook
        with self.assertRaises(GarminReauthRequiredError):
            mgr.connectapi("/x")
        self.assertEqual(len(notifier.reauth_reasons), 1)

    def test_connectapi_404_translates_to_not_found(self):
        self._write_native_token()
        fake = FakeGarmin()
        mgr = build_manager(self.tmpdir, fake)
        mgr.authenticate()

        def hook(path, **kwargs):
            raise GarminConnectConnectionError("API Error 404 - not found")

        fake.connectapi_hook = hook
        with self.assertRaises(GarminNotFoundError):
            mgr.connectapi("/x")

    def test_connectapi_429_translates_to_rate_limit(self):
        self._write_native_token()
        fake = FakeGarmin()
        mgr = build_manager(self.tmpdir, fake)
        mgr.authenticate()

        def hook(path, **kwargs):
            raise GarminConnectTooManyRequestsError("429")

        fake.connectapi_hook = hook
        with self.assertRaises(GarminRateLimitError):
            mgr.connectapi("/x")

    def test_download_500_translates_to_api_error(self):
        self._write_native_token()
        fake = FakeGarmin()
        mgr = build_manager(self.tmpdir, fake)
        mgr.authenticate()

        def hook(path, **kwargs):
            raise GarminConnectConnectionError("API Error 500 - server")

        fake.download_hook = hook
        with self.assertRaises(GarminApiError):
            mgr.download("/download/x")

    # Legacy garth-token -> native migrering (kun lest som fallback)
    def test_legacy_garth_token_migrated_to_native_cache(self):
        legacy = {
            "scope": "CONNECT_READ",
            "token_type": "Bearer",
            "access_token": "legacy-access",
            "refresh_token": "legacy-refresh",
            "expires_at": 9999999999,
        }
        Path(self.tmpdir, LEGACY_GARTH_OAUTH2_FILENAME).write_text(json.dumps(legacy))

        fake = FakeGarmin()
        mgr = build_manager(self.tmpdir, fake)
        self.assertTrue(mgr.authenticate())

        native_path = Path(mgr.token_path)
        self.assertTrue(native_path.is_file())
        native = json.loads(native_path.read_text())
        self.assertEqual(native["di_token"], "legacy-access")
        self.assertEqual(native["di_refresh_token"], "legacy-refresh")
        # login skal ha brukt den migrerte native-cachen
        self.assertEqual(fake.login_calls[-1], mgr.token_path)

    def test_legacy_migration_skipped_when_native_exists(self):
        self._write_native_token()
        Path(self.tmpdir, LEGACY_GARTH_OAUTH2_FILENAME).write_text(
            json.dumps({"access_token": "legacy", "refresh_token": "legacy-r"})
        )
        fake = FakeGarmin()
        mgr = build_manager(self.tmpdir, fake)
        mgr.authenticate()
        native = json.loads(Path(mgr.token_path).read_text())
        # Native cache skal IKKE overskrives av legacy
        self.assertEqual(native["di_token"], "t")


if __name__ == "__main__":
    unittest.main()
