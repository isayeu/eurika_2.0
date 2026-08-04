# Troubleshooting (B.11)

Типовые ошибки при работе с Eurika и способы решения.

---

## 1. Verify timeout

**Симптом:** `eurika fix .` или `eurika agent patch-apply --apply --verify` зависает; после завершения — `"error": "timeout"` в отчёте verify.

**Причины:**

- Pytest выполняется долго (много тестов, медленная сборка).
- Таймаут по умолчанию (300 с) недостаточен.

**Решения:**

1. Увеличить таймаут:

   ```bash
   EURIKA_VERIFY_TIMEOUT=600 eurika fix .
   ```

   Или через CLI (если поддерживается): `--verify-timeout 600`.

2. Задать кастомную команду верификации (меньше тестов):

   ```bash
   # pyproject.toml: [tool.eurika] verify_cmd = "pytest tests/test_smoke.py -q"
   # или через API/CLI
   ```

3. Временно отключить verify: `eurika fix . --dry-run` — только план, без apply/verify.

**Ссылки:** `patch_engine_apply_and_verify.py` (verify_timeout=300), `eurika/api/task_executor_executors.py`. Polygon drills: [POLYGON_VERIFY_PLAYBOOK.md](POLYGON_VERIFY_PLAYBOOK.md) (секция Verify timeout).

---

## 2. ModuleNotFoundError / ImportError при verify

**Симптом:** после `fix` verify падает с `ModuleNotFoundError: No module named 'X'` или `ImportError: cannot import name 'Y' from 'X'`.

**Причины:**

- Патч изменил импорты; тесты импортируют модули, которые переименованы или перенесены.
- Отсутствует `__init__.py` или пакет не установлен в editable mode.

**Решения:**

1. Eurika автоматически пытается исправить импорты (`retry_on_import_error=True`): парсит вывод pytest, предлагает fix (stub или redirect), повторяет verify. Если это сработало — в отчёте будет `fix_import_retry`.

2. Если автоматический fix не помог — исправьте импорты вручную по сообщению об ошибке, затем повторите verify или сделайте rollback:

   ```bash
   eurika agent patch-rollback . --run-id <last_run_id>
   ```

3. Убедитесь, что проект установлен: `pip install -e .` или `pip install -e ".[test]"`.

**Ссылки:** `eurika/refactor/fix_import_from_verify.py`, `patch_engine_apply_and_verify_helpers.py` (maybe_retry_import_fix).

---

## 3. LLM fallback (шаблонный вывод вместо LLM)

**Симптом:** `eurika doctor .` или `eurika architect .` выводят короткую шаблонную фразу вместо развёрнутого анализа от LLM.

**Причины:**

- Не задан `OPENAI_API_KEY` (OpenAI/OpenRouter).
- Ollama не запущен или недоступен (локальный fallback).
- Сеть недоступна или API возвращает ошибку.

**Решения:**

1. **OpenAI/OpenRouter:**
   ```bash
   export OPENAI_API_KEY="sk-..."
   export OPENAI_BASE_URL="https://openrouter.ai/api/v1"  # если OpenRouter
   export OPENAI_MODEL="gpt-4o-mini"  # или mistralai/...
   pip install openai
   ```

2. **Ollama (локальный):**
   - Запустите Ollama: `ollama serve` (или через Qt Models → Start Ollama).
   - Для **NVIDIA**: в Models включите «Use NVIDIA CUDA», `CUDA_VISIBLE_DEVICES=0` (см. `nvidia-smi`).
   - Для **AMD GPU**: «Use Vulkan (AMD GPU)» + при необходимости HSA/ROCR/HIP.
   - Fallback модель: `OLLAMA_OPENAI_MODEL=llama3.2:3b` (или установленная у вас).

3. **Без LLM (быстрый шаблон):**
   ```bash
   eurika doctor . --no-llm
   eurika cycle . --no-llm
   ```

**Ссылки:** `eurika/reasoning/architect.py`, README § Architect (LLM), docs/ONBOARDING.md.

---

## 4. self_map.json missing / self_map not found

