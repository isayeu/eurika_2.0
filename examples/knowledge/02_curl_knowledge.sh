#!/bin/bash
# Примеры запросов к GET /api/knowledge.
# Перед запуском: eurika serve . (порт 8765 по умолчанию)

BASE="${BASE_URL:-http://127.0.0.1:8765}"
# project_root = корень serve; переопределить: ?project_root=/path

echo "=== GET /api/knowledge?topic=python ==="
curl -s "${BASE}/api/knowledge?topic=python" | head -60

echo -e "\n\n=== GET /api/knowledge?topic=cyclic_imports ==="
curl -s "${BASE}/api/knowledge?topic=cyclic_imports" | head -60

echo -e "\n\n=== GET /api/knowledge?topic=typing&online=0 ==="
curl -s "${BASE}/api/knowledge?topic=typing&online=0" | head -60
