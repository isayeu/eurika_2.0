# refactor_code_smell — план повышения verify_success_rate (ROADMAP 6.3)

**Цель:** рост success с 0% для `long_function|refactor_code_smell` и `deep_nesting|refactor_code_smell`.

---

## Текущее состояние

| Параметр | Значение |
|----------|----------|
| Пары в WEAK_SMELL_ACTION_PAIRS | `long_function|refactor_code_smell`, `deep_nesting|refactor_code_smell` |
| Эмиссия по умолчанию | `EURIKA_EMIT_CODE_SMELL_TODO=0` → refactor_code_smell **не эмитится** (skip) |
| При emit_todo=1 | diff = `# TODO (eurika): refactor ...` — только маркер, не реальный фикс |
| _is_strong_refactor_code_smell_success | False для diff с `# TODO (eurika): refactor ` → 0% strong success |
| Policy | auto: deny, hybrid: review |

**Корневая причина:** refactor_code_smell при отсутствии extract_block/extract_nested выдаёт только TODO. Реальный фикс (extract helper) не выполняется.

---

## Текущий flow (get_code_smell_operations)

1. long_function → suggest_extract_nested_function → extract_nested_function **или** suggest_extract_block → extract_block_to_helper **или** (если emit_todo) refactor_code_smell TODO
2. deep_nesting → suggest_extract_block → extract_block_to_helper **или** (если emit_todo) refactor_code_smell TODO

Когда heuristics (extract_block, extract_nested) не находят подходящий блок — fallback: TODO или skip.

---

## Варианты повышения

### A. LLM-powered extract (приоритет 1)

Когда suggest_extract_block/extract_nested возвращают None — вызвать LLM с контекстом (функция, smell, OSS snippets из pattern_library) и сгенерировать **реальный** diff (extract helper). Не TODO.

- **Зависимости:** `ask_llm_extract_method_hints` уже есть; нужен `ask_llm_extract_patch` — генерация полного patch
- **Риски:** LLM может сломать код; verify обязателен
- **Окружение:** `EURIKA_USE_LLM_EXTRACT=1` (новый флаг)

### B. Расширение heuristics (приоритет 2)

- Уменьшить `min_lines` для suggest_extract_block: long_function=3 ✅; deep_nesting=3 ✅ (было 5)
- Добавить поддержку block-типов: with, try/except — ✅ уже поддерживаются (ast.With, ast.Try)
- Улучшить detect extractable block — больше паттернов

- **Эффект:** больше случаев → extract_block_to_helper вместо refactor_code_smell
- **Риски:** низкие; heuristics уже протестированы

### C. Pattern library before/after (приоритет 3)

Из OSS git history извлечь реальные коммиты refactor (long_function → extract, deep_nesting → flatten). Использовать как few-shot для LLM или как шаблоны.

- **Сложность:** высокая — парсинг git log, сопоставление smell→fix
- **Долгосрочно**

### D. Polygon drill для refactor_code_smell

Добавить в `eurika/polygon/` файл с long_function без extractable nested/block — целевой кейс для LLM-powered extract. Whitelist для накопления learning.

- **Быстро:** даёт воспроизводимый сценарий для тестов

### E. Поэтапный выход из WEAK (✅ реализовано)

При достижении rate ≥ 25% (total ≥ 5) для `long_function|refactor_code_smell` — auto: **review** (вместо deny). При 50%+ — возможен allow для whitelisted targets.
- Мониторинг: `report-snapshot` и `learning-kpi` показывают `policy_adjustment (Phase E)` при rate≥25%, total≥5.

---

## Рекомендуемый план

| Фаза | Действие | Оценка |
|------|----------|--------|
| 1 | B: min_lines=3 для long_function (✅ сделано) | — |
| 2 | D: polygon drill refactor_code_smell (без extract) | ✅ refactor_code_smell_drill.py |
| 3 | A: EURIKA_USE_LLM_EXTRACT + ask_llm_extract_patch (✅ реализовано) | — |
| 4 | E: мониторинг learning-kpi, policy adjust при rate ≥ 25% | ✅ policy_adjustment_hints + policy: deny→review в auto при rate≥25%, total≥5. report-snapshot выводит policy_adjustment (Phase E) |
| 5 | C: OSS before/after (при наличии ресурсов) | ✅ git_refactors + pattern_library |

---

## Phase 3 — реализация (LLM-powered extract)

- `EURIKA_USE_LLM_EXTRACT=1` — включает попытку LLM-рефакторинга при long_function без extract_block/extract_nested
- `ask_llm_extract_patch(file_path, function_name, project_root)` — запрос к Ollama для генерации полного refactored файла
- Op `llm_extract_block` с `params.new_content` — patch_apply заменяет файл новым содержимым
- Budget/circuit-breaker как у ask_ollama_split_hints

## Quick start: refactor_code_smell с LLM

```bash
eurika learn-github . --light --limit-repos 3 --scan --build-patterns
EURIKA_USE_LLM_EXTRACT=1 eurika fix . --allow-low-risk-campaign
```

После build-patterns: `pattern_library.json` содержит long_function/deep_nesting snippets и **long_function_before_after** (Phase 5) из git refactor commits. LLM предпочитает before/after пары при наличии.

## Файлы для изменений

- `eurika/api/ops.py` — get_code_smell_operations, _use_llm_extract, опка llm_extract_block
- `eurika/reasoning/planner_llm.py` — ask_llm_extract_patch, _build_extract_patch_prompt
- `patch_apply_handlers.py` — обработчик kind=llm_extract_block
- `eurika/agent/policy.py` — WEAK_SMELL_ACTION_PAIRS (при выходе)
- `eurika/refactor/extract_function.py` — suggest_extract_block (min_lines, block types)
- `eurika/polygon/` — новый drill
