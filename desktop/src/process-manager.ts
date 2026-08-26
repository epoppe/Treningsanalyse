import { ChildProcess, spawn } from "child_process";
import path from "path";
import type { AppPaths } from "./paths";
import { buildBackendEnv, isDev } from "./paths";
import { findFreePort, waitForHttpOk } from "./ports";
import type log from "electron-log";

export type ManagedServices = {
  apiPort: number;
  frontendPort: number;
  frontendUrl: string;
  backend: ChildProcess | null;
  frontend: ChildProcess | null;
};

function treeKill(child: ChildProcess | null, logger: typeof log): void {
  if (!child || child.killed || child.pid == null) return;
  const pid = child.pid;
  try {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      process.kill(-pid, "SIGTERM");
      setTimeout(() => {
        try {
          process.kill(-pid, "SIGKILL");
        } catch {
          /* ignore */
        }
      }, 2000);
    }
  } catch (err) {
    logger.warn("treeKill failed for pid %s: %s", pid, err);
    try {
      child.kill("SIGKILL");
    } catch {
      /* ignore */
    }
  }
}

export class ProcessManager {
  private services: ManagedServices = {
    apiPort: 0,
    frontendPort: 0,
    frontendUrl: "",
    backend: null,
    frontend: null,
  };

  constructor(
    private readonly paths: AppPaths,
    private readonly logger: typeof log,
  ) {}

  getServices(): ManagedServices {
    return this.services;
  }

  async start(): Promise<ManagedServices> {
    const apiPort = await findFreePort();
    const frontendPort = await findFreePort();
    this.services.apiPort = apiPort;
    this.services.frontendPort = frontendPort;
    this.services.frontendUrl = `http://127.0.0.1:${frontendPort}`;

    this.logger.info("Selected ports api=%s frontend=%s", apiPort, frontendPort);
    this.logger.info("Data dir=%s db=%s", this.paths.dataDir, this.paths.databaseFile);

    await this.startBackend(apiPort);
    await waitForHttpOk(`http://127.0.0.1:${apiPort}/health/live`, { timeoutMs: 120_000 });
    this.logger.info("Backend healthy on %s", apiPort);

    await this.startFrontend(apiPort, frontendPort);
    await waitForHttpOk(this.services.frontendUrl, { timeoutMs: 120_000 });
    this.logger.info("Frontend healthy on %s", frontendPort);

    return this.services;
  }

  private async startBackend(apiPort: number): Promise<void> {
    const env = buildBackendEnv(this.paths, apiPort);
    // CORS must allow the frontend origin (different port)
    env.CORS_ORIGINS = `http://127.0.0.1:${apiPort},http://localhost:${apiPort}`;

    let child: ChildProcess;
    if (isDev()) {
      const python = process.platform === "win32"
        ? path.join(this.paths.backendExe, ".venv", "Scripts", "python.exe")
        : path.join(this.paths.backendExe, ".venv", "bin", "python");
      child = spawn(
        python,
        ["-m", "app.desktop_backend", "--host", "127.0.0.1", "--port", String(apiPort)],
        {
          cwd: this.paths.backendExe,
          env,
          stdio: ["ignore", "pipe", "pipe"],
          windowsHide: true,
          detached: process.platform !== "win32",
        },
      );
    } else {
      child = spawn(this.paths.backendExe, ["--host", "127.0.0.1", "--port", String(apiPort)], {
        env,
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      });
    }

    this.attachLogs(child, "backend");
    this.services.backend = child;
    child.on("exit", (code, signal) => {
      this.logger.warn("Backend exited code=%s signal=%s", code, signal);
    });
  }

  private async startFrontend(apiPort: number, frontendPort: number): Promise<void> {
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      PORT: String(frontendPort),
      HOSTNAME: "127.0.0.1",
      NEXT_PUBLIC_API_URL: `http://127.0.0.1:${apiPort}`,
      API_INTERNAL_URL: `http://127.0.0.1:${apiPort}`,
      DESKTOP_RUNTIME_PROXY: "1",
    };

    // Update CORS on backend for actual frontend port — backend already started;
    // relative /api rewrites need Next to proxy to apiPort via NEXT_PUBLIC_API_URL.
    let child: ChildProcess;
    if (isDev()) {
      const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
      child = spawn(npmCmd, ["run", "start", "--", "-p", String(frontendPort), "-H", "127.0.0.1"], {
        cwd: this.paths.frontendDir,
        env,
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
        shell: process.platform === "win32",
        detached: process.platform !== "win32",
      });
    } else {
      const nodeBin = process.execPath; // Electron's node is not ideal; use bundled node if present
      const bundledNode = path.join(this.paths.frontendDir, "node.exe");
      const exe = process.platform === "win32" && require("fs").existsSync(bundledNode)
        ? bundledNode
        : "node";
      child = spawn(exe, [this.paths.frontendServer], {
        cwd: this.paths.frontendDir,
        env,
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      });
    }

    this.attachLogs(child, "frontend");
    this.services.frontend = child;
    child.on("exit", (code, signal) => {
      this.logger.warn("Frontend exited code=%s signal=%s", code, signal);
    });
  }

  private attachLogs(child: ChildProcess, label: string): void {
    child.stdout?.on("data", (buf: Buffer) => {
      this.logger.info("[%s] %s", label, buf.toString().trimEnd());
    });
    child.stderr?.on("data", (buf: Buffer) => {
      this.logger.warn("[%s] %s", label, buf.toString().trimEnd());
    });
  }

  async stop(): Promise<void> {
    this.logger.info("Stopping child processes…");
    treeKill(this.services.frontend, this.logger);
    treeKill(this.services.backend, this.logger);
    this.services.frontend = null;
    this.services.backend = null;
  }
}
