#!/bin/bash
# R4 Release Hygiene — pre-release gate (docs/RELEASE_CHECKLIST.md)
# Run from project root; uses .venv per .eurika/rules/venv.mdc

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${ROOT}/.venv"

# Use venv if exists (local dev); else use PATH (CI)
if [[ -x "${VENV}/bin/python" ]]; then
  PY="${VENV}/bin/python"
  PIP="${VENV}/bin/pip"
  PYTEST="${VENV}/bin/pytest"
  RUFF="${VENV}/bin/ruff"
else
  PY=python
  PIP=pip
  PYTEST=pytest
  RUFF=ruff
fi

cd "$ROOT"
echo "==> Release check (root=$ROOT)"

_step() { echo ""; echo "==> $1"; }
_fail() { echo "FAIL: $1" >&2; exit 1; }

_step "0. .eurika_backups in tree (P0.1 — warning only)"
if [[ -d "${ROOT}/.eurika_backups" ]] && [[ -n "$(ls -A "${ROOT}/.eurika_backups" 2>/dev/null)" ]]; then
  N_RUNS=$(find "${ROOT}/.eurika_backups" -maxdepth 1 -type d ! -path "${ROOT}/.eurika_backups" 2>/dev/null | wc -l)
  N_FILES=$(find "${ROOT}/.eurika_backups" -maxdepth 1 -type f 2>/dev/null | wc -l)
  TOTAL=$((N_RUNS + N_FILES))
  echo "  WARN: .eurika_backups has content ($N_RUNS backup runs, $N_FILES files)"
  echo "        Consider cleaning before release: rm -rf .eurika_backups"
  if [[ "$TOTAL" -ge 5 ]]; then
    echo "        (quite a lot — worth cleaning)"
  fi
fi

_step "1. Tests"
$PYTEST tests/ -q --tb=short || _fail "pytest tests/"

_step "2. Edge-case tests"
$PYTEST -m edge_case -v || _fail "pytest -m edge_case"

_step "3. Dependency firewall (strict)"
EURIKA_STRICT_LAYER_FIREWALL=1 $PYTEST tests/test_dependency_guard.py tests/test_dependency_firewall.py -v || _fail "dependency firewall"

_step "4. Lint (ruff)"
if command -v $RUFF &>/dev/null; then
  if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    $RUFF check eurika cli || echo "  (ruff: fix before release)"
  else
    $RUFF check eurika cli || _fail "ruff check"
  fi
else
  echo "  (ruff not installed, skip)"
fi

_step "5. Type check (mypy)"
if $PY -c "import mypy" 2>/dev/null; then
  if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    $PY -m mypy eurika cli || echo "  (mypy: fix before release)"
  else
    $PY -m mypy eurika cli || _fail "mypy"
  fi
else
  echo "  (mypy not installed, skip)"
fi

_step "6–7. Self-check (file size + layer discipline)"
$PY -m eurika_cli self-check . || _fail "eurika self-check"

_step "8. TODO/FIXME audit (informational)"
if command -v rg &>/dev/null; then
  rg "TODO|FIXME|XXX" --type py -g '!*test*' 2>/dev/null || true
else
  echo "  (rg not installed, skip)"
fi

_step "9. Smoke (install + scan + doctor --no-llm)"
$PIP install -e . -q
$PY -m eurika_cli scan . -q || echo "  (scan warning, continue)"
$PY -m eurika_cli doctor . --no-llm || echo "  (doctor warning, continue)"

echo ""
echo "==> Release check PASSED"
echo "    10. Verify CHANGELOG.md updated before tagging."
