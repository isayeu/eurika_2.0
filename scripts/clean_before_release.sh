#!/bin/bash
# RV4 Release hygiene — очистка дерева от runtime-артефактов перед сборкой sdist
# docs/RELEASE_CHECKLIST.md, optional before python -m build --sdist

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Clean before release (root=$ROOT)"

_rm_safe() {
  if [[ -e "$1" ]]; then
    rm -rf "$1"
    echo "  removed: $1"
  fi
}

# Runtime artifacts
find "$ROOT" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$ROOT" -type f -name "*.pyc" -delete 2>/dev/null || true
_rm_safe "$ROOT/.pytest_cache"

echo "  OK: cleaned __pycache__, *.pyc, .pytest_cache"
echo "  (build/ dist/ — оставлены; при необходимости: rm -rf build dist)"
