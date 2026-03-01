# Отчёт цикла Eurika

## Current state (2026-03-01)

- **97.4 Ритуал 2.1 (2026-03-01):** scan → doctor --no-llm → report-snapshot. modules=278, risk=46, apply_rate=1.0, rollback_rate=0.0. Learning: remove_unused_import 68%, extract_block_to_helper 57%, extract_nested_function 75%. by_smell_action: deep_nesting|extract_block 89%, long_function|extract_nested 75%, long_function|extract_block 0%. CI: coverage в pytest step (--cov=eurika --cov=cli).
- **97.3 ROADMAP 3–6:** POLYGON_VERIFY_PLAYBOOK.md; KPI в doctor output (learning_kpi); R1 explain: get_explain_data + report/explain_format; тесты get_explain_data/explain_module; R3/R4 edge-case + firewall проходят.
- **97.2 ROADMAP 1–4:** KPI verify_success_rate в report-snapshot (by_smell_action rate); тест whitelist overrides weak_pair; R1_DOMAIN_PRESENTATION_AUDIT.md; R2 logging note в R2_FALLBACK_AUDIT.
- **97.1 Ритуал 2.1 (2026-03-01):** scan → doctor --online → report-snapshot → fix. modules=276, risk=46. Fix: imports_ok ✓ (remove_unused_import). deep_nesting, extractable_block, long_function — blocked by policy (historically weak pair). verify success. Polygon восстановлен.
- **97. Learning from GitHub Phase 2–3:** pattern_library snippet extraction; risk-derived topics first in doctor (OSS patterns in Reference); oss_examples in extract_block/extract_nested ops; preview_operation returns oss_examples; ask_llm_extract_method_hints enriched with OSS snippets (EURIKA_USE_LLM_EXTRACT_HINTS=1).
- **96. Ритуал 2.1 (report-snapshot):** modules=260, risk=46, apply_rate=1.0, rollback_rate=0.0. Learning: remove_unused_import 65%, extract_block_to_helper 40%, extract_nested_function 67%. Whitelist candidates: polygon drills.
- **95. R3 Quality Gate:** EDGE_CASE_MATRIX — добавлен test_prepare_context_sources_exception_continues. Fix ROOT в edge_cases (patch_plan import). 10 edge-case тестов, test_r3_edge_case_matrix_passes.
- **94. Subsystem bypass + R2 Fallback:** prepare.py импорт через eurika.agent (is_whitelisted_for_auto). SELF-GUARD: 0 subsystem bypass. docs/R2_FALLBACK_AUDIT.md — каталог fallback-путей. test_prepare_context_sources_exception_continues.
- **93. Doc + smoke + R1 verification:** UI.md/README/CHANGELOG v3.0.22 — Ollama autostart, --runtime-mode auto для fix/cycle при Allow low-risk campaign. Qt smoke 10 passed; R1 `test_self_check_r1_layer_discipline_on_self` passed; `eurika self-check .` → LAYER DISCIPLINE: OK (0 forbidden, 0 layer violations).
- **92.1 Post-v3.0.21 ritual:** report-snapshot после прогона. modified=2, verify=True; modules=256, risk=46; apply_rate=1.0, rollback_rate=0. Polygon drills 100%: imports_ok, extractable_block, deep_nesting, long_function.
- **92. Polygon long_function + deep_nesting extractable:** DRILL_LONG_FUNCTION — extract_nested_function (вложенная _compute_first_half); DRILL_DEEP_NESTING — polygon_deep_nesting_extractable с extractable блоком 5+ строк; whitelist расширен. ops.py: _is_whitelisted_for_kind — bypass learning gate для polygon. long_function padding (>50 lines) для CodeAwareness. test_polygon_long_function_semantics, test_polygon_deep_nesting_extractable_semantics.
- **91. Polygon catalog + team rollback reset + learning-kpi --polygon:** Polygon — каталог `eurika/polygon/` (imports_ok, extractable_block, long_function, deep_nesting). reset_approvals_after_rollback: сброс team_decision=approve в pending_plan после verify fail + rollback (избегаем re-apply без re-review). learning-kpi `--polygon` — фильтр по eurika/polygon/; секция Polygon drills; Next steps для polygon-targets. KPI_VERIFY_SUCCESS_RATE_PLAN A.2 дополнен.
- **90. Extract_block return-value fix + polygon verify + recursion guard:** extract_block_to_helper при assign-to-outer — helper возвращает value. _block_contains_extracted_call — skip блоков, вызывающих _extracted_block_*, избегаем рекурсии при повторном fix. test_suggest_extract_block_skips_when_block_calls_extracted_helper. extract_block_to_helper при assign-to-outer (result=d в блоке, result в parent_locals) — helper возвращает value, call site: `result = helper(...)`. test_extract_block_to_helper_returns_value_when_block_assigns_to_outer; polygon_extractable_block в verify_cmd (test_polygon_extractable_block_semantics).
- **89. Prepend fallback + team-mode patch_plan:** при пустом architect (no suggest_patch_plan) — не early-exit, а prepend clean_imports/code_smells; whitelist `.eurika/operation_whitelist.json` для polygon (remove_unused_import, extract_block_to_helper); team-mode report включает patch_plan в JSON. Polygon в campaign verify_fail_keys → нужен `EURIKA_IGNORE_CAMPAIGN=1` или `--allow-low-risk-campaign` для diff-теста.

---

## 92.1 Snapshot (2026-02-28) — Post-v3.0.21 ritual

### report-snapshot
- **Fix:** modified=2, skipped=0, verify=True
- **verify_metrics:** before=46, after=46
- **telemetry:** apply_rate=1.0, no_op_rate=0.0, rollback_rate=0.0, verify_duration_ms=1844
- **Doctor:** modules=256, risk=46, apply_rate=0.91 (last 10), rollback_rate=0.3

### Learning (by_action_kind)
- extract_block_to_helper: 36% (5 success, 9 fail)
- remove_unused_import: 59% (19 success, 13 fail)
- extract_nested_function: 50% (1 success, 1 fail)

### learning-kpi --polygon (polygon drills 100%)
- imports_ok.py | remove_unused_import: 4/4
- extractable_block.py | extract_block_to_helper: 2/2
- deep_nesting.py | extract_block_to_helper: 1/1
- long_function.py | extract_nested_function: 1/1

### whitelist_candidates
- eurika/polygon/extractable_block.py|extract_block_to_helper
- eurika/polygon/imports_ok.py|remove_unused_import

---

## 91. Snapshot (2026-02-28) — Polygon catalog + team rollback reset + learning-kpi --polygon

