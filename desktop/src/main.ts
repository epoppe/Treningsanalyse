import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  shell,
} from "electron";
import path from "path";
import fs from "fs";
import { resolveAppPaths, sqliteUrlForFile } from "./paths";
import { configureLogging } from "./logger";
import { ProcessManager } from "./process-manager";

let mainWindow: BrowserWindow | null = null;
let splashWindow: BrowserWindow | null = null;
let processManager: ProcessManager | null = null;
let quitting = false;

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

function createSplash(): BrowserWindow {
  const win = new BrowserWindow({
    width: 420,
    height: 220,
    frame: false,
    resizable: false,
    show: true,
    backgroundColor: "#0f172a",
  });
  win.loadURL(
    `data:text/html;charset=utf-8,${encodeURIComponent(`<!doctype html>
<html><body style="margin:0;font-family:Segoe UI,sans-serif;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;height:100vh;">
<div style="text-align:center"><h1 style="margin:0 0 8px;font-size:20px;">Treningsanalyse</h1>
<p style="margin:0;opacity:.8;font-size:13px;">Starter backend og frontend…</p></div>
</body></html>`)}`,
  );
  return win;
}

function createMainWindow(frontendUrl: string): BrowserWindow {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    backgroundColor: "#f8fafc",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  win.webContents.on("will-navigate", (event, url) => {
    const allowed = url.startsWith(frontendUrl) || url.startsWith("http://127.0.0.1");
    if (!allowed) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  win.once("ready-to-show", () => win.show());
  win.loadURL(frontendUrl);
  return win;
}

function buildMenu(paths: ReturnType<typeof resolveAppPaths>): void {
  const template: Electron.MenuItemConstructorOptions[] = [
    {
      label: "Fil",
      submenu: [
        {
          label: "Importer eksisterende database…",
          click: async () => {
            const result = await dialog.showOpenDialog({
              title: "Velg treningsanalyse.db",
              filters: [{ name: "SQLite", extensions: ["db"] }],
              properties: ["openFile"],
            });
            if (result.canceled || !result.filePaths[0]) return;
            try {
              await importDatabaseFile(result.filePaths[0], paths);
              dialog.showMessageBox({
                type: "info",
                message: "Database importert",
                detail: "Start appen på nytt for å bruke den importerte databasen.",
              });
            } catch (err) {
              dialog.showErrorBox("Import feilet", String(err));
            }
          },
        },
        { type: "separator" },
        { role: "quit", label: "Avslutt" },
      ],
    },
    {
      label: "Hjelp",
      submenu: [
        {
          label: "Åpne loggmappe",
          click: () => shell.openPath(paths.logDir),
        },
        {
          label: "Åpne datamappe",
          click: () => shell.openPath(paths.userData),
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

async function importDatabaseFile(
  source: string,
  paths: ReturnType<typeof resolveAppPaths>,
): Promise<void> {
  // Prefer calling packaged backend import if available; otherwise copy + note Alembic on next start.
  const target = paths.databaseFile;
  if (fs.existsSync(target) && fs.statSync(target).size > 0) {
    const confirm = await dialog.showMessageBox({
      type: "warning",
      buttons: ["Avbryt", "Overskriv"],
      defaultId: 0,
      cancelId: 0,
      message: "Eksisterende database vil bli overskrevet (backup tas først).",
    });
    if (confirm.response !== 1) throw new Error("Import avbrutt");
  }
  // Use Python import script in dev; in production copy then rely on Alembic at next backend start.
  const { spawnSync } = await import("child_process");
  if (!app.isPackaged) {
    const python =
      process.platform === "win32"
        ? path.join(paths.backendExe, ".venv", "Scripts", "python.exe")
        : path.join(paths.backendExe, ".venv", "bin", "python");
    const result = spawnSync(
      python,
      [path.join(paths.backendExe, "scripts", "import_database.py"), source, "--overwrite"],
      {
        env: {
          ...process.env,
          TRAININGSANALYSE_DATA_DIR: paths.userData,
          DATABASE_URL: sqliteUrlForFile(paths.databaseFile),
        },
        encoding: "utf-8",
      },
    );
    if (result.status !== 0) {
      throw new Error(result.stdout || result.stderr || "import failed");
    }
    return;
  }
  // Packaged: safe copy; backend will migrate on next launch
  fs.mkdirSync(path.dirname(target), { recursive: true });
  if (fs.existsSync(target)) {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    fs.copyFileSync(target, path.join(paths.backupDir, `pre-import-${stamp}.db`));
  }
  fs.copyFileSync(source, target);
}

function showStartupError(component: string, err: unknown, logDir: string): void {
  dialog.showErrorBox(
    `Oppstart feilet (${component})`,
    `${String(err)}\n\nLoggmappe:\n${logDir}`,
  );
}

app.whenReady().then(async () => {
  const paths = resolveAppPaths();
  const logger = configureLogging(paths);
  logger.info("Treningsanalyse desktop starting version=%s", app.getVersion());
  logger.info("userData=%s", paths.userData);

  buildMenu(paths);
  splashWindow = createSplash();

  ipcMain.handle("desktop:get-paths", () => paths);
  ipcMain.handle("desktop:open-log-folder", () => shell.openPath(paths.logDir));
  ipcMain.handle("desktop:get-version", () => app.getVersion());
  ipcMain.handle("desktop:import-database", async (_e, filePath: string) => {
    await importDatabaseFile(filePath, paths);
    return { ok: true };
  });

  processManager = new ProcessManager(paths, logger);
  try {
    const services = await processManager.start();
    splashWindow?.close();
    splashWindow = null;
    mainWindow = createMainWindow(services.frontendUrl);
  } catch (err) {
    logger.error("Startup failed: %s", err);
    splashWindow?.close();
    showStartupError("Backend/Frontend", err, paths.logDir);
    await processManager.stop();
    app.quit();
  }
});

app.on("before-quit", async (event) => {
  if (quitting) return;
  quitting = true;
  event.preventDefault();
  try {
    await processManager?.stop();
  } finally {
    app.exit(0);
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
