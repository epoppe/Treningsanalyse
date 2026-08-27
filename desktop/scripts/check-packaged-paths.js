/**
 * Unit tests for packaged resource path helpers (runs against compiled dist/).
 * Usage (from desktop/): npm run build && node scripts/check-packaged-paths.js
 */
const assert = require("assert");
const path = require("path");
const {
  PACKAGED_BACKEND_DIR,
  PACKAGED_BACKEND_EXE,
  packagedBackendExe,
  packagedBundledNode,
  packagedFrontendDir,
  packagedFrontendServer,
} = require("../dist/packaged-paths");

function testPackagedBackendLayout() {
  const resourcesRoot = path.join("C:", "App", "resources");
  const exe = packagedBackendExe(resourcesRoot);
  assert.strictEqual(
    exe,
    path.join(resourcesRoot, "backend", PACKAGED_BACKEND_DIR, PACKAGED_BACKEND_EXE),
  );
  // Must NOT be the flat (broken) path that caused ECONNREFUSED in production.
  assert.notStrictEqual(
    exe,
    path.join(resourcesRoot, "backend", PACKAGED_BACKEND_EXE),
  );
  assert.ok(
    exe.includes(path.join("backend", PACKAGED_BACKEND_DIR, PACKAGED_BACKEND_EXE)),
  );
}

function testFrontendLayout() {
  const resourcesRoot = "/opt/app/resources";
  const frontendDir = packagedFrontendDir(resourcesRoot);
  assert.strictEqual(frontendDir, path.join(resourcesRoot, "frontend"));
  assert.strictEqual(
    packagedFrontendServer(frontendDir),
    path.join(frontendDir, "server.js"),
  );
  assert.strictEqual(
    packagedBundledNode(frontendDir),
    path.join(frontendDir, "node.exe"),
  );
}

testPackagedBackendLayout();
testFrontendLayout();
console.log("check-packaged-paths.js: OK");
