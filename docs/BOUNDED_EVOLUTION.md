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
| ops per fix cycle | 12 | EURIKA_MAX_OPS_PER_CYCLE (default 12, 0=unlimited) |
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

## 7. Существующие лимиты (справочник)

- **File size:** 400 LOC (candidate), 600 LOC (must split) — `eurika/checks/file_size.py`
- **Weight adaptation:** bounded [0.02..0.25], EURIKA_WEIGHT_ADAPTATION=1
- **Learn-github:** --limit-repos, 100 files, 30 entries per kind

---

## Последовательность

1. Обновить BOUNDED_EVOLUTION (risks + ritual) ✓
2. Запустить 300–500 циклов:
   ```bash
   .venv/bin/python scripts/run_cycle_batch.py . --max-cycles 500 --report-every 100
   ```
   С `--dry-run` — без apply; вывод каждые N циклов → вставить в CYCLE_REPORT.
3. Сформировать 3–5 CYCLE_REPORT
4. Проверить: есть ли изменение поведения
5. Только потом — §5.7 MetricVector / EnergyModel

**Не делать сейчас:** decay агрегатов, изменение EventLog лимита, усложнение scoring, добавление EnergyModel. Сначала доказательство адаптации.

---

## Ссылки

- **ROADMAP.md** §5 — Bounded evolution, EURIKA_MAX_OPS_PER_CYCLE
- **review.md** §1 — bounded learning, границы эволюции
- **.eurika/rules/bounded-evolution.mdc** — правило для агента
