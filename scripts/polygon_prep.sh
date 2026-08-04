#!/bin/bash
# Подготовка полигона для verify cycles (POLYGON_VERIFY_PLAYBOOK)
# Запускать из корня проекта

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${ROOT}/.venv"
cd "$ROOT"

PY="${VENV}/bin/python"
PYTEST="${VENV}/bin/pytest"

echo "==> Polygon prep (root=$ROOT)"

echo ""
echo "1. Scan (refresh self_map.json)"
"${PY}" -m eurika_cli scan . 2>/dev/null || true

echo ""
echo "2. Polygon semantics (pytest)"
$PYTEST tests/test_clean_imports_cli.py -k polygon -q --tb=short || exit 1

echo ""
echo "3. Быстрая проверка цикла (без LLM):"
echo "   eurika prove-cycle ."
echo ""
echo "4. Готово. Дальше (POLYGON_VERIFY_PLAYBOOK):"
echo "   eurika fix . --runtime-mode hybrid --allow-low-risk-campaign"
echo "   # или Qt: Commands → Fix, hybrid + Allow low-risk → одобрить polygon ops → Apply approved"
echo ""
echo "   eurika learning-kpi . --polygon   # KPI по drills"
echo ""
