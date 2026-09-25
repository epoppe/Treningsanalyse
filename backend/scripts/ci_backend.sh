#!/usr/bin/env bash
# Authoritative backend CI. GitHub Actions and `npm run ci:backend` both call this.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  export PATH="$ROOT/.venv/bin:${PATH}"
fi

export PYTHONPATH=.
export SKIP_GARMIN_INIT="${SKIP_GARMIN_INIT:-true}"

section() {
  echo ""
  echo "=== $1 ==="
}

run_pytest() {
  section "pytest tests"
  # The merge gate is the full tests/ tree, not a copied file list.
  python -m pytest tests -q --tb=short
}

if [[ "${1:-}" == "--pytest-only" ]]; then
  run_pytest
  exit 0
fi

section "ruff"
ruff check app/

section "mypy"
mypy

section "alembic"
python -c "from app.database.migrations import assert_single_alembic_head; print(assert_single_alembic_head())"
rm -f /tmp/ci-migrate.db
DATABASE_URL="sqlite:////tmp/ci-migrate.db" alembic upgrade head
DATABASE_URL="sqlite:////tmp/ci-migrate.db" alembic current

run_pytest

section "api smoke"
bash scripts/ci_smoke_api.sh

section "import smoke"
python -c "from app.main import app; assert app.title"
