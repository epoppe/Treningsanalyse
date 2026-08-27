import { ChildProcess, spawn } from "child_process";
import fs from "fs";
import path from "path";
import type { AppPaths } from "./paths";
import { assertPackagedResources, buildBackendEnv, isDev } from "./paths";
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

  /** Rejects when a child fails to spawn (ENOENT) or exits before healthy. */
  private earlyFailure: Promise<never> | null = null;
  private earlyFailureReject: ((err: Error) => void) | null = null;
  private healthy = false;

  constructor(
    private readonly paths: AppPaths,
    private readonly logger: typeof log,
  ) {}

  getServices(): ManagedServices {
    return this.services;
  }

  async start(): Promise<ManagedServices> {
    assertPackagedResources(this.paths);
    this.resetEarlyFailure();

    const apiPort = await findFreePort();
    const frontendPort = await findFreePort();
    this.services.apiPort = apiPort;
    this.services.frontendPort = frontendPort;
    this.services.frontendUrl = `http://127.0.0.1:${frontendPort}`;

    this.logger.info("Selected ports api=%s frontend=%s", apiPort, frontendPort);
    this.logger.info("Data dir=%s db=%s", this.paths.dataDir, this.paths.databaseFile);
    this.logger.info("Backend exe=%s", this.paths.backendExe);
    this.logger.info("Frontend server=%s", this.paths.frontendServer);

    await this.startBackend(apiPort);
    await Promise.race([
      waitForHttpOk(`http://127.0.0.1:${apiPort}/health/live`, { timeoutMs: 120_000 }),
      this.earlyFailure!,
    ]);
    this.logger.info("Backend healthy on %s", apiPort);

    this.resetEarlyFailure();
    await this.startFrontend(apiPort, frontendPort);
    await Promise.race([
      waitForHttpOk(this.services.frontendUrl, { timeoutMs: 120_000 }),
      this.earlyFailure!,
    ]);
    this.healthy = true;
    this.logger.info("Frontend healthy on %s", frontendPort);

    return this.services;
  }

  private resetEarlyFailure(): void {
    this.earlyFailure = new Promise<never>((_resolve, reject) => {
      this.earlyFailureReject = reject;
    });
    // Prevent unhandled rejection if we never race against it
    this.earlyFailure.catch(() => undefined);
  }

  private failEarly(err: Error): void {
    this.logger.error("%s", err.message);
    this.earlyFailureReject?.(err);
  }

  private async startBackend(apiPort: number): Promise<void> {
    const env = buildBackendEnv(this.paths, apiPort);
    env.CORS_ORIGINS = `http://127.0.0.1:${apiPort},http://localhost:${apiPort}`;

    let child: ChildProcess;
    let spawnTarget: string;
    if (isDev()) {
      spawnTarget =
        process.platform === "win32"
          ? path.join(this.paths.backendExe, ".venv", "Scripts", "python.exe")
          : path.join(this.paths.backendExe, ".venv", "bin", "python");
      if (!fs.existsSync(spawnTarget)) {
        throw new Error(
          `Backend executable not found / could not start:\n${spawnTarget}`,
        );
      }
      child = spawn(
        spawnTarget,
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
      spawnTarget = this.paths.backendExe;
      if (!fs.existsSync(spawnTarget)) {
        throw new Error(
          `Backend executable not found / could not start:\n${spawnTarget}`,
        );
      }
      child = spawn(spawnTarget, ["--host", "127.0.0.1", "--port", String(apiPort)], {
        cwd: path.dirname(spawnTarget),
        env,
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      });
    }

    this.attachChild(child, "Backend", spawnTarget);
    this.services.backend = child;
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

    let child: ChildProcess;
    let spawnTarget: string;
    if (isDev()) {
      spawnTarget = process.platform === "win32" ? "npm.cmd" : "npm";
      child = spawn(spawnTarget, ["run", "start", "--", "-p", String(frontendPort), "-H", "127.0.0.1"], {
        cwd: this.paths.frontendDir,
        env,
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
        shell: process.platform === "win32",
        detached: process.platform !== "win32",
      });
    } else {
      const hasBundledNode = Boolean(this.paths.bundledNode && fs.existsSync(this.paths.bundledNode));
      spawnTarget = hasBundledNode ? this.paths.bundledNode! : process.execPath;
      if (!hasBundledNode) {
        env.ELECTRON_RUN_AS_NODE = "1";
      }
      if (!fs.existsSync(this.paths.frontendServer)) {
        throw new Error(
          `Frontend server not found / could not start:\n${this.paths.frontendServer}`,
        );
      }
      child = spawn(spawnTarget, [this.paths.frontendServer], {
        cwd: this.paths.frontendDir,
        env,
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      });
    }

    this.attachChild(child, "Frontend", spawnTarget);
    this.services.frontend = child;
  }

  private attachChild(child: ChildProcess, label: string, exePath: string): void {
    this.attachLogs(child, label.toLowerCase());

    child.on("error", (err) => {
      this.failEarly(
        new Error(
          `${label} executable not found / could not start:\n${exePath}\n${err.message}`,
        ),
      );
    });

    child.on("exit", (code, signal) => {
      this.logger.warn("%s exited code=%s signal=%s", label, code, signal);
      if (!this.healthy) {
        this.failEarly(
          new Error(
            `${label} exited before becoming healthy (code=${code}, signal=${signal}):\n${exePath}`,
          ),
        );
      }
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
    this.healthy = true; // suppress early-failure noise during intentional stop
    treeKill(this.services.frontend, this.logger);
    treeKill(this.services.backend, this.logger);
    this.services.frontend = null;
    this.services.backend = null;
  }
}
