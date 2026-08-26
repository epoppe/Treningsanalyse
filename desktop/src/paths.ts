import { app } from "electron";
import path from "path";
import fs from "fs";

export type AppPaths = {
  userData: string;
  dataDir: string;
  tokenDir: string;
  fitDir: string;
  cacheDir: string;
  logDir: string;
  backupDir: string;
  configDir: string;
  databaseFile: string;
  resourcesRoot: string;
  backendExe: string;
  frontendDir: string;
  frontendServer: string;
};

export function isDev(): boolean {
  return !app.isPackaged;
}

export function resolveAppPaths(): AppPaths {
  const userData = app.getPath("userData");
  const dataDir = path.join(userData, "data");
  const tokenDir = path.join(userData, "tokens");
  const fitDir = path.join(userData, "fit");
  const cacheDir = path.join(userData, "cache");
  const logDir = path.join(userData, "logs");
  const backupDir = path.join(userData, "backups");
  const configDir = path.join(userData, "config");
  const databaseFile = path.join(dataDir, "treningsanalyse.db");

  for (const dir of [dataDir, tokenDir, fitDir, cacheDir, logDir, backupDir, configDir]) {
    fs.mkdirSync(dir, { recursive: true });
  }

  const resourcesRoot = isDev()
    ? path.resolve(__dirname, "..", "..", "dist", "desktop")
    : process.resourcesPath;

  const backendExe = isDev()
    ? path.resolve(__dirname, "..", "..", "backend")
    : path.join(resourcesRoot, "backend", "treningsanalyse-backend.exe");

  const frontendDir = isDev()
    ? path.resolve(__dirname, "..", "..", "frontend")
    : path.join(resourcesRoot, "frontend");

  const frontendServer = isDev()
    ? path.join(frontendDir, "node_modules", "next", "dist", "bin", "next")
    : path.join(frontendDir, "server.js");

  return {
    userData,
    dataDir,
    tokenDir,
    fitDir,
    cacheDir,
    logDir,
    backupDir,
    configDir,
    databaseFile,
    resourcesRoot,
    backendExe,
    frontendDir,
    frontendServer,
  };
}

export function sqliteUrlForFile(dbPath: string): string {
  return "sqlite:///" + path.resolve(dbPath).replace(/\\/g, "/");
}

export function buildBackendEnv(paths: AppPaths, apiPort: number): NodeJS.ProcessEnv {
  return {
    ...process.env,
    TRAININGSANALYSE_DATA_DIR: paths.userData,
    DATABASE_URL: sqliteUrlForFile(paths.databaseFile),
    TOKEN_DIR: paths.tokenDir,
    DATA_DIR: paths.dataDir,
    FIT_DATA_DIR: paths.fitDir,
    CACHE_DIR: paths.cacheDir,
    LOG_DIR: paths.logDir,
    BACKUP_DIR: paths.backupDir,
    DESKTOP_MODE: "true",
    SKIP_GARMIN_INIT: "true",
    ENVIRONMENT: "desktop",
    BACKEND_HOST: "127.0.0.1",
    BACKEND_PORT: String(apiPort),
    CORS_ORIGINS: `http://127.0.0.1:${apiPort},http://localhost:${apiPort}`,
    PYTHONUNBUFFERED: "1",
  };
}
