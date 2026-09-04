# Polygon verify_success — Playbook

Как накапливать verify_success по polygon drills (extract_block_to_helper, extract_nested_function) для whitelist и policy.

## C.14 HITL ритуал (самый тонкий контур)

Один deterministic цикл «посеять → предложить → человек решает» (без LLM, без silent apply):

```bash
eurika prove-cycle . --propose                      # drill imports (default)
eurika prove-cycle . --propose --drill extractable_block
eurika prove-cycle . --propose --drill long_function
eurika prove-cycle . --propose --drill llm_extract
# Qt Approvals → Load plan → approve только polygon target
# или вручную team_decision=approve в .eurika/pending_plan.json
eurika fix . --apply-approved
```

`--propose` пишет pending plan и **не** применяет патч. Drills: `imports` → `remove_unused_import`; `extractable_block` → `extract_block_to_helper`; `long_function` → `extract_nested_function`; `llm_extract` → `llm_extract_block` на `refactor_code_smell_drill.py` (live LLM при `EURIKA_USE_LLM_EXTRACT=1`, иначе offline synthetic с `_sum_intermediates`). Обычный `prove-cycle` (без флага) по-прежнему работает только на `.eurika/prove_cycle/drill_unused.py`.

Chat: «предложи полигон эксперимент» → `imports`; «второй полигон» → `extractable_block`; «третий полигон» → `long_function`; «четвёртый полигон» / «полигон llm» → `llm_extract`. Mirror в Terminal + `live_activity.jsonl`, автофокус Approvals.

**Важно (2026-09-04):** после apply pytest может быть зелёным, а rescan — увидеть «шум» (грязное дерево / float jitter) и раньше откатывал с `metrics_worsened`. Для **только** `eurika/polygon/*` и для Δ score < `1e-4` откат по метрикам **не** делается — gate остаётся pytest.

## Подготовка

```bash
./scripts/polygon_prep.sh
```

Выполняет scan (refresh self_map) и pytest polygon semantics. Дальше — fix с hybrid + allow-low-risk.

---

## Вариант A: Qt Hybrid (рекомендуется)

1. Запустить `eurika-qt` или Qt-приложение.
2. Выбрать project root = eurika_2.0.Qt.
3. **Commands** → Fix, включить `--runtime-mode hybrid`, `--allow-low-risk-campaign`.
4. Запустить fix.
5. Во вкладке **Approvals** появятся pending операции (в т.ч. polygon: extractable_block, long_function, deep_nesting).
6. Одобрить (`Approve`) только polygon ops: `eurika/polygon/extractable_block.py`, `eurika/polygon/long_function.py`, `eurika/polygon/long_function_extractable_block.py`, `eurika/polygon/deep_nesting.py`.
7. Нажать **Apply approved**.
8. После apply → verify → learning записывает `verify_success`/`verify_fail`.
9. Повторить 2–3 раза для накопления статистики.

**Цель:** 2+ `verify_success` на target без повторных `verify_fail` → `whitelist_candidates` в `eurika learning-kpi . --polygon`.

---

## Вариант B: CLI hybrid

```bash
eurika fix . --runtime-mode hybrid --allow-low-risk-campaign
# В интерактивном запросе: approve номера polygon ops (1–5 и т.д.)
# Или: eurika fix . --apply-approved  (после сохранения pending_plan с approved ops)
```

---

## Вариант C: Whitelist уже есть

`.eurika/operation_whitelist.json` содержит polygon drills с `allow_in_auto`. При `eurika fix . --allow-low-risk-campaign` (auto) whitelist должен обходить weak-pair deny. Если всё ещё blocked — проверить campaign `verify_fail_keys` (2+ fail → skip); попробовать `EURIKA_IGNORE_CAMPAIGN=1` для теста.

---

## Проверка накопления

```bash
eurika learning-kpi . --polygon
```

Секция **Polygon drills** покажет `verify_success`, `verify_fail`, `rate` по smell|action. Кандидаты в whitelist: 2+ success, 0 fail.

---

## Verify timeout (диагноз)

Частый `verify_fail` на polygon — не ошибка кода, а **таймаут pytest**. При `apply_and_verify` verify гоняет полный `pytest -q`; полный прогон часто >90–300s → `verify command timed out` → rollback, хотя фикс корректен.

Для тренировочных циклов — быстрый verify только затронутых тестов (`python -m pytest`, иначе возможен `ModuleNotFoundError` из-за sys.path):

```bash
eurika fix . --no-code-smells --allow-low-risk-campaign \
  --verify-cmd "python -m pytest tests/test_clean_imports_cli.py -q"
```

В `pyproject.toml` по умолчанию может быть быстрый `verify_cmd` / `verify_timeout = 300`. Полный прогон: `--verify-cmd ".venv/bin/pytest tests/ -q"` или `EURIKA_VERIFY_TIMEOUT=600`.
