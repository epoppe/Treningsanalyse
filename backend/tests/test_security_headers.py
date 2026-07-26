"""Tester for sikkerhetsheaders, CORS-origins og maskert logging."""

from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.middleware.security_headers import SecurityHeadersMiddleware


class CorsOriginsTests(unittest.TestCase):
    def test_parse_origins(self):
        s = Settings(
            _env_file=None,
            CORS_ORIGINS="http://localhost:3000, https://app.example.com ,",
        )
        self.assertEqual(
            s.cors_origin_list(),
            ["http://localhost:3000", "https://app.example.com"],
        )


class MaskedEmailTests(unittest.TestCase):
    def test_masks_local_part(self):
        s = Settings(_env_file=None, GARMIN_EMAIL="runner@example.com")
        self.assertEqual(s.masked_garmin_email(), "ru***@example.com")

    def test_empty(self):
        s = Settings(_env_file=None, GARMIN_EMAIL="")
        self.assertEqual(s.masked_garmin_email(), "(ikke satt)")


class SecurityHeadersMiddlewareTests(unittest.TestCase):
    def test_headers_present(self):
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/ping")
        def ping():
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/ping")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("Referrer-Policy"), "no-referrer")
        self.assertIn("default-src 'none'", response.headers.get("Content-Security-Policy", ""))


if __name__ == "__main__":
    unittest.main()
