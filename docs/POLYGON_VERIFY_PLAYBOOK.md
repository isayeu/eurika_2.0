# Polygon verify_success — Playbook

Как накапливать verify_success по polygon drills (extract_block_to_helper, extract_nested_function) для whitelist и policy.

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
