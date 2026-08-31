import fs from "fs";
import path from "path";

const DESKTOP_ENV_TEMPLATE = `# Treningsanalyse — Garmin Connect (desktop)
# Fyll inn dine Garmin-innloggingsdetaljer for synkronisering.
# Tokens lagres automatisk i tokens/ etter første vellykkede innlogging.

GARMIN_EMAIL=
GARMIN_PASSWORD=

# Valgfritt: kinesiske Garmin-kontoer
# GARMIN_IS_CN=false

# Logging (INFO, DEBUG, …)
# LOG_LEVEL=INFO
`;

/** Oppretter config/.env under AppData første gang (skriver aldri over eksisterende). */
export function ensureDesktopConfigEnv(configDir: string): string {
  const envPath = path.join(configDir, ".env");
  fs.mkdirSync(configDir, { recursive: true });
  if (!fs.existsSync(envPath)) {
    fs.writeFileSync(envPath, DESKTOP_ENV_TEMPLATE, { encoding: "utf-8", mode: 0o600 });
  }
  return envPath;
}
