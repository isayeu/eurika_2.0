#!/bin/bash
# Verify gate for fix cycle: ruff + mypy + pytest subset
# Close loop with release_check — Eurika learns from ruff/mypy/pytest failures
# Run from project root (invoked by patch_engine verify_patch)
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${ROOT}/.venv"
cd "$ROOT"
PY="${VENV}/bin/python"
RUFF="${VENV}/bin/ruff"
[[ -x "$PY" ]] || PY=python
[[ -x "$RUFF" ]] || RUFF=ruff
$RUFF check eurika cli
$PY -m mypy eurika cli
$PY -m pytest tests/test_clean_imports_cli.py tests/test_remove_unused_import.py tests/test_extract_function.py -q
