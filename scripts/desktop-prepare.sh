#!/usr/bin/env bash
# Build desktop artifacts into dist/desktop/ (run from repo root).
# On Linux this prepares frontend + documents Windows PyInstaller/Electron steps.
# Full NSIS installer is produced on windows-latest via GitHub Actions.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/dist/desktop"
FRONTEND_OUT="$OUT/frontend"
BACKEND_OUT="$OUT/backend"

echo "== Desktop prepare =="
echo "Root: $ROOT"
rm -rf "$OUT"
mkdir -p "$FRONTEND_OUT" "$BACKEND_OUT"

echo "Building Next.js standalone…"
npm run build --prefix "$ROOT/frontend"

STANDALONE="$ROOT/frontend/.next/standalone"
if [[ ! -d "$STANDALONE" ]]; then
  echo "ERROR: frontend/.next/standalone mangler etter build"
  exit 1
fi

# Copy standalone server + static + public
cp -a "$STANDALONE"/. "$FRONTEND_OUT/"
mkdir -p "$FRONTEND_OUT/.next"
cp -a "$ROOT/frontend/.next/static" "$FRONTEND_OUT/.next/static"
if [[ -d "$ROOT/frontend/public" ]]; then
  cp -a "$ROOT/frontend/public" "$FRONTEND_OUT/public"
fi

# Prefer server.js at frontend root (Next standalone layout nests by package name)
if [[ ! -f "$FRONTEND_OUT/server.js" ]]; then
  FOUND="$(find "$FRONTEND_OUT" -maxdepth 3 -name server.js | head -1 || true)"
  if [[ -n "$FOUND" ]]; then
    echo "Note: server.js at $FOUND"
  else
    echo "ERROR: fant ikke server.js i standalone output"
    exit 1
  fi
fi

echo "Frontend packaged → $FRONTEND_OUT"

if [[ "${SKIP_PYINSTALLER:-}" == "1" ]]; then
  echo "SKIP_PYINSTALLER=1 — hopper over PyInstaller (bruk Windows CI for .exe)"
  cat > "$BACKEND_OUT/README.txt" <<EOF
Backend executable is built on Windows with:
  cd backend
  .venv\\Scripts\\pip install pyinstaller
  .venv\\Scripts\\pyinstaller packaging/treningsanalyse-backend.spec --distpath ../dist/desktop/backend --workpath ../dist/desktop/pyi-work
EOF
else
  if command -v wine >/dev/null 2>&1 && [[ -f "$ROOT/backend/.venv/bin/pyinstaller" ]]; then
    echo "PyInstaller via wine not fully supported here — use Windows CI"
  fi
  if [[ "$(uname -s)" == "Linux" ]]; then
    echo "Building Linux sidecar for smoke (not the Windows .exe)…"
    "$ROOT/backend/.venv/bin/pip" install -q pyinstaller
    "$ROOT/backend/.venv/bin/pyinstaller" \
      "$ROOT/backend/packaging/treningsanalyse-backend.spec" \
      --distpath "$BACKEND_OUT" \
      --workpath "$OUT/pyi-work" \
      --noconfirm || {
        echo "WARN: PyInstaller Linux build failed — Windows CI builds the .exe"
        echo "Linux sidecar unavailable" > "$BACKEND_OUT/README.txt"
      }
  fi
fi

echo "Compile Electron TypeScript…"
if [[ ! -d "$ROOT/desktop/node_modules" ]]; then
  npm install --prefix "$ROOT/desktop"
fi
npm run build --prefix "$ROOT/desktop"

echo "Done. Artifacts under $OUT"
echo "Next (Windows): npm run desktop:dist"
