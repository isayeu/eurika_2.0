# Bounded Evolution — дисциплина роста

**Не технический шаг. Управленческий.** Спасает проект от расползания.

Eurika склонна к усложнению — это сила и риск. Bounded evolution — контролируемые пределы.

---

## 1. Лимиты на размер логов

| Артефакт | Лимит | Реализация |
|----------|-------|------------|
| EventLog | 500 событий | `eurika/storage/events.py` MAX_EVENTS=500; _save() хранит последние 500 |
| read limits | 5–200 | get_recent_failures(5), get_recent_failed_plan_hashes(10), get_kind_plan_failure_counts(20) |
| string truncation | 2000 chars | _json_safe() обрезает длинные строки в event payload |

**Запрет:** увеличивать MAX_EVENTS или read limits без обоснования в CYCLE_REPORT.

---

## 2. Лимиты на рост памяти

| Хранилище | Ограничение |
|-----------|-------------|
| events.json | MAX_EVENTS=500 (rolling window) |
| observations.json, history.json | Нет hard cap — мониторить размер |
| pattern_library.json | 30 entries per kind (extract_patterns_from_repos) |
| campaign_checkpoints | list_campaign_checkpoints(limit=20) |

**Рекомендация:** при observations/history > 10 MB — рассмотреть ротацию или pruning.

---

## 3. Лимиты на complexity planner'а

| Параметр | Лимит | Env / источник |
|----------|-------|----------------|
| max actions (planner output) | 20 | EURIKA_MAX_ACTIONS (default 20, 0=unlimited); RV7 |
| ops per fix cycle | 12 | EURIKA_MAX_OPS_PER_CYCLE (default 12, 0=unlimited) |
| effective cap | min(actions, ops) | planner caps at stricter of the two when both > 0 |
| MAX_PLAN_DEPTH | 3 | Reserved (future beam/multi-step planning) |
| BEAM_WIDTH | 5 | Reserved (future beam search) |
| Σ\|ΔE\| per cycle | 0 (off) | EURIKA_ENERGY_CAP (default 0, 0=disabled) |
| OSS hints per op | 3 | build_hints_and_params max_oss |
| DIFF_HINTS entries | фиксированный словарь | heuristics.py |
| fallback_kind mapping | явный словарь | heuristics.fallback_kind_for_low_success |

**Запрет:** добавлять неограниченные циклы, рекурсивные зависимости, ветвления без cap.

---

## 4. Запрет на крупные фичи без отчёта

**Правило:** фича считается крупной, если:
- новый модуль > 200 LOC
- изменение ≥ 3 файлов в разных подсистемах
- новый тип события/артефакта в storage
- новый smell type или action kind в planner

**Перед реализацией:** краткий отчёт в `docs/CYCLE_REPORT.md` или отдельный `docs/FEATURE_*.md`:
- цель
- затронутые области
- лимиты (если добавляются)
- критерий отката

**Агент:** при запросе на крупную фичу — напомнить про отчёт, не начинать без явного одобрения.

---

## 5. § Risks (Known Gaps)

Осознанные пробелы. Не реализовывать сейчас. Зафиксировать — значит превратить документ из "правил" в "управляемую эволюцию".

### 5.1 EventLog=500 — риск потери высокоценного контекста

При многих мелких событиях, разных проектах, learn+scan+patch — контекст может теряться раньше стабилизации learning.

**Потенциальное решение:** разделение high-value events (learn/patch приоритетнее scan); приоритетное сохранение.

### 5.2 Агрегаты без decay

Устаревшие статистики продолжают влиять на planner. Комбинации smell/action накапливаются.

**Идея:** age-based decay или recency weighting.

**Подготовка (2026-03):** в learning_stats добавлен `last_ts` (timestamp последнего события). Реализация decay — позже.

### 5.3 Поведенческая сложность planner

Формула scoring может расползтись (новые факторы, ветвления).

