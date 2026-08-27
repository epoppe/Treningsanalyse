import path from "path";

/** PyInstaller COLLECT folder name (must stay next to runtime DLLs/_internal). */
export const PACKAGED_BACKEND_DIR = "treningsanalyse-backend";
export const PACKAGED_BACKEND_EXE = "treningsanalyse-backend.exe";

/**
 * Resolve the packaged backend executable under Electron resources.
 *
 * Layout after electron-builder extraResources + PyInstaller COLLECT:
 *   resources/backend/treningsanalyse-backend/treningsanalyse-backend.exe
 */
export function packagedBackendExe(resourcesRoot: string): string {
  return path.join(
    resourcesRoot,
    "backend",
    PACKAGED_BACKEND_DIR,
    PACKAGED_BACKEND_EXE,
  );
}

export function packagedFrontendDir(resourcesRoot: string): string {
  return path.join(resourcesRoot, "frontend");
}

export function packagedFrontendServer(frontendDir: string): string {
  return path.join(frontendDir, "server.js");
}

export function packagedBundledNode(frontendDir: string): string {
  return path.join(frontendDir, "node.exe");
}
