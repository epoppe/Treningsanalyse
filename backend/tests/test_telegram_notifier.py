"""Tester for TelegramNotifier (varsling ved re-auth)."""

import unittest
from unittest.mock import MagicMock, patch

from app.services.telegram_notifier import TelegramNotifier


class TelegramNotifierTests(unittest.TestCase):
    def test_not_configured_is_noop(self):
        notifier = TelegramNotifier(bot_token="", chat_id="", enabled=True)
        self.assertFalse(notifier.is_configured)
        with patch("app.services.telegram_notifier.requests.post") as post:
            self.assertFalse(notifier.notify("hei"))
            post.assert_not_called()

    def test_disabled_is_noop(self):
        notifier = TelegramNotifier(bot_token="t", chat_id="c", enabled=False)
        self.assertFalse(notifier.is_configured)
        with patch("app.services.telegram_notifier.requests.post") as post:
            self.assertFalse(notifier.notify("hei"))
            post.assert_not_called()

    def test_configured_sends_message(self):
        notifier = TelegramNotifier(bot_token="bot123", chat_id="42", enabled=True)
        response = MagicMock()
        response.status_code = 200
        with patch("app.services.telegram_notifier.requests.post", return_value=response) as post:
            self.assertTrue(notifier.notify("hei"))
            post.assert_called_once()
            _, kwargs = post.call_args
            self.assertEqual(kwargs["json"]["chat_id"], "42")
            self.assertEqual(kwargs["json"]["text"], "hei")

    def test_cooldown_dedupes_same_key(self):
        notifier = TelegramNotifier(
            bot_token="bot123", chat_id="42", enabled=True, cooldown_seconds=3600
        )
        response = MagicMock()
        response.status_code = 200
        with patch("app.services.telegram_notifier.requests.post", return_value=response) as post:
            self.assertTrue(notifier.notify("m1", dedupe_key="k"))
            self.assertFalse(notifier.notify("m2", dedupe_key="k"))
            self.assertEqual(post.call_count, 1)

    def test_http_error_returns_false(self):
        notifier = TelegramNotifier(bot_token="bot123", chat_id="42", enabled=True)
        response = MagicMock()
        response.status_code = 403
        response.text = "forbidden"
        with patch("app.services.telegram_notifier.requests.post", return_value=response):
            self.assertFalse(notifier.notify("hei"))

    def test_exception_never_raises(self):
        notifier = TelegramNotifier(bot_token="bot123", chat_id="42", enabled=True)
        with patch("app.services.telegram_notifier.requests.post", side_effect=RuntimeError("network")):
            self.assertFalse(notifier.notify("hei"))

    def test_notify_reauth_required_uses_dedupe_key(self):
        notifier = TelegramNotifier(
            bot_token="bot123", chat_id="42", enabled=True, cooldown_seconds=3600
        )
        response = MagicMock()
        response.status_code = 200
        with patch("app.services.telegram_notifier.requests.post", return_value=response) as post:
            self.assertTrue(notifier.notify_reauth_required("MFA kreves"))
            # Andre kall undertrykkes av cooldown (samme dedupe-nøkkel)
            self.assertFalse(notifier.notify_reauth_required("MFA kreves igjen"))
            self.assertEqual(post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
