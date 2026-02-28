# R2 Fallback Audit — Fallback-устойчивость

Аудит fallback-путей и гарантий детерминированного завершения цикла при недоступности внешних зависимостей.

## 1. LLM (Architect)

**Цепочка fallback:**

| Порядок | Источник | Условие |
|--------|----------|---------|
| 1 | litellm | `_should_use_litellm_first()` (OpenAI/OpenRouter) |
| 2 | primary OpenAI client | при наличии API key |
| 3 | ollama HTTP | `/v1/chat/completions` |
| 4 | ollama CLI | `ollama run` subprocess |
| 5 | **template** | всегда доступен |

**Локальный Ollama (без API key):**

| Порядок | Источник |
|--------|----------|
| 1 | ollama CLI |
| 2 | ollama HTTP |
| 3 | **template** |

**degraded_mode:** устанавливается при `use_llm=True` и сбое LLM; `degraded_reasons`: `llm_unavailable:<reason>` или `llm_disabled`.

**Файлы:** `eurika/reasoning/architect.py` — `_llm_interpret`, `interpret_architecture_with_meta`.

---

## 2. Knowledge Layer

**CompositeKnowledgeProvider:** запрашивает провайдеры по очереди. При сбое одного (исключение) — пропускает, продолжает с остальными (R2).

**Провайдеры:**

- **LocalKnowledgeProvider** — JSON-кэш; отсутствие файла/ошибка парсинга → пустой ответ.
- **OSSPatternProvider** — `pattern_library.json`; `_load()` ловит `Exception` → `{}`.
- **PEPProvider** — `_fetch_url` ловит URLError/OSError/ValueError → `None` → пустой `StructuredKnowledge`.
- **OfficialDocsProvider** / **ReleaseNotesProvider** — аналогично.

**Architect:** при сбое `_resolve_knowledge_snippet` (исключение) → `knowledge_snippet = ''` (R2).

**degraded_mode** для knowledge не заводится — knowledge считается best-effort, цикл завершается с пустым Reference.

**Файлы:** `eurika/knowledge/base.py`, `eurika/reasoning/architect.py`.

---

## 3. Runtime (summary, scan)

**get_summary:** при отсутствии `self_map.json` → `{"error": "...", "path": "..."}`. Doctor возвращает этот объект с `runtime.degraded_mode=True`, `degraded_reasons=["summary_unavailable"]`.

**run_scan:** возвращает exit code. Full cycle при `!= 0` → early return с error и `report.runtime.degraded_reasons=["scan_failed"]`.

**full_cycle doctor error:** при `data.get("error")` — если `report` без `runtime`, добавляется `degraded_reasons=["doctor_error"]`.

**Файлы:** `eurika/api/__init__.py`, `cli/orchestration/doctor.py`, `cli/orchestration/full_cycle.py`.

---

## 4. Cycle State (R2)

Все точки выхода doctor/fix добавляют `state` и `state_history` через `with_cycle_state`. `state` ∈ {done, error}, `state_history` ∈ {[thinking, done], [thinking, error]}.

---

## Критерий готовности R2

> При недоступности внешних зависимостей цикл завершается предсказуемо.

- [x] LLM → template
- [x] Knowledge fetch → пустой snippet
- [x] self_map missing → error dict
- [x] CompositeKnowledgeProvider: сбой одного провайдера не роняет остальных
- [x] Architect: сбой knowledge resolution → empty snippet
- [x] Тесты: `test_composite_knowledge_provider_skips_failing_provider`, `test_interpret_architecture_with_meta_knowledge_throws_uses_empty_snippet`, `test_doctor_llm_unavailable_falls_back_to_template`, `test_doctor_handles_network_unavailable_without_crash`
