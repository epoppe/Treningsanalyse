import log from "electron-log";
import path from "path";
import type { AppPaths } from "./paths";

export function configureLogging(paths: AppPaths): typeof log {
  log.transports.file.resolvePathFn = () => path.join(paths.logDir, "desktop.log");
  log.transports.file.level = "info";
  log.transports.console.level = "info";
  return log;
}