**Симптом:** `"self_map.json not found"`, `"self_map.json not found. Run scan first"`, `"module 'X' not in graph (run 'eurika scan .' to refresh self_map.json)"`.

**Причины:**

- Команды doctor, fix, architect, explain требуют `self_map.json` в корне проекта.
- `self_map.json` создаётся только при `eurika scan .`.

**Решения:**

1. Выполните скан перед doctor/fix:
   ```bash
   eurika scan .
   eurika doctor .
   eurika fix . --dry-run
   ```

2. При `update_artifacts=False` pipeline читает только существующие артефакты (без перезаписи).

3. В Qt: выберите project root с `pyproject.toml` или уже имеющимся `self_map.json`; при пустом проекте — сначала Commands → scan → Run.

**Ссылки:** `core/pipeline.py`, `eurika/api/architecture.py`, `eurika/api/explain_api.py`, docs/ONBOARDING.md § 3.

---

## 5. Qt: «Project root has no pyproject.toml or self_map.json»

**Симптом:** При выборе папки в Qt — предупреждение или отказ запускать команды.

**Решение:** Выберите корень Python-проекта (с `pyproject.toml`) или папку, где уже был выполнен `eurika scan .` (есть `self_map.json`). Для нового проекта — сначала `eurika scan .` из CLI или после добавления pyproject.

---

## 6. Ollama: GPU не виден

Мин./оптимум VRAM и будущий PyTorch: [HARDWARE.md](HARDWARE.md).

### NVIDIA (CUDA)

**Симптом:** Ollama на CPU, в `nvidia-smi` нет процесса `ollama` во время генерации.

**Решение:**

1. Qt Models → включить **Use NVIDIA CUDA**, `CUDA_VISIBLE_DEVICES=0`.
2. Stop → Start Ollama (перезапуск обязателен).
3. Во время Chat/doctor смотреть `nvidia-smi` — Memory-Usage у ollama должна расти.
4. CLI:
   ```bash
   CUDA_VISIBLE_DEVICES=0 OLLAMA_VULKAN=0 ollama serve
   ```

На картах с малой VRAM (≤4 GB) берите лёгкие модели (`llama3.2:3b`), не 7B+.

### AMD RX 6xxx/7xxx (Vulkan)

**Симптом:** Ollama запускается, но `total_vram="0 B"`; модели работают на CPU.

**Решение:** Включите Vulkan backend:

```bash
OLLAMA_VULKAN=1 HSA_OVERRIDE_GFX_VERSION=10.3.0 ollama serve
```

В Qt Models tab: чекбокс «Use Vulkan (AMD GPU)»; при необходимости задайте HSA_OVERRIDE_GFX_VERSION, ROCR_VISIBLE_DEVICES, HIP_VISIBLE_DEVICES.

**Ссылки:** README § Ollama, Qt Models tab.

---

## 7. release_check / pytest падает после изменений

**Симптом:** `./scripts/release_check.sh` или `pytest tests/` падает с ruff/mypy/pytest ошибками.

**Решение:** См. `.cursor/rules/change-verify-pattern.mdc` — после правок в модуле `eurika/X/` запускайте `pytest tests/ -q -k "X"`. При F401/F811 (ruff) — удалить неиспользуемый импорт или переименовать; при mypy Incompatible return type — поправить аннотацию или return.

**Qt:** Release check (Quality tab) передаёт `OLLAMA_OPENAI_MODEL` из Models tab в smoke step (fix --dry-run). Выберите модель до Run.

---

## Быстрые ссылки

| Проблема          | Документ / раздел        |
| ----------------- | ------------------------ |
| Onboarding        | [docs/ONBOARDING.md](ONBOARDING.md) |
| Железо / PyTorch  | [docs/HARDWARE.md](HARDWARE.md) |
| CLI команды       | [docs/CLI.md](CLI.md)    |
| Patch Engine      | [docs/Architecture.md](Architecture.md) § 0 |
| Dogfooding ритуал (B.13) | [docs/DOGFOODING.md](DOGFOODING.md) — fix --dry-run после изменений, CYCLE_REPORT |
| Qt first-run      | ROADMAP B.12 ✅ (folder picker + подсказка при пустом root) |
