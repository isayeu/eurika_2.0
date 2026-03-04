#!/bin/bash
# Примеры GET /api/* — knowledge, metrics (ROADMAP §5.7).
# Перед запуском: eurika serve . (порт 8765)

BASE="${BASE_URL:-http://127.0.0.1:8765}"

echo "=== GET /api/metrics (MetricVector + Energy) ==="
curl -s "${BASE}/api/metrics" | head -20

echo -e "\n\n=== GET /api/knowledge?topic=python ==="
curl -s "${BASE}/api/knowledge?topic=python" | head -30
