# Sikkerhet

Treningsanalyse er et personlig prosjekt. API-et eksponerer treningsdata og
skal ikke være offentlig uten ekstra autentisering.

## Credentials

| Hemmelighet | Hvor |
|-------------|------|
| Garmin e-post/passord | `GARMIN_EMAIL` / `GARMIN_PASSWORD` i `.env` |
| Garmin tokens | `TOKEN_DIR` (gitignore) |
| Redis-passord | `REDIS_PASSWORD` (valgfritt) |
| Frost / Telegram | `FROST_*` / `TELEGRAM_*` |

- `.env` er gitignore’t — aldri commit credentials
- Logger skriver kun maskert e-post (`settings.masked_garmin_email()`)

## CORS

Tillatte origins styres av `CORS_ORIGINS` (komma-separert).

```bash
CORS_ORIGINS=http://localhost:3000,https://din-frontend.example
```

Standard er localhost:3000–3002. Ikke bruk `*` med `allow_credentials=True`.

## HTTP-headers

`SecurityHeadersMiddleware` setter:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy` (kamera/mikrofon/geo av)
- `Content-Security-Policy` (streng for JSON-API)

## Dev vs prod

| Variabel | Dev | Prod |
|----------|-----|------|
| `SKIP_GARMIN_INIT` | `true` (rask boot) | `false` / unset |
| `CORS_ORIGINS` | localhost | eksplisitt frontend-URL |
| `REDIS_ENABLED` | valgfritt | anbefalt |

## Begrensninger

API-et har **ikke** egen brukerinnlogging. Beskytt med nettverksnivå
(VPN, reverse proxy auth, firewall) hvis eksponert utenfor localhost.
