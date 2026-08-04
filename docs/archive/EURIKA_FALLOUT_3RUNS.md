# Eurika Fallout — 3 прогона fix подряд

**Цель:** проверить обучение на неудачах, память, изменение планов.

**Настройка:** оригинальная Eurika (eurika_2.0.Qt) применяет fix к копии (eurika_fallout).

---

## Прогон 1

**Команда:** `eurika fix /home/lena/project/eurika_fallout --runtime-mode auto`

**Результат:**
- Modified: 1 file — `eurika/polygon/decay_polygon.py` (remove_unused_import)
- Verify: ✓ passed
- Decision summary: blocked by policy=43, critic=0, human=0
- delta_score: 0

**EventLog (learn):**
- type: learn, result: **true** (успех)
- goal_id: `eurika/polygon/decay_polygon.py|remove_unused_import`
- execution_outcome: verify_success

**Вывод:** Успех. Провалов нет → обучения на неудачах не было.

---

## Прогон 2

**Команда:** `eurika fix /home/lena/project/eurika_fallout --runtime-mode auto`

**Результат:**
- 0 operations (nothing to apply)
- blocked by policy: 43
- pipeline_stages: input, plan (до Apply не дошло)

**Причина:** policy gates заблокировали все 43 ops. prioritized_smell_actions учитывают verify_success_rate из истории; recent_verify_fail_targets влияют на контекст.

---

## Прогон 3

**Команда:** `eurika fix /home/lena/project/eurika_fallout --runtime-mode auto`

**Результат:**
- 0 operations (nothing to apply)
- blocked by policy: 43
- Аналогично прогону 2

---

## Итоги

| Прогон | Modified | Verify | Learn events | Память/обучение |
|--------|----------|--------|--------------|-----------------|
| 1 | 1 (decay_polygon, remove_unused_import) | ✓ passed | 1 success | record_outcome(verify_success) |
| 2 | 0 | — | 0 | plan заблокирован policy |
| 3 | 0 | — | 0 | plan заблокирован policy |

**Файлы:** Единственное изменение — `eurika/polygon/decay_polygon.py`: удалён неиспользуемый импорт `ProjectMemory`. Логика не нарушена.

**Failure log (из истории eurika_fallout):**
- 10+ recent_failures: llm_extract_block на metric_vector, scoring, explain_api (incomplete_or_broken_llm_extract)
- Enriched: goal_id/plan_hash = None (старый формат событий)

**Вывод:**
1. Прогон 1 применил remove_unused_import, verify прошёл.
2. Прогоны 2–3: policy gates (operation whitelist, verify rate, campaign rules) не допустили apply.
3. Обучение на неудачах не было задействовано — в этих прогонах провалов не было (run 1 — успех; runs 2–3 — 0 apply).
4. Для проверки learning loop нужны сценарии с verify failure; текущая policy строга и блокирует рискованные ops до apply.