### Scope
- **Polygon catalog:** `eurika/polygon.py` → `eurika/polygon/` (imports_ok, extractable_block, long_function, deep_nesting). Один файл на drill.
- **reset_approvals_after_rollback:** при verify fail + rollback в ветке apply_approved — сброс team_decision=approve в pending_plan.json. Избегаем re-apply одних и тех же ops без re-review.
- **extract_block_to_helper:** _block_has_extracted_call в collect_blocks — skip блоков с вызовом _extracted_block_* (предотвращение рекурсии).
- **learning-kpi --polygon:** фильтр по eurika/polygon/*; секция Polygon (eurika/polygon/); Next steps для polygon-targets с низким rate.

### Метрики (report-snapshot)
- modules=256, risk=46, apply_rate=0.91, rollback_rate=0.3
- remove_unused_import: 54% (15/28), extract_block_to_helper: 21% (3/14)

### Итог
Polygon готов как каталог drills; team-mode rollback-reset; KPI --polygon для drill-фокуса.

### 91.1 Polygon drill-прогон (2026-02-28)

- **Whitelist** `.eurika/operation_whitelist.json` для polygon (imports_ok, extractable_block).
- **Fix apply:** remove_unused_import на imports_ok (3× verify_success), extract_block_to_helper на extractable_block (1× verify_success, team-mode approve).
- **learning-kpi --polygon:** 100% по обоим drills. whitelist-draft: imports_ok в promote candidates.
- **remove_unused_import:** 58% (18/31) — критерий 6/10 выполнен (≥50%).
- **88. 3.6.7 Approvals diff view:** API preview_operation, POST /api/operation_preview, Qt diff panel при выборе строки в Approvals. Single-file ops: remove_unused_import, remove_cyclic_import, extract_block_to_helper, extract_nested_function, fix_import. Polygon подготовлен для теста diff.
- **87. Post-v3.0.18 ritual:** report-snapshot после релиза. modules=255, risk=46, apply_rate=0.93 baseline; 5 skipped (approval_state=pending).
- **86. KPI 4 — Learning from GitHub для code smells:** DIFF_HINTS для extract_block_to_helper; pattern library long_function/deep_nesting; OSS hints в get_code_smell_operations.
- **85. KPI verify_success_rate (план A):** `eurika learning-kpi` — by_smell_action + promote/deprioritize; policy dynamic deny из deny_candidates; context_sources.by_target с verify_success_rate для приоритизации.
- **84. Post-v3.0.17 ritual:** report-snapshot после релиза R2/R3/R4 gates. risk_score=46, apply_rate=0.93, rollback_rate=0.6; learning: extract_block_to_helper 5%, remove_unused_import 38%.
- **83. R4 gate:** `test_r4_dependency_firewall_passes` — EURIKA_STRICT_LAYER_FIREWALL=1 pytest test_dependency_guard + test_dependency_firewall. DEPENDENCY_FIREWALL, API_BOUNDARIES.
- **82. R3 gate:** `test_r3_edge_case_matrix_passes` — pytest -m edge_case должен проходить. EDGE_CASE_MATRIX.
- **81. R2 gate:** `test_doctor_cycle_r2_state_model_on_self` — doctor на проекте возвращает state ∈ {done, error}, валидный state_history. FALLBACK_AUDIT, LOGGING_R2.
- **80. R1 gate:** `test_self_check_r1_layer_discipline_on_self` — регрессионный тест: self-check на проекте выдаёт LAYER DISCIPLINE: OK (0 forbidden, 0 layer violations). EURIKA_STRICT_LAYER_FIREWALL=1 проходит.
- **79. Qt MVP flow зафиксирован:** smoke-сценарий: открыть → выбрать проект (Browse) → Commands → scan → Live output → Stop. First-run UX: при пустом project root при первом запуске показывается folder picker.
- **Qt Hybrid Approvals + Dashboard готовы:** Approvals — Run fix (team-mode) из вкладки, workflow hint, корректный risk из explainability; Dashboard — Top risks, Operational metrics, автообновление при смене project root.
- **R1 Structural Hardening (частично):** Layer discipline OK — 0 forbidden, 0 layer violations. SMELL_TO_KNOWLEDGE_TOPICS перенесён в eurika.knowledge; self-check выводит LAYER DISCIPLINE блок.
- Интерфейсный контур проекта переведён в **Qt-first** режим (`eurika-qt`, пакет `qt_app/`).
- Вкладки Qt: **Models**, **Chat**, **Commands**, **Dashboard**, **Approvals**.
- `eurika serve` работает в **API-only** режиме (`/api/*`), без runtime-раздачи web статики.
- Исторические snapshot'ы ниже (включая Web UI этапы) сохранены как архив эволюции и не удаляются.
- Learning-фокус операционности: `verify_success_rate` по `smell|action|target`, с видимостью сигналов в Qt Dashboard.

---

## 88. Snapshot (2026-02-28) — 3.6.7 Approvals diff view

### Scope
- **preview_operation:** eurika.api — вызов refactor-хендлеров (remove_unused_imports, extract_block_to_helper, …) в режиме «только вычислить»; возврат old_content, new_content, unified_diff.
- **POST /api/operation_preview:** serve.py, body `{operation}`.
- **Qt Approvals diff panel:** при выборе строки — вызов preview_operation, отображение unified diff в QPlainTextEdit.
- **Polygon:** drill state (json, os) для теста diff view и KPI.

### Метрики (report-snapshot)
- modules=256, risk=46
- remove_unused_import: 14 success, 13 fail (52%)
- apply_rate=1.0 (last fix), rollback_rate=0.5

### Итог
ROADMAP 3.6.7 закрыт. Approvals tab показывает реальный diff при выборе операции.

---

## 87. Snapshot (2026-02-27) — Post-v3.0.18 ritual

report-snapshot после релиза v3.0.18. modules=255, risk=46, apply_rate baseline 0.93; 5 ops skipped (pending).

---

## 86. Snapshot (2026-02-27) — KPI 4 Learning from GitHub для code smells

### Scope
- **DIFF_HINTS:** (long_function, extract_block_to_helper), (deep_nesting, extract_block_to_helper) с конкретными подсказками.
- **REMEDIATION_HINTS:** long_function, deep_nesting в eurika.smells.detector.
- **Pattern library:** extract_patterns_from_repos собирает long_function, deep_nesting через CodeAwareness; learn-github --build-patterns обогащает .eurika/pattern_library.json.
- **get_code_smell_operations:** при наличии pattern_library добавляет в description суффикс (OSS: Django, FastAPI).

### Итог
KPI 4 — pattern library и hints для extract_block_to_helper/extract_nested_function.

---

## 85. Snapshot (2026-02-27) — KPI verify_success_rate (план A)

### Scope
- **CLI `eurika learning-kpi [path]`:** KPI блок по smell|action|target, promote (whitelist candidates), deprioritize (policy deny candidates). `--json`, `--top-n`.
- **Policy:** динамический deny из `get_learning_insights` deny_candidates — при rate<0.25, total>=3, совпадение smell|action|target: auto→deny, hybrid→review.
- **Context sources:** `by_target[target].verify_success_rate` из learning; `_apply_context_priority` учитывает rate (high≥0.5 +1, low<0.25 −1), tiebreak по rate.

### Итог
KPI flow зафиксирован. docs/KPI_VERIFY_SUCCESS_RATE_PLAN.md.

---

## 84. Snapshot (2026-02-27) — Post-v3.0.17 ritual

### Scope
- report-snapshot после релиза v3.0.17 (R2/R3/R4 gates).
- Метрики: risk_score=46, apply_rate=0.93, rollback_rate=0.6; median_verify_time 149882 ms.
- Learning: extract_block_to_helper 5% (2/41), remove_unused_import 38% (5/13); split_module, extract_nested_function — 0%.

### Итог
Ритуал закрыт. Следующий фокус — KPI verify_success_rate (ROADMAP бэклог) или направление A/B/C.

---

## 83. Snapshot (2026-02-27) — R4 Modular Platform gate

### Scope
- **R4 gate-тест:** `test_r4_dependency_firewall_passes` — запускает dependency guard (layer + subsystem bypass) в strict mode, assert exit 0.
- SubsystemBypassRule, layer firewall — зафиксированы. release_check.sh, API_BOUNDARIES, DEPENDENCY_FIREWALL.

### Итог
R4 Modular Platform: dependency firewall как gate.

---

## 82. Snapshot (2026-02-27) — R3 Quality Gate

### Scope
- **R3 gate-тест:** `test_r3_edge_case_matrix_passes` — запускает pytest -m edge_case в subprocess, assert exit 0.
- Edge-case matrix (EDGE_CASE_MATRIX): пустой/огромный вход, model error, memory, cycle state.

### Итог
R3 Quality Gate: edge-case block зафиксирован как gate.

---

## 81. Snapshot (2026-02-27) — R2 Runtime Robustness gate

### Scope
- **R2 gate-тест:** `test_doctor_cycle_r2_state_model_on_self` — doctor на проекте возвращает state и state_history. State ∈ {done, error}, history valid (thinking → done|error).
- State model (cycle_state.py), fallback (FALLBACK_AUDIT), logging (LOGGING_R2) — зафиксированы.

### Итог
R2 Runtime Robustness: gate зафиксирован.

---

## 80. Snapshot (2026-02-27) — R1 Structural Hardening gate

### Scope
- **R1 regression test:** `test_self_check_r1_layer_discipline_on_self` проверяет, что self-check на проекте выводит LAYER DISCIPLINE: OK (0 forbidden, 0 layer violations).
- Layer discipline и dependency guard (EURIKA_STRICT_LAYER_FIREWALL=1) остаются в зелёной зоне.

### Итог
R1 Structural Hardening: gate зафиксирован в тестах.

---

## 79. Snapshot (2026-02-27) — Qt MVP flow + First-run UX

### Scope
- **Smoke-сценарий в CYCLE_REPORT:** открыть `eurika-qt` → Browse выбрать project root → Commands → Run scan → вывод в Live output → Stop корректно останавливает. Критерий MVP из стартового промпта выполнен.
- **First-run UX:** при первом запуске (project_root в settings пустой) после show окна автоматически показывается folder picker «Select project root», чтобы пользователь сразу выбрал папку.

### Проверка
1. Запустить `eurika-qt` (при пустом ~/.eurika/qt_settings.json или без project_root).
2. После появления окна — диалог выбора папки.
3. Выбрать проект (например, корень eurika_2.0.Qt) → Dashboard обновляется.
4. Commands → scan → Run → вывод в Live output.
5. Stop — процесс останавливается.

### Итог
Qt MVP Phase 2: smoke flow зафиксирован, first-run prompt улучшает onboarding.

---

## 78. Snapshot (2026-02-27) — Qt Hybrid Approvals + Dashboard MVP

### Scope
- **Approvals tab:** Run fix (team-mode) — кнопка для создания pending plan без перехода на Commands; workflow hint; risk из explainability.risk при отображении таблицы.
- **Dashboard tab:** Top risks (из summary.risks), Operational metrics (apply_rate, rollback_rate, median_verify_time_ms); обновление при смене project root.
- **UI.md:** обновлено описание вкладок.

### Итог
Hybrid approvals и Dashboard доведены до готовности (MVP из стартового промпта Qt).

---

## 77. Snapshot (2026-02-27) — R1 Layer discipline (Structural Hardening)

### Scope
- **Layer discipline:** Устранено нарушение L3→L6: `planner_llm` импортировал `cli.orchestration.doctor.SMELL_TO_KNOWLEDGE_TOPICS`. Константа перенесена в `eurika/knowledge/topics.py`; doctor, planner_llm, chat импортируют из `eurika.knowledge`.
- **self-check:** Добавлен блок LAYER DISCIPLINE (R1). При 0 нарушений: «OK (0 forbidden, 0 layer violations)»; при наличии — список forbidden/layer violations.
- **Architecture.md:** Обновлены 0.6, 0.7, 0.8 (Knowledge API, self-check output).

### Итог
Dependency guard стабильно ловит нарушения; EURIKA_STRICT_LAYER_FIREWALL=1 проходит. Size budget и Domain vs Presentation — в плане R1 (итеративно).

---

## 76. Snapshot (2026-02-27) — Doc sync + Qt tabs (v3.0.12)

### Scope
- Синхронизация документации с текущей стадией проекта.
- **pyproject.toml:** version 3.0.12, requires-python >=3.10, description с Qt-first и списком вкладок.
- **README:** Qt section обновлён — Models, Chat Apply/Reject, Terminal tab, Commands, Dashboard, Approvals.
- **CHANGELOG:** добавлена секция v3.0.12 (Models tab, Chat hardening, Terminal via intent, runtime hardening).
- **UI.md, MIGRATION_WEB_TO_QT.md:** описание текущих Qt-вкладок и возможностей.

### Итог
Документация приведена в соответствие с Qt-first интерфейсом на этапе v3.0.12.

---

## 75. Snapshot (2026-02-27) — Qt runtime hardening + stability gate + chat actions E2E

### Scope
- **Runtime hardening (Qt):** в `qt_app/ui/main_window.py` добавлен `closeEvent` с корректным shutdown фоновых процессов:
  - `QProcess.terminate()` -> `waitForFinished()` -> `kill()` fallback для `ollama` и task-process.
  - остановка health timer перед закрытием окна.
- **Stability gate окружения:** `tests/test_qt_smoke.py` переведён на запуск smoke в изолированном subprocess.
  - Добавлен gate для Python 3.14: рекомендован отдельный интерпретатор 3.12/3.13 через `EURIKA_QT_SMOKE_PYTHON`.
  - Даже при child teardown-crash родительский pytest не падает.
- **Chat action hardening (E2E):** расширены сценарии для `ui_add_empty_tab`/`ui_remove_tab` по цепочке `interpret -> pending_plan -> применяй -> verify`.
  - Закрывается регрессия уровня "удали" -> "добавь".
- **Operability 3.6 KPI (точечно):**
  - policy whitelist теперь поддерживает kind-level entry (без обязательного `target_file`) + fallback на versioned controlled whitelist.
  - добавлен `operation_whitelist.controlled.json` (seed: 1-2 action-kind для осторожного rollout).

### Mitigation plan (runtime incident)
1. Детачить Qt smoke в child-process (уже сделано).
2. В CI/ритуале держать отдельный gate для рекомендуемого Python runtime Qt (3.12/3.13).
3. Сохранять строгий verify/rollback контракт для кодовых изменений через chat executor.

---

## 74. Snapshot (2026-02-26) — Target-aware policy + operation whitelist (controlled rollout)

### Scope
- В policy добавлен **target-aware override** по истории verify_fail:
  - для operation key (`target|kind|location`) при `verify_fail >= 2`:
    - `auto` → `deny`
    - `hybrid` → `review`
- Добавлен **operation whitelist**: `.eurika/operation_whitelist.json` для controlled rollout risky ops.
- Starter whitelist: `extract_block_to_helper` для `eurika/api/chat.py` (`deep_nesting`).

### Проверка
- Controlled hybrid (`--approve-ops 1`): применён `eurika/api/chat.py`, verify ✅ (`458 passed`).
- В отчёте зафиксировано:
  - `policy_reason = whitelisted target for controlled hybrid rollout`
  - `execution_outcome = verify_success`.
- Контрольные запуски на других targets:
  - `eurika/storage/global_memory.py` — verify_fail + rollback
  - `cli/core_handlers.py` — verify_fail + rollback.

### Итог
1. `extract_block_to_helper` остаётся guarded-path (не массовый auto-fix).
2. Появился безопасный механизм точечного rollout через whitelist.
3. Новый операционный фокус: `verify_success_rate` по `smell|action|target` (а не только apply-rate).

---

## 72. Snapshot (2026-02-26) — Ритуал 2.1: extract_block_to_helper массовый verify_fail → rollback

### Scope
- Полный ритуал: scan → doctor → fix → report-snapshot.
- После релаксации suggest_extract_block (parent_locals, min_lines=3): план fix содержал **24 ops extract_block_to_helper**.
- Все 24 применены, verify провален (10 failed tests), **rollback** отработал — 16 файлов восстановлены.

### Doctor (eurika_doctor_report.json)
| Метрика | Значение |
|---------|----------|
| Модули | 221 |
| Зависимости | 108 |
| Risk score | 46/100 |
| apply_rate (baseline) | 0.8095 |
| patch_plan operations | 0 (context filter) |

### Fix (eurika_fix_report.json)
| Поле | Значение |
|------|----------|
| modified | 16 |
| rollback | done (verify_failed) |
| operations | 24 × extract_block_to_helper |
| verify | failed (10 tests) |
| apply_rate (current) | 0.6667 |
| rollback_rate | 1.0 |

### Learning (by_action_kind)
| Action | Success | Fail | Rate |
|--------|---------|------|------|
| remove_unused_import | 7 | 43 | 14% |
| split_module | 2 | 7 | 22% |
| extract_class | 1 | 1 | 50% |
| refactor_code_smell | 0 | 1041 | 0% |
| extract_nested_function | 0 | 33 | 0% |
| **extract_block_to_helper** | 0 | 28 (+24) | **0%** |

### Выводы
1. **extract_block_to_helper** — 0% success; релаксация (parent_locals, min_lines=3) породила много ops, все провалили verify.
2. **Snapshot #73:** эвристика ужесточена — см. ниже.

---

## 73. Snapshot (2026-02-26) — extract_block эвристика: ужесточение после verify_fail

### Scope
- Реверт и улучшение эвристики suggest_extract_block после массового verify_fail (24 ops → rollback).
- **Изменения:**
  1. **parent_params only** — used_from_outer из parent_params (не parent_locals); исключены loop vars и промежуточные locals.
  2. **writes_to_params** — пропуск блоков, которые присваивают в параметры parent.
  3. **min_lines=5** (вместо 3) — меньше мелких экстракций.
  4. **_EXTRACT_BLOCK_SKIP_PATTERNS** — skip для eurika/refactor/, planner_patch_ops.py, planner_llm.py, report/, cli/orchestration/ (модули, где extraction часто ломает verify).
  5. **Исправлен баг** extra_params: `(used - assigned) & parent_params`.

### Итог
- Эвристика консервативнее; ожидаем меньше ops, но выше success rate при следующем прогоне.

---

## 71. Snapshot (2026-02-26) — Apply-rate: skip tests/ в get_clean_imports

### Scope
- get_clean_imports_operations: пропуск tests/ — policy всё равно deny, предложение создаёт no-op.
- Цель: не тратить слоты операций на файлы, которые policy заблокирует.

### Итог
- Меньше no-op по remove_unused_import для tests/*; apply-rate при прочих равных выше.

---

## 70. Snapshot (2026-02-26) — allow-low-risk-campaign, tool_contract fix, REMOVE_UNUSED_IMPORT_SKIP

### Scope
- `--allow-low-risk-campaign` и `EURIKA_CAMPAIGN_ALLOW_LOW_RISK=1`: низкорисковые ops (remove_unused_import) обходят campaign skip.
- tool_contract: init импортирует DefaultToolContract из tool_contract_extracted напрямую; убран re-export в tool_contract.py.
- `REMOVE_UNUSED_IMPORT_SKIP`: tool_contract.py исключён из remove_unused_import (re-export layer).
- test_cli_env: skip при отсутствии python-dotenv.
- eurika_cli: dotenv_values(path) с корректной передачей пути.

### Проверка
- pytest: 450 passed, 1 skipped.
- fix --allow-low-risk-campaign: cycle complete (tool_contract не в плане; test_cli_env deny по policy).

### Итог
- campaign skip ослаблен для low-risk; tool_contract защищён от false-positive remove_unused_import.

---

## 69. Snapshot (2026-02-26) — Dogfooding no-op (campaign_skipped)

### Scope
- Полный цикл `eurika fix .` + `eurika report-snapshot .` на проекте Eurika.
- План: 1 операция remove_unused_import (eurika/agent/tool_contract.py, policy: allow).
- Итог: campaign_skipped=1 — target в recent_verify_fail_targets; apply_rate=0, no_op_rate=1.
- Архитектура: 221 модулей, risk 46/100, maturity low; learning по by_action_kind без изменений.

### Проверка
- report-snapshot: context effect (recent_verify_fail_targets=8) → campaign skip, baseline apply_rate 0.87.

### Итог
- Контекстный фильтр отработал: операция отфильтрована по истории verify_fail.

---

## 68. Snapshot (2026-02-25) — Дальнейшая доработка long/deep закрыта

### Scope
- Подтверждено, что пункты ROADMAP «Дальнейшая доработка» уже реализованы:
  - `refactor_code_smell`: по умолчанию не эмитить (emit_todo=0); `EURIKA_EMIT_CODE_SMELL_TODO=1` для старого поведения
  - `deep_nesting`: `EURIKA_DEEP_NESTING_MODE=heuristic|hybrid|llm|skip`, suggest_extract_block + extract_block_to_helper
  - `long_function` fallback: suggest_extract_block (min_lines=5) при отсутствии вложенных def
- ROADMAP обновлён: эти пункты перенесены в «Закрыто»; новый бэклог — dogfooding.

### Итог
- Фокус смещён на dogfooding — регулярные циклы на Eurika для валидации и метрик.

---

## 67. Snapshot (2026-02-25) — extract_nested_function controlled scenario verify_success

### Scope
- реализован uplift `extract_nested_function` (ROADMAP backlog):
  - поддержка extraction с до 3 parent locals (params и locals);
  - валидация free names и лимит переменных в `extract_nested_function`;
  - точнее диагностика в `diagnose_extract_nested_failure`;
  - planner rule `_EXTRACT_NESTED_INTERNAL_SKIP`: блокировка внутренних helper (`_has_nonlocal_or_global`, `add_extra_args_to_calls`, `collect_blocks`) в `eurika/refactor/extract_function.py`;
  - `_should_try_extract_nested` обновлён для outcome (`verify_fail`, `not_applied`) и legacy aggregates.
- controlled scenario `.tmp_extract_nested_demo/`: long function + nested helper — `fix ... --allow-campaign-retry --approve-ops 1` успешно применён.
- тесты: dry-run no-op допускает `operations=[]`; skip-причины при неудачном extraction.

### Проверка
- `pytest` regression pack: `tests/test_cycle.py`, `tests/test_api.py`, `tests/test_patch_apply.py`, `tests/test_extract_function.py` — passed;
- learning-summary: `extract_nested_function` — `verify_success=1`.

### Итог
- `extract_nested_function` получил подтверждённый verify_success в controlled scenario;
- planner не предлагает extraction для внутренних helper extract_function.py.

---

## 66. Snapshot (2026-02-23) — Uplift refactor/extract action-kind (phase 1+2)

### Scope
- выполнен двухфазный uplift по проблемным action-kind:
  - `refactor_code_smell`
  - `extract_nested_function`
  - `extract_block_to_helper`
- **Фаза 1 (метрики/семантика outcome):**
  - в `fix`-контуре добавлен per-op `execution_outcome` (`not_applied|verify_success|verify_fail`);
  - learning-агрегаты разделяют `not_applied`, `verify_success`, `verify_fail` (без смешивания с `fail`);
  - `report-snapshot` показывает расширенные counters в `by_action_kind`.
- **Фаза 2 (extract hardening):**
  - `extract_nested_function`: устойчивый выбор parent-context и post-validation AST (`parse/compile`) перед возвратом;
  - `extract_block_to_helper`: стабильный выбор target-block в parent-функции, post-validation AST;
  - `patch_apply_handlers`: детальные причины skip через `diagnose_extract_*_failure(...)` вместо общего `extraction failed`.

### Проверка
- `pytest` regression pack:
  - `tests/test_cycle.py`
  - `tests/test_api.py`
  - `tests/test_patch_apply.py`
  - `tests/test_extract_function.py`
  - `tests/test_storage_memory.py`
  - `tests/test_architecture_learning.py`
  - результат: `107 passed`
- `mypy` по изменённым модулям:
  - `cli/orchestration/apply_stage.py`
  - `eurika/storage/event_views.py`
  - `architecture_learning.py`
  - `eurika/refactor/extract_function.py`
  - `patch_apply_handlers.py`
  - `report/report_snapshot.py`
  - результат: `Success: no issues found in 6 source files`
- `eurika report-snapshot .`:
  - `by_action_kind` теперь показывает `verify_success/verify_fail/not_applied` рядом с `success/fail`.

### Итог
- метрики action-kind стали операционно прозрачнее (`not_applied` отделён от `verify_fail`);
- extract-пайплайн получил более предсказуемую диагностику и синтаксическую валидацию результата.

---

## 65. Snapshot (2026-02-23) — Product readiness B closed (6/10)

### Scope
- закрыт блок `B. Продуктовая готовность (5→6/10)` в ROADMAP:
  - `B.1` README quick start venv-нейтральный;
  - `B.2` README содержит 4 продуктовые команды (`scan`, `doctor`, `fix --dry-run`, `serve`);
  - `B.3` `UI.md` оформлен как MVP-гайд с вкладками и Chat;
  - `B.4` `CLI.md` содержит рекомендуемый цикл/CI-CD и выровнен по venv-нейтральной формулировке;
  - `B.5` 5-minute onboarding сценарий покрыт документами README/UI/CLI;
  - `B.6` актуальность CYCLE_REPORT и ритуалов подтверждена snapshot-цепочкой `#61..#64`.

### Итог
- оценка `Продуктовая готовность` в ROADMAP повышена до `6/10`;
- backlog-пункт B снят как закрытый, фокус смещён на качество рефакторинг-операций (`long_function/deep_nesting`).

---

## 64. Snapshot (2026-02-23) — Product onboarding docs refresh (README)

### Scope
- закрыт следующий пункт backlog по продуктовой готовности:
  - обновлён `README.md` с venv-нейтральным quick start;
  - добавлен явный блок установки (`python -m venv .venv`, `pip install -e ".[test]"`);
  - сохранены и выделены базовые команды onboarding:
    - `eurika scan .`
    - `eurika doctor .`
    - `eurika fix . --dry-run`
    - `eurika serve .`

### Итог
- onboarding для новых пользователей стал короче и воспроизводимее без machine-specific путей.

---

## 63. Snapshot (2026-02-23) — Full cycle + snapshot ritual (post R3 typing)

### Команды
- `eurika cycle .`
- `eurika report-snapshot .`

### Report-snapshot вывод (факт)
- **Fix (`eurika fix .`)**
  - `modified=0`, `skipped=0`, `verify=N/A`
  - telemetry: `apply_rate=0.0`, `no_op_rate=1.0`, `rollback_rate=0.0`, `verify_duration_ms=0`, `median_verify_time_ms=N/A`
- **Doctor (`eurika_doctor_report.json`)**
  - `modules=221`
  - `dependencies=108`
  - `risk_score=46/100`
  - `apply_rate(last 10)=0.3576`
  - `rollback_rate=0.7`
  - `median_verify_time_ms=96430`
- **Context effect (3.6.3)**
  - `context_targets=0`, `recent_verify_fail_targets=10`, `campaign_rejected_targets=0`
  - `apply_rate: current=0.0, baseline=0.3576 (Δ -35.8pp)`
  - `no_op_rate: current=1.0, baseline=0.0 (Δ +100.0pp)`
- **Learning (top)**
  - `refactor_code_smell: 0 success / 1042 fail (0%)`
  - `remove_unused_import: 8 success / 41 fail (16%)`
  - `split_module: 2 success / 7 fail (22%)`
  - `extract_nested_function: 0 success / 30 fail (0%)`

### Итог
- полный ритуал завершён в no-op режиме без apply и без verify-шага (`verify=N/A`);
- архитектурный срез стабилен (`risk_score=46`, cycles=0), но продуктивность smell-рефакторинга остаётся основной зоной улучшения.

---

## 62. Snapshot (2026-02-23) — Ritual 2.1 `eurika report-snapshot .` (post R3 typing)

### Команда
- `eurika report-snapshot .`

### Fix (`eurika fix .`)
- `modified`: `0`
- `skipped`: `0`
- `verify`: `True`

### Doctor (`eurika_doctor_report.json`)
- `modules`: `220`
- `dependencies`: `109`
- `risk_score`: `43/100`
- `apply_rate` (last 10 runs): `0.3576`
- `rollback_rate`: `0.7`
- `median_verify_time_ms`: `96430`

### Learning
- `by_action_kind`:
  - `refactor_code_smell`: `0 success / 1042 fail (0%)`
  - `remove_unused_import`: `8 success / 41 fail (16%)`
  - `split_module`: `2 success / 7 fail (22%)`
  - `extract_nested_function`: `0 success / 30 fail (0%)`
  - `extract_class`: `1 success / 1 fail (50%)`
  - `extract_block_to_helper`: `0 success / 4 fail (0%)`
- `by_smell_action`:
  - `long_function|refactor_code_smell`: `total=868, success=0, fail=857`
  - `unknown|remove_unused_import`: `total=49, success=8, fail=41`
  - `deep_nesting|refactor_code_smell`: `total=187, success=0, fail=185`
  - `god_module|split_module`: `total=9, success=2, fail=7`
  - `long_function|extract_nested_function`: `total=30, success=0, fail=30`
  - `god_class|extract_class`: `total=2, success=1, fail=1`
  - `long_function|extract_block_to_helper`: `total=2, success=0, fail=2`
  - `deep_nesting|extract_block_to_helper`: `total=2, success=0, fail=2`

### Итог
- ритуал 2.1 выполнен: post-R3 typing состояние зафиксировано в едином snapshot;
- подтверждена стабильность verify в текущем срезе (`modified=0`, `verify=True`), при этом learning-метрики по smell-refactor остаются ключевой зоной улучшения.

---

## 61. Snapshot (2026-02-23) — R3 Typing contract final consolidate ritual

### Scope
- финальная консолидация R3 typing-contract без расширения покрытия модулей;
- подтверждён boundary-gate на полном текущем скоупе (`80` модулей в `tool.mypy.overrides`);
- выполнен единый целевой regression-pack по критичным контурам:
  - CLI/orchestration (`cycle`, `hitl`, `team_mode`);
  - API surface;
  - agent/runtime + tool-contract;
  - storage/memory + campaign checkpoint;
  - reasoning/context + architect;
  - evolution/diagnostics + semantic architecture;
  - knowledge/learning.

### Проверка
- full mypy gate:
  - `Success: no issues found in 80 source files`
- targeted regression pack:
  - `tests/test_cycle.py`
  - `tests/test_api.py`
  - `tests/test_agent_runtime.py`
  - `tests/test_tool_contract.py`
  - `tests/test_storage_memory.py`
  - `tests/test_campaign_checkpoint.py`
  - `tests/test_context_sources.py`
  - `tests/test_architect.py`
  - `tests/test_evolution_diff.py`
  - `tests/test_architecture_diagnostics.py`
  - `tests/test_semantic_architecture.py`
  - `tests/test_knowledge.py`
  - `tests/test_github_search.py`
  - `tests/test_team_mode.py`
  - `tests/test_hitl_cli.py`
  - результат: `157 passed`

### Итог
- R3 typing-contract консолидирован: gate стабилен, регрессионный контур зелёный, rollout step-7..step-16 подтверждён финальным ритуалом.

---

## 60. Snapshot (2026-02-23) — R3 Typing contract step 16 (support layer: checks/utils/storage sidecar)

### Scope
- расширен typing-gate на support-слой:
  - `eurika/__init__.py`
  - `eurika/agent/__init__.py`
  - `eurika/reasoning/__init__.py`
  - `eurika/refactor/__init__.py`
  - `eurika/checks/__init__.py`
  - `eurika/checks/dependency_firewall.py`
  - `eurika/checks/file_size.py`
  - `eurika/utils/__init__.py`
  - `eurika/utils/fs.py`
  - `eurika/utils/logging.py`
  - `eurika/storage/events.py`
  - `eurika/storage/global_memory.py`
  - `eurika/storage/campaign_checkpoint.py`
- дополнительный type-hardening для полного гейта:
  - `cli/orchestration/prepare.py`: `runtime_mode` приведён к `Literal["assist", "hybrid", "auto"]` перед `load_policy_config(...)`.
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 80 модулей boundary-гейта.

### Проверка
- `mypy` по support-слою: `Success: no issues found in 13 source files`
- `mypy` по full boundary-скоупу: `Success: no issues found in 80 source files`
- regression-check:
  - `tests/test_campaign_checkpoint.py`
  - `tests/test_global_memory.py`
  - `tests/test_file_size_check.py`
  - `tests/test_clean_imports_cli.py`
  - `tests/test_cycle.py`
  - результат: `73 passed`

### Итог
- typed boundary расширен на инфраструктурный support-контур; full-gate стабилен на 80 модулях.

---

## 59. Snapshot (2026-02-23) — R3 Typing contract step 15 (analysis + reporting layer)

### Scope
- расширен typing-gate на analysis/reporting слой:
  - `eurika/analysis/__init__.py`
  - `eurika/analysis/cycles.py`
  - `eurika/analysis/metrics.py`
  - `eurika/analysis/topology.py`
  - `eurika/analysis/self_map.py`
  - `eurika/analysis/scanner.py`
  - `eurika/analysis/graph.py`
  - `eurika/reporting/__init__.py`
  - `eurika/reporting/json.py`
  - `eurika/reporting/markdown.py`
  - `eurika/reporting/text.py`
- минимальные type-hardening правки фасадов:
  - `eurika/analysis/graph.py`: wildcard-export заменён на explicit export `ProjectGraph`, `NodeMetrics`;
  - `eurika/analysis/self_map.py`: wildcard-export заменён на explicit export `load_self_map`, `build_graph_from_self_map`.
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 67 модулей boundary-гейта.

### Проверка
- `mypy` по analysis/reporting модулям: `Success: no issues found in 11 source files`
- `mypy` по full boundary-скоупу: `Success: no issues found in 67 source files`
- regression-check:
  - `tests/test_semantic_architecture.py`
  - `tests/test_architecture_diagnostics.py`
  - `tests/test_architecture_history.py`
  - `tests/test_evolution_diff.py`
  - `tests/test_api.py`
  - результат: `27 passed`

### Итог
- typed boundary расширен на analysis/reporting контур; import-контракты фасадов стабилизированы для `mypy attr-defined`.

---

## 58. Snapshot (2026-02-23) — R3 Typing contract step 14 (smells + core layer)

### Scope
- расширен typing-gate на smells/core слой:
  - `eurika/smells/__init__.py`
  - `eurika/smells/detector.py`
  - `eurika/smells/models.py`
  - `eurika/smells/rules.py`
  - `eurika/smells/summary.py`
  - `eurika/smells/advisor.py`
  - `eurika/smells/health.py`
  - `eurika/core/__init__.py`
  - `eurika/core/snapshot.py`
  - `eurika/core/pipeline.py`
- минимальные type-hardening правки:
  - `eurika/smells/advisor.py`: добавлены явные типы `fan: Dict[str, Tuple[int, int]]` в helper-функции рекомендаций;
  - `eurika/core/pipeline.py`: убран wildcard-export, добавлен explicit re-export `run_full_analysis` и `build_snapshot_from_self_map` + `__all__`.
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 56 модулей boundary-гейта.

### Проверка
- `mypy` по smells/core модулям: `Success: no issues found in 10 source files`
- `mypy` по full boundary-скоупу: `Success: no issues found in 56 source files`
- regression-check:
  - `tests/test_architecture_smells.py`
  - `tests/test_architecture_advisor.py`
  - `tests/test_architecture_health.py`
  - `tests/test_architecture_diagnostics.py`
  - `tests/test_evolution_diff.py`
  - `tests/test_api.py`
  - результат: `29 passed`

### Итог
- typed boundary расширен до smells/core контура; совместимость import-контрактов `eurika.core.pipeline` сохранена.

---

## 57. Snapshot (2026-02-23) — R3 Typing contract step 13 (evolution layer)

### Scope
- расширен typing-gate на evolution-слой:
  - `eurika/evolution/__init__.py`
  - `eurika/evolution/diff.py`
  - `eurika/evolution/history.py`
- в `diff.py` добавлен безопасный парсер centrality shift payload:
  - `_parse_centrality_shift(...)` нормализует `module/fan_in/fan_out`,
  - убирает `object is not iterable`/`invalid index type` ошибки в отчётных секциях,
  - поведение для валидных данных не изменяется; невалидные записи пропускаются.
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 46 модулей boundary-гейта.

### Проверка
- `mypy` по evolution-модулям: `Success: no issues found in 3 source files`
- `mypy` по full boundary-скоупу: `Success: no issues found in 46 source files`
- regression-check:
  - `tests/test_cycle.py -k "report_snapshot_context_effect_block or report_snapshot_telemetry_block"`
  - `tests/test_architect.py`
  - результат: `2 passed` (targeted), без регрессий

### Итог
- typed boundary расширен на evolution diff/history контур; отчётная типизация стабилизирована.

---

## 56. Snapshot (2026-02-23) — R3 Typing contract step 12 (agent runtime contracts)

### Scope
- расширен typing-gate на runtime/tool-contract модули:
  - `eurika/agent/runtime.py`
  - `eurika/agent/tool_contract.py`
  - `eurika/agent/tool_contract_extracted.py`
  - `eurika/agent/tool_contract_toolcontract.py`
- в `cli/orchestration/full_cycle.py` добавлен type-safe cast:
  - `runtime_mode` приводится к `Literal["assist", "hybrid", "auto"]` перед `run_agent_cycle`,
  - устраняет `mypy` arg-type без изменения runtime-поведения.
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 43 модулей boundary-гейта.

### Проверка
- `mypy` по runtime/tool-contract модулям: `Success: no issues found in 4 source files`
- `mypy` по full boundary-скоупу: `Success: no issues found in 43 source files`
- regression-check:
  - `tests/test_agent_runtime.py`
  - `tests/test_tool_contract.py`
  - `tests/test_cli_runtime_mode.py`
  - результат: `18 passed`

### Итог
- typed boundary расширен на runtime/tool-contract контур; gate стабилен на полном 43-модульном скоупе.

---

## 55. Snapshot (2026-02-23) — R3 Typing contract step 11 (reasoning layer)

### Scope
- расширен typing-gate на reasoning-слой:
  - `eurika/reasoning/architect.py`
  - `eurika/reasoning/context_sources.py`
  - `eurika/reasoning/planner_patch_ops.py`
  - `eurika/reasoning/graph_ops.py`
- в `architect` закрыт type-дефект доступа к patch plan:
  - безопасное извлечение `operations` через `isinstance(patch_plan, dict)` вместо прямой индексации nullable payload.
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 39 модулей boundary-гейта.

### Проверка
- `mypy` по reasoning-модулям: `Success: no issues found in 4 source files`
- `mypy` по full boundary-скоупу: `Success: no issues found in 39 source files`
- regression-check:
  - `tests/test_architect.py`
  - `tests/test_context_sources.py`
  - результат: `17 passed`

### Итог
- typed boundary расширен на planner/architect reasoning контур без изменения runtime-поведения.

---

## 54. Snapshot (2026-02-23) — R3 Typing contract step 10 (learning + knowledge layer)

### Scope
- расширен typing-gate на learning/knowledge слой:
  - `eurika/learning/__init__.py`
  - `eurika/learning/github_search.py`
  - `eurika/learning/pattern_library.py`
  - `eurika/learning/curated_repos.py`
  - `eurika/knowledge/__init__.py`
  - `eurika/knowledge/base.py`
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 35 модулей boundary-гейта.

### Проверка
- `mypy` по 35 модулям:
  - CLI + orchestration + API + agent/storage + storage facade + learning/knowledge
  - результат: `Success: no issues found in 35 source files`
- regression-check:
  - `tests/test_github_search.py`
  - `tests/test_knowledge.py`
  - `tests/test_architect.py`
  - результат: `38 passed`

### Итог
- typing-contract gate покрывает весь operational path и knowledge/learning слой без изменения runtime-поведения.

---

## 53. Snapshot (2026-02-23) — R3 Typing contract step 9 (storage facade layer)

### Scope
- расширен typing-gate на storage facade/utility слой:
  - `eurika/storage/__init__.py`
  - `eurika/storage/persistence.py`
  - `eurika/storage/paths.py`
  - `eurika/storage/operational_metrics.py`
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 29 модулей boundary-гейта.

### Проверка
- `mypy` по 29 модулям:
  - CLI entry + orchestration + API + agent/storage contracts + storage facade layer
  - результат: `Success: no issues found in 29 source files`
- regression-check:
  - `tests/test_storage_memory.py`
  - `tests/test_storage_events.py`
  - `tests/test_architecture_learning.py`
  - `tests/test_architecture_feedback.py`
  - `tests/test_cycle.py -k "attach_fix_telemetry_median_verify_time or attach_fix_telemetry_counts_campaign_session_skips"`
  - результат: `2 passed` (targeted), без регрессий

### Итог
- boundary typing-gate расширен до полного storage entry/facade слоя, включая operational metrics pipeline.

---

## 52. Snapshot (2026-02-23) — R3 Typing contract step 8 (event views/memory)

### Scope
- расширен typing-gate на storage event-модель:
  - `eurika/storage/event_views.py`
  - `eurika/storage/event_engine.py`
  - `eurika/storage/memory.py`
- в `event_views` добавлены `TYPE_CHECKING`-импорты для:
  - `LearningRecord`
  - `FeedbackRecord`
  что закрывает `name-defined` ошибки без влияния на runtime.
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 25 модулей boundary-гейта.

### Проверка
- `mypy`:
  - `eurika/storage/event_views.py`
  - `eurika/storage/event_engine.py`
  - `eurika/storage/memory.py`
  - плюс ранее включённые agent/storage контрактные модули
  - результат: `Success: no issues found in 9 source files`
- regression-check:
  - `tests/test_storage_memory.py`
  - `tests/test_storage_events.py`
  - `tests/test_architecture_learning.py`
  - `tests/test_architecture_feedback.py`
  - результат: `18 passed`

### Итог
- typed boundary расширен до event-driven memory слоя; learning/feedback views и event-store контракты подтверждены тестами.

---

## 51. Snapshot (2026-02-23) — R3 Typing contract step 7 (agent/storage contracts)

### Scope
- расширен typing-gate на контракты agent/storage слоя:
  - `cli/orchestration/models.py`
  - `eurika/agent/models.py`
  - `eurika/agent/config.py`
  - `eurika/agent/policy.py`
  - `eurika/agent/tools.py`
  - `eurika/storage/session_memory.py`
- устранён typing-дефект в `SessionMemory`:
  - `path` переведён из nullable в стабильный `Path`, что убрало `union-attr` ошибки в `_load/_save`.
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 22 модулей (CLI + orchestration + API + agent/storage contracts).

### Проверка
- `mypy` по 22 модулям boundary-гейта:
  - результат: `Success: no issues found in 22 source files`
- regression-check:
  - `tests/test_session_memory.py`
  - `tests/test_cycle_test_apply_campaign_memory_filters_rejected_ops.py`
  - `tests/test_context_sources.py`
  - результат: `6 passed`

### Итог
- typed boundary расширен до ключевых контрактов памяти/политик; поведение campaign/session memory остаётся стабильным.

---

## 50. Snapshot (2026-02-23) — R3 typing consolidate ritual (16-module gate)

### Сценарий
- единый `mypy`-прогон по целевому boundary-сетапу (16 модулей):
  - orchestration core: `prepare`, `apply_stage`, `fix_cycle_impl`, `hybrid_approval`, `full_cycle`, `facade`, `doctor`, `team_mode`, `deps`
  - CLI entry: `cli/orchestrator.py`, `cli/wiring/parser.py`, `cli/wiring/dispatch.py`, `cli/core_handlers.py`, `cli/handlers.py`
  - API surface: `eurika/api/__init__.py`, `eurika/api/serve.py`
- целевой regression-набор:
  - `tests/test_hitl_cli.py`
  - `tests/test_team_mode.py`
  - `tests/test_github_search.py`
  - `tests/test_api.py`
  - `tests/test_api_serve.py`
  - `tests/test_cycle.py -k "doctor_runtime_reports_degraded_mode_when_llm_disabled or knowledge_topics_derived_from_summary or run_full_cycle_wrapper_delegates_to_orchestration_module or full_cycle_propagates_doctor_runtime_to_fix_report or fix_cycle_approve_ops_selects_subset or fix_cycle_approve_ops_reject_ops_conflict"`

### Результат
- `mypy`: `Success: no issues found in 16 source files`
- `pytest`: `5 passed` (targeted selection), без регрессий

### Итог
- R3 typing-contract gate подтверждён консолидированным ритуалом: покрыт полный путь `CLI entry -> orchestration -> API surface`, поведение остаётся стабильным.

---

## 49. Snapshot (2026-02-23) — R3 Typing contract step 6 (API surface)

### Scope
- расширен typing-gate на API слой:
  - `eurika/api/__init__.py`
  - `eurika/api/serve.py`
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 16 модулей (orchestration + CLI entry + API surface).

### Проверка
- `mypy` по 16 модулям:
  - orchestration core + CLI entry/wiring + API surface
  - результат: `Success: no issues found in 16 source files`
- regression-check:
  - `tests/test_api.py` — green
  - `tests/test_api_serve.py` — green
  - суммарно: `54 passed`

### Итог
- typing-contract gate покрывает полный путь `CLI entry -> orchestration -> API surface` без изменения runtime-поведения.

---

## 48. Snapshot (2026-02-23) — R3 Typing contract step 5 (CLI wiring + core handlers)

### Scope
- расширен typing-gate на CLI entry/wiring слой:
  - `cli/wiring/parser.py`
  - `cli/wiring/dispatch.py`
  - `cli/core_handlers.py`
  - `cli/handlers.py`
- устранён typing-дефект в `handle_learn_github`:
  - нормализован сбор `projects` к `set[str]` перед `sorted(...)`.
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 14 модулей orchestration+CLI entry boundary.

### Проверка
- `mypy` по 14 модулям:
  - orchestration core + `cli/orchestrator.py` + `cli/wiring/*` + `cli/core_handlers.py` + `cli/handlers.py`
  - результат: `Success: no issues found in 14 source files`
- regression-check:
  - `tests/test_hitl_cli.py` — green
  - `tests/test_team_mode.py` — green
  - `tests/test_github_search.py` — green

### Итог
- typing-contract gate покрывает полный CLI entry path до orchestration core без изменения runtime-поведения.

---

## 47. Snapshot (2026-02-23) — R3 Typing contract step 4 (doctor + team mode + deps)

### Scope
- расширен typing-gate на ещё 3 модуля orchestration:
  - `cli/orchestration/doctor.py`
  - `cli/orchestration/team_mode.py`
  - `cli/orchestration/deps.py`
- обновлён `pyproject.toml` (`tool.mypy.overrides`) для целевого скоупа 10 модулей.
- в `fix_cycle_impl` добавлены типобезопасные правки:
  - `fix_cycle_deps` теперь типизирован как `Callable[[], FixCycleDeps]`;
  - для team-mode сохранения введён безопасный fallback `pending_patch_plan = patch_plan or {"operations": operations}`.

### Проверка
- `mypy` по 10 модулям orchestration/entry boundary:
  - `prepare`, `apply_stage`, `fix_cycle_impl`, `hybrid_approval`, `full_cycle`, `facade`, `doctor`, `team_mode`, `deps`, `orchestrator`
  - результат: `Success: no issues found in 10 source files`
- regression-check:
  - `tests/test_team_mode.py` — green
  - `tests/test_cycle.py -k "doctor_runtime_reports_degraded_mode_when_llm_disabled or knowledge_topics_derived_from_summary"` — green

### Итог
- typing-contract gate расширен на весь orchestration core-путь (prepare/apply/fix/full/doctor/team/deps/orchestrator) без изменения runtime-поведения.

---

## 46. Snapshot (2026-02-23) — R3 Typing contract step 3 (full-cycle + facade)

### Scope
- расширен typing-gate на orchestration-routing слой:
  - `cli/orchestration/full_cycle.py`
  - `cli/orchestration/facade.py`
- исправлен typing-дефект в `EurikaOrchestrator.run`:
  - устранены `no-redef` и `"None" not callable` в lazy-import ветке.
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 7 модулей orchestration/entry boundary.

### Проверка
- `mypy` по 7 модулям:
  - `prepare`, `apply_stage`, `fix_cycle_impl`, `hybrid_approval`, `full_cycle`, `facade`, `orchestrator`
  - результат: `Success: no issues found in 7 source files`
- regression-check:
  - `tests/test_hitl_cli.py` — green
  - `tests/test_cycle.py -k "run_full_cycle_wrapper_delegates_to_orchestration_module or full_cycle_propagates_doctor_runtime_to_fix_report or fix_cycle_approve_ops_selects_subset or fix_cycle_approve_ops_reject_ops_conflict"` — green

### Итог
- typing-contract gate расширен на полный orchestration entry path без изменения runtime-поведения.

---

## 45. Snapshot (2026-02-23) — R3 Typing contract step 2 (HITL + orchestrator adapters)

### Scope
- расширен typing-gate на соседний orchestration-слой:
  - `cli/orchestration/hybrid_approval.py`
  - `cli/orchestrator.py`
- `hybrid_approval` переведён на контракт `OperationRecord`, устранён no-redef паттерн для `approved/rejected`.
- `orchestrator`-адаптер синхронизирован по типам с `PatchPlan`/`OperationRecord`/`FixCycleDeps`.
- `pyproject.toml` (`tool.mypy.overrides`) расширен до 5 модулей orchestration boundary.

### Проверка
- `mypy`:
  - `cli/orchestration/prepare.py`
  - `cli/orchestration/apply_stage.py`
  - `cli/orchestration/fix_cycle_impl.py`
  - `cli/orchestration/hybrid_approval.py`
  - `cli/orchestrator.py`
  - результат: `Success: no issues found in 5 source files`
- `pytest -q tests/test_hitl_cli.py` → `6 passed`

### Итог
- typing-contract gate расширен на HITL и compatibility-адаптер без изменения runtime-семантики approve/reject flow.

---

## 44. Snapshot (2026-02-23) — R3 Typing contract kickoff (orchestration boundary)

### Scope
- старт целевого typing-гейта для критичного fix-контура:
  - `cli/orchestration/prepare.py`
  - `cli/orchestration/apply_stage.py`
  - `cli/orchestration/fix_cycle_impl.py`
- добавлен модуль контрактов `cli/orchestration/contracts.py` (пограничные алиасы + typed payloads для decision/telemetry/safety).
- в `pyproject.toml` добавлен optional extra `typecheck` (`mypy`) и базовая конфигурация `tool.mypy` для постепенного включения typecheck.

### Проверка
- `mypy` по целевым модулям: `Success: no issues found in 3 source files`.
- regression-check:
  - `tests/test_agent_handlers_decision_summary.py` — green
  - `tests/test_campaign_flow.py` — green
  - `tests/test_cycle.py -k "attach_fix_telemetry_counts_campaign_session_skips or attach_fix_telemetry_median_verify_time"` — green

### Итог
- включён узкий typing-contract gate на boundary fix-orchestration без изменения runtime-поведения.

---

## 43. Snapshot (2026-02-23) — QG-4 ritual confirmation (apply-safe + no-op)

### Сценарий A (apply-safe e2e, mini-project)
- подготовлен временный проект `.tmp_qg4_apply` (`a.py` + `tests/test_a.py`).
- `../.venv/bin/python -m eurika_cli scan .tmp_qg4_apply`
- `../.venv/bin/python -m eurika_cli fix .tmp_qg4_apply --quiet`
- `../.venv/bin/python -m eurika_cli campaign-undo .tmp_qg4_apply --checkpoint-id 20260223_113847_517`

### Результат A
- `fix`: `modified_count=1`, `apply_rate=1.0`, `no_op_rate=0.0`, `rollback_rate=0.0`.
- verify: `1 passed`; `verify_required=true`, `verify_ran=true`, `verify_passed=true`.
- checkpoint: `checkpoint_id=20260223_113847_517`, `status=completed`, `run_ids=["20260223_083847"]`.
- `campaign-undo`: `status=undone`, `restored=["a.py"]`, `errors=[]`.

### Сценарий B (no-op e2e, основной проект)
- `../.venv/bin/python -m eurika_cli scan .`
- `../.venv/bin/python -m eurika_cli doctor . --no-llm`
- `../.venv/bin/python -m eurika_cli fix . --dry-run --quiet`

### Результат B
- `eurika_fix_report`: `message="Patch plan has no operations. Cycle complete."`
- telemetry: `operations_total=1`, `modified_count=0`, `skipped_count=1`, `apply_rate=0.0`, `no_op_rate=1.0`, `rollback_rate=0.0`.
- safety gates: `verify_required=false`, `verify_ran=false`, `rollback_done=false`.
- campaign memory: `campaign_skipped=1` по рискованной цели, apply-stage не запускался (ожидаемое no-op поведение).

### Итог
- QG-4 подтверждён: и apply-safe путь (apply + verify + campaign-undo), и no-op путь отрабатывают предсказуемо и детерминированно.

---

## 42. Snapshot (2026-02-23) — QG-1/QG-2 closeout for 3.6.4

### QG-1 (edge-case hardening)
- `campaign-undo` для битого checkpoint payload теперь возвращает явную ошибку (`Invalid checkpoint payload`).
- повторный `campaign-undo` по already-undone checkpoint сделан идемпотентным (`already_undone=true`, без повторного rollback).
- добавлены тесты на missing checkpoint id, invalid payload, repeated undo, mixed rollback errors.

### QG-2 (integrated flow)
- добавлен интеграционный тест `tests/test_campaign_flow.py`:
  - `fix --approve-ops 1` (частичный apply),
  - проверка `decision_summary.blocked_by_human` и `not_in_approved_set`,
  - проверка `campaign_checkpoint` (`checkpoint_id`, `run_ids`),
  - `campaign-undo --checkpoint-id ...` и восстановление изменённого файла.

### Проверка
- `tests/test_campaign_checkpoint.py` — edge-cases green
- `tests/test_campaign_flow.py` + related suites (`test_agent_handlers_decision_summary`) — green

### Итог
- quality-gate для контура `decision gate + checkpoint + campaign-undo` закрыт на интеграционном уровне.

---

## 41. Snapshot (2026-02-23) — DoD 3.6 baseline (3 ritual runs)

### Сценарий
- 3 последовательных прогона: `scan -> doctor --no-llm -> fix --dry-run --quiet`

### Метрики по прогонам
| run | apply_rate | no_op_rate | rollback_rate | verify_required | blocked policy/critic/human | doctor apply_rate | doctor rollback_rate | doctor median_verify_time_ms |
|-----|------------|------------|---------------|-----------------|------------------------------|-------------------|----------------------|------------------------------|
| 1 | 0.0 | 1.0 | 0.0 | false | 0 / 0 / 0 | 0.3576 | 0.7 | 96430 |
| 2 | 0.0 | 1.0 | 0.0 | false | 0 / 0 / 0 | 0.3576 | 0.7 | 96430 |
| 3 | 0.0 | 1.0 | 0.0 | false | 0 / 0 / 0 | 0.3576 | 0.7 | 96430 |

### Вывод
- baseline стабилен и предсказуем: no-op сценарий повторяется без новых регрессий.
- risky target по `eurika/agent/tool_contract.py` последовательно отсекается campaign-memory, verify stage не запускается (ожидаемое поведение для no-op).

---

## 40. Snapshot (2026-02-23) — Sprint 3.6.4 e2e: checkpoint -> campaign-undo

### Сценарий (безопасный mini-project)
- создан временный проект `.tmp_campaign_demo` с `a.py` (unused import) и `tests/test_a.py`.
- `eurika scan .tmp_campaign_demo`
- `eurika fix .tmp_campaign_demo --quiet` (apply + verify)
- `eurika campaign-undo .tmp_campaign_demo --list`
- `eurika campaign-undo .tmp_campaign_demo --checkpoint-id <id>`

### Результат
- fix применил `remove_unused_import` для `a.py`; verify: `1 passed`.
- в `eurika_fix_report.json` зафиксирован `campaign_checkpoint`:
  - `checkpoint_id=20260223_004858_306`
  - `status=completed`
  - `run_ids=["20260222_214858"]`
- `campaign-undo --list` показал checkpoint со статусом `completed`, после undo — `status=undone`.
- после `campaign-undo` файл `a.py` восстановлен из backup (`import os` вернулся).

### Итог
- Контур Sprint 3.6.4 подтверждён end-to-end: checkpoint создаётся до apply, связывается с run_id, и откат кампании одним действием работает предсказуемо.

---

## 39. Snapshot (2026-02-22) — ritual check after Sprint 3 push

### Команды
- `eurika scan .`
- `eurika doctor . --no-llm`
- `eurika fix . --dry-run` / no-op fix-path

### Результат
- `eurika_fix_report.json`: `message="Patch plan has no operations. Cycle complete."`
- telemetry: `operations_total=1`, `modified_count=0`, `skipped_count=1`, `apply_rate=0.0`, `no_op_rate=1.0`, `rollback_rate=0.0`
- safety_gates: `verify_required=false`, `verify_ran=false`, `rollback_done=false`
- `eurika_doctor_report.json`: риск стабилен (`risk_score=46`), `smells=stable`, `regressions=[]`

### Проверка Sprint 3.6.4 в ритуале
- risky op по `eurika/agent/tool_contract.py` снова отсечён campaign-memory (`campaign_skipped=1`) — ожидаемо.
- checkpoint кампании в этом прогоне не создаётся, так как apply-stage не запускался (нет executable ops) — поведение корректное для no-op ритуала.

---

## 38. Snapshot (2026-02-22) — 3.6.3 closed: context visibility + context effect

### Изменения
- **UI Dashboard / Context sources:** добавлена карточка с агрегатами (`targets with context`, `recent verify-fail`, `campaign rejected`, `recent patch-modified`).
- **Top context hits:** в UI отображаются top-3 `context_hits` по текущим операциям для объяснения приоритизации.
- **By-target breakdown:** в UI добавлен компактный блок `target -> related_tests / neighbor_modules / hits`.
- **CYCLE_REPORT effect:** `report-snapshot` теперь пишет блок `2.1 Context effect (ROADMAP 3.6.3)` с `apply_rate/no_op_rate` (current vs baseline, delta in pp).

### Тесты
- `tests/test_cycle.py::test_report_snapshot_context_effect_block`
- `tests/test_cycle.py::test_report_snapshot_telemetry_block`

### Проверка
- `../.venv/bin/python -m pytest -q tests/test_cycle.py -k "report_snapshot_telemetry_block or report_snapshot_context_effect_block"` → `2 passed`

---

## 37. Snapshot (2026-02-22) — v3.0.9: runtime robustness (state + degraded visibility)

### Изменения
- **R2 state-модель runtime:** `AgentCycleResult` теперь фиксирует `state` и `state_history` (`idle -> thinking -> done|error`).
- **Детерминированные переходы:** `run_agent_cycle` переводит состояние в `error` при сбое стадии и в `done` при успешном завершении.
- **Doctor degraded metadata:** `run_doctor_cycle` добавляет `runtime` блок (`degraded_mode`, `degraded_reasons`, `llm_used`, `use_llm`).
- **Fix/Cycle degraded metadata:** для non-assist и full-cycle `report.runtime` теперь содержит причины деградации/fallback.

### Тесты
- runtime: `test_run_agent_cycle_state_transitions_success`, `test_run_agent_cycle_state_transitions_error`
- doctor: `test_doctor_runtime_reports_degraded_mode_when_llm_disabled`
- cycle/fix: `test_run_cycle_non_assist_adds_runtime_block_to_report`, `test_full_cycle_propagates_doctor_runtime_to_fix_report`

### Проверка
- `tests/test_agent_runtime.py tests/test_cli_runtime_mode.py tests/test_cycle.py` — green.

---

## 36. Snapshot (2026-02-21) — v3.0.8: long_function extract_block fallback

### Изменения
- **long_function без вложенных def:** fallback на suggest_extract_block (if/for/while 5+ строк) когда extract_nested_function не срабатывает.
- extract_block работает даже при allow_extract_nested=False (learning блокирует только extract_nested).
- fixed_locations предотвращает дубли extract_block для одной функции с long_function и deep_nesting.

---

## 35. Snapshot (2026-02-21) — v3.0.8: god_class WEAK, deep_nesting extract_block

### Изменения (CHANGELOG v3.0.8)
- **god_class|extract_class** в WEAK_SMELL_ACTION_PAIRS; EXTRACT_CLASS_SKIP_PATTERNS (*tool_contract*.py) — защита от повторения #34
- **deep_nesting** — suggest_extract_block, extract_block_to_helper; EURIKA_DEEP_NESTING_MODE=hybrid

### report-snapshot . (текущее состояние)

| Блок | Значение |
|------|----------|
| **Doctor** | 204 модулей, Risk 46/100, apply_rate 0.358 |
| **Learning** | god_class\|extract_class 1/2; deep_nesting\|refactor_code_smell 0% (теперь есть extract_block_to_helper) |

---

## 34. Fix rollback (2026-02-22) — extract_class на tool_contract провалил verify

### Что произошло
`eurika fix .` из UI применил extract_class к `eurika/agent/tool_contract.py` (DefaultToolContract). Созданы файлы:
- `tool_contract_defaulttoolcontractextracted.py` — сломанный код (undefined `kwargs`, `dry_run`, `_ok`/`_err`)
- `tool_contract_defaulttoolcontract.py` — обёртка

verify failed (pytest), auto_rollback не восстановил оригинал полностью (backup был перезаписан второй операцией).

### Исправление
1. `eurika agent patch-rollback --run-id 20260221_221321 .` — восстановлен tool_contract.py из backup
2. `git restore eurika/agent/tool_contract.py` — полное восстановление из git
3. Удалены созданные файлы: `tool_contract_defaulttoolcontract.py`, `tool_contract_defaulttoolcontractextracted.py`

### Итог
- 319 tests passed
- extract_class для god_class нуждается в доработке: при извлечении статических методов теряются параметры и хелперы

---

## 33. Fix (2026-02-21) — eurika fix . после dry-run

### Команда
`eurika fix .` (assist mode)

### Результат

| Поле | Значение |
|------|----------|
| **modified** | 7 |
| **skipped** | 0 |
| **verify** | ✓ passed |

### Операции
- 4× remove_unused_import: cli/orchestrator_run_doctor_cycle.py, eurika/api/chat_intent.py, tests/test_chat_intent.py, tests/test_chat_rag.py
- 3× refactor_code_smell (TODO): cli/wiring/dispatch.py (long_function), eurika/api/chat.py (long_function), eurika/api/chat_rag.py (deep_nesting)

### telemetry
apply_rate=1.0, no_op_rate=0.0, rollback_rate=0.0, verify_duration_ms=58098

### verify_metrics
before_score=46, after_score=46

### Итог
- 7 файлов изменены, verify ✓
- Learning: +4 success remove_unused_import, +3 success refactor_code_smell (TODO-маркеры)

---

## 32. Snapshot (2026-02-21) — ритуал 2.1, после багфикса knowledge/base.py

### Команда
`eurika scan .` → `eurika doctor . --no-llm` → `eurika report-snapshot .`

### Багфикс
- `eurika/knowledge/base.py`: SyntaxError — закрыта скобка `}` для dict `meta` (строка 402)

### 1. Fix (последний прогон из events)

| Поле | Значение |
|------|----------|
| **modified** | 382 (curated_repos) / 3 (локальные) |
| **skipped** | 16 |
| **verify** | mixed |

### 2. Doctor (`eurika_doctor_report.json`)

| Метрика | Значение |
|---------|----------|
| **Модули** | 200 |
| **Зависимости** | 108 |
| **Risk score** | 33/100 |
| **apply_rate** (last 10) | 0.3542 |
| **median_verify_time** | 131199 ms |

### 3. Learning

**by_action_kind**
- refactor_code_smell: 0 success, 1045 fail (0%)
- split_module: 4 success, 4 fail (50%)
- remove_unused_import: 10 success, 40 fail (20%)

**by_smell_action**
- long_function|refactor_code_smell: total=881, success=0, fail=860
- god_module|split_module: total=8, success=4, fail=4
- unknown|remove_unused_import: total=50, success=10, fail=40

### Итог
- Ритуал 2.1 выполнен; doctor падал на SyntaxError в knowledge/base.py — исправлено
- Risk score 33/100; модули 200 (+13 vs §31)
- refactor_code_smell 0% (WEAK_SMELL_ACTION_PAIRS)

---

## 31. Snapshot (2026-02-21) — ритуал 2.1, после B (продуктовая готовность) + 3.5.11.A Chat

### Команда
`eurika report-snapshot .`

### 1. Fix (`eurika fix .`)

| Поле | Значение |
|------|----------|
| **modified** | 3 |
| **skipped** | 0 |
| **verify** | True |

### verify_metrics: before=46, after=46

### telemetry (ROADMAP 2.7.8)
apply_rate=1.0, no_op_rate=0.0, rollback_rate=0.0, verify_duration_ms=123701, median_verify_time_ms=123701

### 2. Doctor (`eurika_doctor_report.json`)

| Метрика | Значение |
|---------|----------|
| **Модули** | 187 |
| **Зависимости** | 107 |
| **Risk score** | 46/100 |

### 3. Learning

### by_action_kind
- refactor_code_smell: 0 success, 7 fail (0%)
- split_module: 4 success, 1 fail (80%)
- remove_unused_import: 10 success, 3 fail (77%)

### by_smell_action
- long_function|refactor_code_smell: total=28, success=0, fail=7
- deep_nesting|refactor_code_smell: total=2, success=0, fail=0
- god_module|split_module: total=5, success=4, fail=1
- unknown|remove_unused_import: total=13, success=10, fail=3

### Итог
- Ритуал 2.1 выполнен после направления B (продуктовая готовность) и 3.5.11.A (Chat)
- Risk score 46/100, apply-rate=1.0
- refactor_code_smell по-прежнему 0% (WEAK_SMELL_ACTION_PAIRS)

---

## 30. Snapshot (2026-02-21) — report-snapshot via Web UI (ритуал 2.1)

### Команда
`eurika report-snapshot .` (через Terminal tab Web UI)

### 1. Fix (`eurika fix .`)

| Поле | Значение |
|------|----------|
| **modified** | 3 |
| **skipped** | 0 |
| **verify** | True |

### verify_metrics
- before_score=46, after_score=46

### telemetry (ROADMAP 2.7.8)
- apply_rate=1.0, no_op_rate=0.0, rollback_rate=0
- verify_duration_ms=123701, median_verify_time_ms=123701

### 2. Doctor (`eurika_doctor_report.json`)

| Метрика | Значение |
|---------|----------|
| **Модули** | 187 |
| **Зависимости** | 107 |
| **Risk score** | 46/100 |

### 3. Learning

**by_action_kind**
- refactor_code_smell: 0 success, 7 fail (0%)
- split_module: 4 success, 1 fail (80%)
- remove_unused_import: 10 success, 3 fail (77%)

**by_smell_action**
- long_function|refactor_code_smell: total=28, success=0, fail=7
- deep_nesting|refactor_code_smell: total=2, success=0, fail=0
- god_module|split_module: total=5, success=4, fail=1
- unknown|remove_unused_import: total=13, success=10, fail=3

### Итог
- Ритуал 2.1: report-snapshot выполнен через Web UI
- Risk score стабилен (46/100), apply-rate=1.0

---

## 20. Dogfooding cycle 2026-02-20 (ROADMAP 2.7.9)

### Команда
`eurika cycle .` (assist mode, с LLM fallback)

### Fix результат
| Поле | Значение |
|------|----------|
| **modified** | 7 |
| **skipped** | 0 |
| **verify** | success |
| **tests** | 258 passed (37.03s) |
| **rollback** | нет |

### Операции применены
- 3× refactor_code_smell (TODO long_function: handle_report_snapshot, prepare_fix_cycle_operations, handle_non_default_kind)
- 2× remove_unused_import (architecture_planner_build_patch_plan, tests/test_hitl_cli)
- 1× split_module (architecture_planner → architecture_planner_build_plan)

### Telemetry (ROADMAP 2.7.8)
- apply_rate=1.17, no_op_rate=0, rollback_rate=0
- verify_duration_ms=37582, median_verify_time_ms=19497

### Rescan
- modules_added: architecture_planner_build_plan.py
- verify_metrics: before_score=46, after_score=46
- architecture_planner.py: fan_out 2→3

### Learning (по циклу)
| action | success | fail | rate |
|--------|---------|------|------|
| split_module | 22 | 11 | 67% |
| extract_class | 5 | 2 | 71% |
| remove_unused_import | 4 | 4 | 50% |
| refactor_code_smell | 0 | 76 | 0% |

### Итог
- Verify passed, rollback не потребовался
- architecture_planner — фасад: build_plan в architecture_planner_build_plan, build_patch_plan в architecture_planner_build_patch_plan
- Цикл 1/3 для DoD 2.7.9

---

## 21. Dogfooding cycle 2 — 2026-02-20

### Fix результат
| Поле | Значение |
|------|----------|
| **modified** | 2 |
| **skipped** | 0 |
| **verify** | success |
| **tests** | 258 passed (33.38s) |
| **rollback** | нет |

### Операции применены
- 2× remove_unused_import (architecture_planner.py, architecture_planner_build_action_plan.py)
- 1× split_module (architecture_planner → build_action_plan в architecture_planner_build_action_plan.py)

### Telemetry
- apply_rate=0.67, no_op_rate=0, rollback_rate=0
- verify_duration_ms=33846, median_verify_time_ms=34229

### Rescan
- verify_metrics: before_score=46, after_score=46
- architecture_planner.py: fan_out 4→3; action_plan.py: fan_in 8→7

### Итог
- verify passed, rollback не потребовался
- Цикл 2/3 для DoD 2.7.9

---

## 22. Dogfooding cycle 3 — 2026-02-20

### Fix результат
| Поле | Значение |
|------|----------|
| **modified** | 0 или минимально |
| **verify** | success |
| **rollback** | нет |

### Learning (после 3 циклов)
| action | success | fail | rate |
|--------|---------|------|------|
| split_module | 19 | 6 | **76%** |
| extract_class | 4 | 1 | **80%** |
| remove_unused_import | 8 | 3 | **73%** |
| refactor_code_smell | 0 | 41 | 0% |

### Итог
- 3 стабильных цикла подряд ✓
- DoD 2.7.9 выполнен

---

## 23. Policy update: refactor_code_smell в WEAK_SMELL_ACTION_PAIRS (2026-02-20)

### Обоснование
- Learning: `refactor_code_smell` — 0% success (0/41), только TODO-маркеры
- `long_function|refactor_code_smell` и `deep_nesting|refactor_code_smell` добавлены в `WEAK_SMELL_ACTION_PAIRS`

### Поведение
- **hybrid:** требуют manual approval (review)
- **auto:** блокируются (deny)
- **assist:** без изменений (все ops apply)
- Деприоритизация: слабые пары в конце плана, первыми отсекаются при max_ops

### Файл
`eurika/agent/policy.py` — WEAK_SMELL_ACTION_PAIRS

---

## 24. Dogfooding 2.9 — 3 цикла с LLM + Knowledge (ROADMAP 2.9.5)

### Команда
`eurika cycle . --apply-suggested-policy`

### Результат
- 3 стабильных цикла подряд
- verify ✓ passed
- apply-rate, rollback-rate стабильны
- architect даёт рекомендации «как»; suggested policy при низком apply_rate

### DoD 2.9.5
- [x] apply-rate не падает
- [x] релевантность рекомендаций (Recommendation block, Reference block)
- [x] learning: suggested policy из telemetry

---

## 1. Fix (`eurika fix . --quiet --no-code-smells`) — 2026-02-19

| Поле | Значение |
|------|----------|
| **modified** | 0 |
| **skipped** | 0 |
| **errors** | 0 |
| **verify** | success |
| **tests** | 188 passed in ~28s |

### Skipped — причины (`skipped_reasons`)

- Нет (`patch plan has no operations`).

### Rescan diff

- **Модули:** 139, без изменений
- **Smells:** bottleneck 4, god_module 7, hub 9
- **Maturity:** low
- **verify_metrics:** success=true, before=46, after=46

---

## 2. Doctor (`eurika_doctor_report.json`)

| Метрика | Значение |
|---------|----------|
| **Модули** | 139 |
| **Зависимости** | 91 |
| **Циклы** | 0 |
| **Maturity** | low |
| **Risk score** | 46/100 |

### Центральные модули

- project_graph_api.py (fan-in 10, fan-out 1)
- patch_engine.py (fan-in 6, fan-out 5)
- patch_apply.py (fan-in 10, fan-out 0)

### Риски

- god_module @ patch_engine.py (severity 11.00), patch_apply.py (10.00), code_awareness.py (9.00), agent_core.py (7.00)
- bottleneck @ patch_apply.py (10.00)

### Architect

- **LLM:** fallback на template (`Connection error` при попытке LLM).

### Planned refactorings

- 0 ops (`patch_plan.operations=[]`).

---

## 3. Learning (`agent learning-summary`)

### По виду операции (`by_action_kind`)

| action | total | success | fail | rate |
|--------|-------|---------|------|------|
| remove_unused_import | 20 | 16 | 4 | 80% |
| split_module | 120 | 74 | 46 | 62% |
| introduce_facade | 4 | 2 | 2 | 50% |
| extract_class | 16 | 10 | 6 | 62% |
| refactor_code_smell | 411 | 241 | 170 | 59% |
| extract_nested_function | 1 | 0 | 1 | 0% |

### По smell+action

| smell\|action | total | success | fail |
|---------------|-------|---------|------|
| god_module\|split_module | 117 | 74 | 43 |
| long_function\|refactor_code_smell | 284 | 167 | 117 |
| deep_nesting\|refactor_code_smell | 127 | 74 | 53 |
| hub\|split_module | 3 | 0 | 3 |
| long_function\|extract_nested_function | 1 | 0 | 1 |

---

## 4. Recent events (patch/learn, из doctor context)

| type | modified | success |
|------|----------|---------|
| patch | 1 file | True |
| learn | [cli/orchestrator.py] | True |
| patch | 0 files | True |
| patch | 1 file | True |
| learn | [eurika/api/__init__.py] | True |

---

## 5. Итог

- **Verify:** 188 тестов прошли
- **Изменений в контрольном fix:** 0
- **Skip-шум устранён:** стабильная причина `extract_class: extracted file exists` больше не воспроизводится
- **Система стабильна:** score 46, регрессий нет
- **Фокус дальше:** повышать долю реальных apply и улучшать fallback-policy для слабых пар learning

---

## 6. Рефактор `eurika/reasoning/architect.py`

- Разбит `long_function` в `_template_interpret` и `_llm_interpret` на helper-функции.
- Поведение сохранено: LLM fallback и шаблонная интерпретация без функциональных изменений.
- Проверка: `pytest -q tests/test_architect.py` → `6 passed`.

---

## 7. LLM Fallback (OpenRouter -> Ollama)

- Добавлена цепочка провайдеров в `architect`: сначала `OPENAI_*` (OpenRouter), при ошибке — локальный Ollama (`OLLAMA_OPENAI_*` или дефолт `http://127.0.0.1:11434/v1`, `qwen2.5:1.5b`).
- Обновлены тесты на контракт dry-run и fallback-поведение:
  - `pytest -q tests/test_architect.py tests/test_cycle.py` → `22 passed`.
- Контрольный `eurika cycle .` после фикса тестов: `verify=true`, `189 passed`.
- Operational note: если в shell уже экспортированы `OPENAI_*`, они имеют приоритет над `.env` (из-за `load_dotenv(..., override=False)`), поэтому для принудительного локального сценария нужен `unset OPENAI_API_KEY OPENAI_MODEL OPENAI_BASE_URL`.

---

## 8. Контрольный прогон (после env-priority и no-op prefilter)

- `eurika doctor .`:
  - system: `modules=140`, `dependencies=92`, `cycles=0`
  - risk score: `43/100` (было 46)
  - trends: `complexity=increasing`, `smells=stable`, `centralization=stable`
  - patch_plan: `operations=[]`
- `eurika fix . --no-code-smells --quiet`:
  - `{"message":"Patch plan has no operations. Cycle complete."}`
- LLM в данном runtime окружении агента: не достигнут ни primary, ни fallback
  (`primary LLM failed (Connection error.); ollama fallback failed (Connection error.)`).
  В пользовательском терминале локальный Ollama ранее подтверждён рабочим (`doctor` с содержательным LLM-ответом).

---

## 9. Sprint 4 update (Safety gates + KPI telemetry)

### Реализовано

- В `eurika_fix_report.json` добавлены KPI:
  - `telemetry.operations_total`
  - `telemetry.modified_count`
  - `telemetry.skipped_count`
  - `telemetry.apply_rate`
  - `telemetry.no_op_rate`
  - `telemetry.rollback_rate`
  - `telemetry.verify_duration_ms`
- Добавлен блок guardrails:
  - `safety_gates.verify_required`
  - `safety_gates.auto_rollback_enabled`
  - `safety_gates.verify_ran`
  - `safety_gates.verify_passed`
  - `safety_gates.rollback_done`
- Для rollback-ветки фиксируется `rollback.trigger = "verify_failed"`.
- Telemetry/safety теперь формируются не только в apply-ветке, но и в edge-cases:
  - `patch plan has no operations`
  - `all operations rejected by user/policy`
  - `dry-run`.

### Проверка

- Прогон через venv:
  - `"/mnt/sdb2/project/.venv/bin/python" -m pytest -q tests/test_cycle.py tests/test_patch_engine.py tests/test_architect.py`
  - Результат: `42 passed`.
- Добавлен тест на edge-case полного отклонения операций в hybrid (`telemetry + no verify gate`).

### Ollama runtime policy (обновление)

- Автозапуск/перезапуск `ollama serve` из Eurika отключён.
- При недоступности daemon возвращается явная инструкция запустить `ollama serve` вручную.
- Дефолт fallback-модели Ollama переключен на coding-профиль:
  - `OLLAMA_OPENAI_MODEL=qwen2.5-coder:7b`.

---

## 10. Контрольный baseline после Sprint 4

### Прогоны (через venv)

- `"/mnt/sdb2/project/.venv/bin/python" -m eurika_cli doctor .`
- `"/mnt/sdb2/project/.venv/bin/python" -m eurika_cli fix . --dry-run --quiet`
- `"/mnt/sdb2/project/.venv/bin/python" -c "... run_cycle(..., mode='fix', dry_run=True, quiet=True) ..."`

### Doctor snapshot

- system: `modules=151`, `dependencies=93`, `cycles=0`
- risk score: `46/100` (Δ0 по окну)
- trends: `complexity=stable`, `smells=stable`, `centralization=stable`
- patch plan from doctor: `operations=[]`
- LLM status в этом запуске: template fallback, причина:
  - `ollama CLI fallback failed (could not connect to ollama server; start it manually with ollama serve)`

### Fix dry-run snapshot (runtime assist)

- patch plan operations: `1`
  - `refactor_code_smell` для `eurika/agent/policy.py:evaluate_operation` (`deep_nesting`, risk=`medium`)
- telemetry:
  - `operations_total=1`
  - `modified_count=0`
  - `skipped_count=0`
  - `apply_rate=0.0`
  - `no_op_rate=0.0`
  - `rollback_rate=0.0`
  - `verify_duration_ms=0`
- safety_gates:
  - `verify_required=false`
  - `auto_rollback_enabled=false`
  - `verify_ran=false`
  - `verify_passed=null`
  - `rollback_done=false`

---

## 11. Orchestrator Split progress (ROADMAP 2.8.3 a-d + facade thinning)

### До/после по фасаду

- `cli/orchestrator.py`: **798 → 383 LOC** (фасад значительно истончен).
- Вынесено в слой `cli/orchestration/`:
  - `prepare.py` — pre-stage (scan/diagnose/plan/policy/session-filter), **217 LOC**
  - `apply_stage.py` — apply/verify/rescan/report/memory/telemetry, **223 LOC**
  - `doctor.py` — doctor-cycle wiring + knowledge topics, **69 LOC**
  - `full_cycle.py` — full-cycle wiring, **58 LOC**

### Что сохранено по контракту

- Публичные точки входа (`run_cycle`, `run_doctor_cycle`, `run_fix_cycle`, `run_full_cycle`) не менялись.
- Тестируемые shim-точки в `cli/orchestrator.py` оставлены там, где это требуется для patch-моков.
- Формат `eurika_fix_report.json` и поля `telemetry/safety_gates/policy_decisions` сохранены.

### Проверка после декомпозиции

- `"/mnt/sdb2/project/.venv/bin/python" -m pytest -q tests/test_cycle.py tests/test_cli_runtime_mode.py tests/test_architect.py tests/test_patch_engine.py`
- Результат: **46 passed**.

---

## 12. CLI Wiring Split progress (ROADMAP 2.8.4, step 1-2)

### До/после по entrypoint

- `eurika_cli.py`: **633 → 59 LOC** (тонкий entrypoint: env-load + parser + dispatch call).
- Вынесено в `cli/wiring/`:
  - `parser.py` — регистрация subcommands и аргументов, **231 LOC**
  - `dispatch.py` — роутинг команд к handlers, **59 LOC**

### Что сохранено по контракту

- Синтаксис CLI и список флагов/команд сохранены 1:1.
- `eurika --version` и parser-контракт runtime-флагов (`--runtime-mode`, `--non-interactive`, `--session-id`) не изменены.
- `main()` в `eurika_cli.py` теперь только `parse -> dispatch`, без бизнес-логики.

### Проверка после декомпозиции

- `"/mnt/sdb2/project/.venv/bin/python" -m pytest -q tests/test_cli_runtime_mode.py tests/test_cycle.py`
- Результат: **25 passed**.

---

## 13. Planner Boundary progress (ROADMAP 2.8.5, safe split)

### До/после по facade-модулю

- `architecture_planner.py`: **497 -> 88 LOC** (тонкий facade: `build_plan`, `build_action_plan`, `build_patch_plan`).
- Вынесено в `eurika/reasoning/`:
  - `planner_types.py` — модели `PlanStep`/`ArchitecturePlan`, **38 LOC**
  - `planner_rules.py` — smell-action правила и env-фильтры, **92 LOC**
  - `planner_patch_ops.py` — сборка patch-операций и фильтры применимости, **460 LOC**
  - `planner_analysis.py` — индекс smells + сборка шагов плана, **77 LOC**
  - `planner_actions.py` — конвертация шагов в `ActionPlan`, **83 LOC**

### Что сохранено по контракту

- Внешний API `architecture_planner` сохранен: `build_plan`, `build_action_plan`, `build_patch_plan`.
- Семантика prefilter/fallback логики patch-планировщика не менялась; изменена только граница модулей.
- Форматы `PatchPlan` и `ActionPlan` не изменялись.

### Проверка после декомпозиции

- `python -m pytest tests/test_graph_ops.py -q`
- `python -m pytest tests/test_cycle.py -q`
- Результат: **49 passed** (28 + 21).

---

## 14. Patch Apply Boundary progress (ROADMAP 2.8.6, step 1)

### До/после по фасаду apply

- `patch_apply.py`: **489 -> 389 LOC** (сохранен API `apply_patch_plan`, `list_backups`, `restore_backup`).
- Вынесено в новый модуль:
  - `patch_apply_backup.py` — backup/restore и file-write helper-функции, **133 LOC**

### Что сохранено по контракту

- Поведение публичных функций `patch_apply` не менялось: внешние точки входа и формат отчетов те же.
- `list_backups`/`restore_backup` остались доступными из `patch_apply` как фасадные вызовы.
- Основная логика operation-kind обработки в `apply_patch_plan` сохранена без изменений.

### Проверка шага

- `python -m py_compile patch_apply.py patch_apply_backup.py`
- `ReadLints` по `patch_apply.py` и `patch_apply_backup.py` — без ошибок.

### Step 2: kind-dispatch extraction

- `patch_apply.py`: **389 -> 209 LOC** (тонкий orchestrator apply-цикла с fallback append-путем).
- Вынесено в новый модуль:
  - `patch_apply_handlers.py` — обработчики operation-kind (`create_module_stub`, `fix_import`, `split_module`, `extract_class`, и др.), **271 LOC**

### Проверка шага 2

- `python -m py_compile patch_apply.py patch_apply_handlers.py patch_apply_backup.py`
- `ReadLints` по `patch_apply.py`, `patch_apply_handlers.py`, `patch_apply_backup.py` — без ошибок.

### Step 3: patch_engine verify/rollback orchestration extraction

- `patch_engine_apply_and_verify.py`: **99 -> 67 LOC** (тонкий orchestrator apply+verify flow).
- Вынесено в новый модуль:
  - `patch_engine_apply_and_verify_helpers.py` — import-fix retry, `py_compile` fallback, auto-rollback flow, **108 LOC**

### Проверка шага 3

- `python -m py_compile patch_engine_apply_and_verify.py patch_engine_apply_and_verify_helpers.py`
- `ReadLints` по `patch_engine_apply_and_verify.py` и `patch_engine_apply_and_verify_helpers.py` — без ошибок.

### Step 4: patch_engine facade constant boundary

- `patch_engine.py` теперь реэкспортирует `BACKUP_DIR`, чтобы внешние слои не зависели напрямую от `patch_apply`.
- `cli/orchestration/deps.py` переключен на импорт `BACKUP_DIR` из `patch_engine` facade.

### Проверка шага 4

- `python -m py_compile patch_engine.py cli/orchestration/deps.py`
- `ReadLints` по `patch_engine.py` и `cli/orchestration/deps.py` — без ошибок.

---

## 15. Violation Audit progress (ROADMAP 2.8.7, iteration 1)

### Closed violations (before -> after)

- `cli/orchestration/deps.py` больше не импортирует `BACKUP_DIR` напрямую из `patch_apply`; зависимость переведена на `patch_engine` facade (`from patch_engine import BACKUP_DIR, ...`).
- `cli/agent_handlers.py` и `cli/agent_handlers_handle_agent_patch_apply.py` больше не вызывают `patch_apply.apply_patch_plan` напрямую; dry-run/apply маршруты переведены на `patch_engine` facade (`apply_patch_dry_run`, `apply_patch`).

### Current intentional/legacy boundaries (tracked)

- `patch_engine` по-прежнему использует `patch_apply` как execution backend (`apply_patch_plan`, `restore_backup`, `list_backups`) — это текущий совместимый контракт фасада patch-подсистемы.
- В `eurika/reasoning/` остаются legacy compatibility shims с wildcard-реэкспортами (`planner.py`, `heuristics.py`, `advisor.py`); они поддерживают обратную совместимость, но не соответствуют целевому strict-layer стилю.

### Next closure candidates

- Минимизировать wildcard-compat shims в `eurika/reasoning` до явных экспортов/алиасов.

## 16. Violation Audit progress (ROADMAP 2.8.7, iteration 2)

### Closed violations (before -> after)

- `eurika/reasoning/planner.py`: удалены wildcard-реэкспорты (`from ... import *`), введен явный facade-контракт через именованные импорты и `__all__`.
- `eurika/reasoning/heuristics.py`: удалены wildcard-реэкспорты (`from ... import *`), введен явный facade-контракт через именованные импорты и `__all__`.
- `eurika/reasoning/advisor.py`: удалены wildcard-реэкспорты (`from ... import *`), введен явный facade-контракт через именованные импорты и `__all__`.

### Compatibility contract

- Сохранена обратная совместимость по публичным сущностям фасадов (`build_*`, `Action*`, `Patch*`, `AgentCore`/`ArchReviewAgentCore`, `SimpleMemory`/`DummyReasoner`/`SimpleSelector` и др.) через явный экспорт.
- Изолирована поверхность API: внешние импорты получают стабильный список символов вместо неявного расширения через wildcard.

### Verification

- `python -m py_compile eurika/reasoning/planner.py eurika/reasoning/heuristics.py eurika/reasoning/advisor.py`
- `ReadLints` по обновленным файлам — без ошибок.

---

## 17. Dogfooding on New Boundaries (ROADMAP 2.8.8)

### Сценарий

- Проведен dogfooding-контур на декомпозированных границах (`doctor -> fix --dry-run -> fix`) после шагов 2.8.5-2.8.7.
- Контрольный apply-run: `run_id=20260220_095348` (`eurika_fix_report.json`).

### Контрольные метрики (из fix-report)

- `verify.success=true`, `returncode=0`
- `verify.stdout`: `214 passed in 31.36s`
- `telemetry.operations_total=8`
- `telemetry.modified_count=9`
- `telemetry.no_op_rate=0.0`
- `telemetry.rollback_rate=0.0`
- `telemetry.verify_duration_ms=31840`
- `safety_gates.verify_required=true`, `verify_ran=true`, `verify_passed=true`, `rollback_done=false`

### Stability / regression check

- Верификация после apply стабильна (падений verify нет).
- Rollback не потребовался (`rollback_rate=0.0`), safety-gates отработали штатно.
- По rescan-метрикам score без деградации (`before_score=46`, `after_score=46`).

### Вывод

- Шаг ROADMAP `2.8.8 Dogfooding on New Boundaries` считается закрытым: декомпозиция границ не ухудшила verify-стабильность и не вызвала всплеска rollback/no-op метрик в контрольном прогоне.

---

## 18. Layer Map progress (ROADMAP 2.8.1)

### Выполнено

- Добавлен раздел **§0 Layer Map** в `Architecture.md`:
  - Карта 6 слоёв (Infrastructure → Core → Analysis → Planning → Execution → Reporting)
  - Таблица allowed dependencies (no upward deps)
  - Маппинг модулей v2.7 по слоям
  - Anti-pattern examples (Analysis→Execution, Planning→Execution, cross-layer bypass)
  - Ссылка на 2.8.2 Dependency Guard для автоматической проверки
- Добавлена ссылка в `CLI.md` § Рекомендуемый цикл
- В `ROADMAP.md` шаг 2.8.1 отмечен как выполненный

---

## 19. Dependency Guard progress (ROADMAP 2.8.2)

### Выполнено

- Добавлен тест `tests/test_dependency_guard.py`:
  - Проверка запрещённых импортов по Architecture.md §0.4
  - Правила: CLI → patch_apply; architecture_planner* → patch_apply; eurika/smells/, eurika/analysis/, code_awareness, graph_analysis, semantic_architecture, system_topology → patch_apply, patch_engine
  - Исключены: tests/, __pycache__/, .eurika_backups/, _shelved/
  - Парсинг через `ast`; вывод нарушений в assertion
- Обновлены Architecture.md §0.5 и ROADMAP.md (2.8.2 помечен как выполнено)

---

## 23. API Boundaries (ROADMAP 3.1-arch.2)

### Выполнено

- Добавлен `__all__` в ключевые модули:
  - `patch_engine`: apply_patch, verify_patch, rollback_patch, apply_and_verify, rollback, list_backups, apply_patch_dry_run, BACKUP_DIR
  - `eurika.core`, `eurika.analysis`, `eurika.smells`, `eurika.evolution`, `eurika.reporting`: публичные подмодули
- Добавлен раздел **§0.6 API Boundaries** в `Architecture.md`:
  - Таблица подсистем → публичные точки входа
  - Список пакетов с `__all__`

---

## 24. CLI thinning (ROADMAP 3.1-arch.5)

### Выполнено

- **report/report_snapshot.py** — format_report_snapshot(path) → str; логика форматирования вынесена из handle_report_snapshot
- **eurika.api** — explain_module(path, module_arg, window), get_suggest_plan_text(path, window), clean_imports_scan_apply(path, apply)
- **Тонкие handlers**: handle_report_snapshot, handle_explain, handle_suggest_plan, handle_clean_imports — только валидация args и вызов API
- **test_handle_report_snapshot_delegates_to_format** — тест на изоляцию (патч format_report_snapshot)

---

## 25. Planning–Execution split (ROADMAP 3.1-arch.6)

### Выполнено

- **eurika/reasoning/planner.py** — удалены apply_patch_plan, list_backups, restore_backup, ExecutorSandbox, ExecutionLogEntry; только planning types и build_*
- **Architecture.md §0.5** — Planner–Executor Contract: Planner выдаёт dict, Executor применяет; явный контракт
- **tests/test_dependency_guard.py** — правило eurika/reasoning/ → patch_apply, patch_engine запрещены

---

## 26. Domain vs presentation (ROADMAP 3.1-arch.4)

### Выполнено

- **report/architecture_report.py** — модуль presentation: render_full_architecture_report, _smells_to_text, _render_architecture_report_md
- **core/pipeline.py** — только domain (run_full_analysis, build_snapshot_from_self_map); render делегирует в report
- **system_topology.py** — central_modules_for_topology вынесена из architecture_pipeline (используется и domain, и presentation)

---

## 27. File size limits (ROADMAP 3.1-arch.3)

### Выполнено

- **eurika/checks/file_size.py** — check_file_size_limits(root), format_file_size_report(root); лимиты 400 (candidate) и 600 (must split)
- **handle_self_check** — выводит блок FILE SIZE LIMITS после scan
- **python -m eurika.checks.file_size [path]** — standalone run
- **tests/test_file_size_check.py** — 7 тестов

---

## 28. Dogfooding 3.1-arch (ROADMAP 3.1-arch.7) — 2026-02-21

### Команды

- `eurika fix .` (apply)
- 3× `eurika fix . --dry-run` (fixpoint check)

### Fix результат (apply run)

| Поле | Значение |
|------|----------|
| **modified** | 6 |
| **skipped** | 0 |
| **verify** | success |
| **tests** | 287 passed (138.14s) |
| **rollback** | нет |
| **run_id** | 20260221_092534 |

### Операции применены

- 3× remove_unused_import (architecture_pipeline.py, core/pipeline.py, tests/test_file_size_check.py)
- 3× refactor_code_smell (TODO long_function: handle_doctor, _render_architecture_report_md, format_report_snapshot)

### Dry-run × 3 (fixpoint)

| Прогон | operations_total | Результат |
|--------|------------------|-----------|
| 1 | 0 | Patch plan has no operations. Cycle complete. |
| 2 | 0 | Patch plan has no operations. Cycle complete. |
| 3 | 0 | Patch plan has no operations. Cycle complete. |

### Rescan / Architecture

- modules: 187, dependencies: 107, cycles: 0
- verify_metrics: before_score=46, after_score=46
- Health score: 46/100 (medium)

### Итог

- DoD 3.1-arch.7 выполнен: нет регресса, verify стабилен, fixpoint достигнут после 1 apply + 3 dry-run
- Policy: remove_unused_import allowed; refactor_code_smell (long_function) blocked in auto mode (WEAK_SMELL_ACTION_PAIRS)

---

## 29. Cycle v3.0.7 (2026-02-21)

### Команда

`eurika cycle .` (assist mode, после коммита v3.0.7)

### Fix результат

| Поле | Значение |
|------|----------|
| **modified** | 3 |
| **skipped** | 0 |
| **verify** | True |
| **tests** | 294 passed (123.19s) |
| **rollback** | нет |
| **run_id** | 20260221_131545 |

### Операции применены

- 3× refactor_code_smell (TODO long_function: run_doctor_cycle, _dispatch_api_get, aggregate_operational_metrics)
- Policy: long_function|refactor_code_smell в WEAK_SMELL_ACTION_PAIRS (deny в auto); в assist применились

### verify_metrics

- before_score=46, after_score=46

### telemetry (ROADMAP 2.7.8)

- apply_rate=1.0, no_op_rate=0.0, rollback_rate=0
- verify_duration_ms=123701, median_verify_time_ms=123701

### Doctor (eurika_doctor_report.json)

| Метрика | Значение |
|---------|----------|
| Модули | 187 |
| Зависимости | 107 |
| Risk score | 46/100 |

### Learning

**by_action_kind**

- refactor_code_smell: 0 success, 7 fail (0%)
- split_module: 4 success, 1 fail (80%)
- remove_unused_import: 10 success, 3 fail (77%)

**by_smell_action**

- long_function|refactor_code_smell: total=28, success=0, fail=7
- deep_nesting|refactor_code_smell: total=2, success=0, fail=0
- god_module|split_module: total=5, success=4, fail=1
- unknown|remove_unused_import: total=13, success=10, fail=3

### Итог

- Verify passed, rollback не потребовался
- v3.0.7: Web UI 3.5.6/3.5.7 (Approve tab, Graph), operational metrics, team mode, refactor serve._run_handler