**Идея:** complexity cap — не более 5 факторов в итоговом score, каждый bounded [0..1], итог нормализован.

---

## 6. § CYCLE_REPORT Ritual

**Частота:** каждые 100 циклов (или configurable N).

**Минимальный чеклист:**

- success_rate (overall + last window)
- top_failure_reason
- most_deprioritized goal
- most successful action_kind
- memory size stats (events.json size, pattern_library size)
- **Был ли сдвиг поведения?** (Yes/No + краткий комментарий)

Ключевой пункт — последний. Если 3 отчёта подряд "No" → система не адаптируется.

---

## 7. EnergyModel как resource constraint (2026-03)

**Источник:** archive/EXECUTION_MODEL_PLAN, ROADMAP §5.7, review 2026 II.

| Аспект | Реализация |
|--------|------------|
| Scoring | Score = estimated_delta - risk; rank по delta (energy_ranking) |
| Ops cap | EURIKA_MAX_OPS_PER_CYCLE=12 |
| **Energy cap** | EURIKA_ENERGY_CAP: Σ\|ΔE\| за цикл ≤ cap. 0 = disabled. planner_patch_ops truncates по heuristic estimated_delta. |
| Delta в event | record_outcome(delta_energy=...); learn event |

**EURIKA_ENERGY_CAP:** при >0 план обрезается по накопленному |ΔE| (heuristic per smell|action). Пример: `EURIKA_ENERGY_CAP=0.3` — ~2–3 ops типа split_module (0.15 each).

---

## 8. Существующие лимиты (справочник)

- **File size:** 400 LOC (candidate), 600 LOC (must split) — `eurika/checks/file_size.py`
- **Weight adaptation:** bounded [0.02..0.25], EURIKA_WEIGHT_ADAPTATION=1
- **Learn-github:** --limit-repos, 100 files, 30 entries per kind

---

## Последовательность (историческая)

1. Обновить BOUNDED_EVOLUTION (risks + ritual) ✓
2. Запустить 300–500 циклов ✓ (100 выполнено, адаптация доказана; CYCLE_REPORT #123):
   ```bash
   .venv/bin/python scripts/run_cycle_batch.py . --max-cycles 500 --report-every 100
   ```
   С `--dry-run` — без apply; вывод каждые N циклов → вставить в CYCLE_REPORT.
3. Сформировать 3–5 CYCLE_REPORT ✓
4. Проверить: есть ли изменение поведения ✓ (Yes — success_rate, most_successful_action)
5. §5.7 — bounded evolution как часть execution model (целевой вектор зафиксирован в ROADMAP)

**Следующий фокус:** EnergyModel как resource constraint — контракт документирован в §7. Реализация — по мере пробелов. Decay агрегатов, high-value events — §5 Risks.

---

## 8. Саморазвитие: полигон → proposal → HITL (2026-09-03)

Architecture Freeze **не** означает «Eurika не трогает свой код». Запрещён только **тихий** rewrite боевого ядра и онлайн-патчинг без контроля.

**Разрешённый контур:**
1. Эксперимент в песочнице / `eurika/polygon/` / отдельном worktree (LLM + интернет для идей и проверки — ок).
2. Apply+verify только внутри полигона.
3. При удачном варианте — **предложить** патч человеку.
4. В основное дерево — только после явного разрешения (approve / reject).

**Ритуал v1:** `eurika prove-cycle . --propose [--drill imports|extractable_block|long_function|llm_extract]` → Approvals → `eurika fix . --apply-approved` (см. POLYGON_VERIFY_PLAYBOOK).

См. ROADMAP §4.6 (уточнение), Architecture.md §2, VISION.md C.14.

---

## Ссылки

- **ROADMAP.md** §4.6 / §5 — Architecture Freeze + Bounded evolution, EURIKA_MAX_OPS_PER_CYCLE
- **archive/review.md** §1 — bounded learning, границы эволюции
- **.eurika/rules/bounded-evolution.mdc** — правило для агента
