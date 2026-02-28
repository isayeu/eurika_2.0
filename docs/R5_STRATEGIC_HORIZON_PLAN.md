# R5 — Strategic Horizon: план

**Цель:** вывести Eurika на следующий уровень — самонаблюдение, предиктивная аналитика, расширяемость.

---

## 1. Self-guard / Meta-architecture

**Критерий:** Eurika сама детектирует деградацию архитектуры и даёт алерты.

### 1.1 Уже есть
- Layer violations → `dependency_firewall`, `test_dependency_guard`
- Subsystem bypass → `SubsystemBypassRule`, `test_subsystem_imports_via_public_api`
- File size limits → `check_file_size_limits`, блок в self-check
- Trends (complexity, smells, centralization) → `eurika.smells.health`, `evolution.history`

### 1.2 План
| Шаг | Действие | Результат |
|-----|----------|-----------|
| 1.2.1 | Агрегированный SELF-GUARD блок в `eurika self-check` | Один итоговый PASS/FAIL по layer + file_size + subsystem |
| 1.2.2 | Флаг `--strict` / `--fail-on-guard` | `eurika self-check . --strict` → exit 1 при нарушениях |
| 1.2.3 | Complexity budget alarms | Пороги по количеству god_module, bottleneck; алерт при превышении |
| 1.2.4 | Centralization trend alarm | При centralization=increasing в history — предупреждение в self-check |

---

## 2. Intelligence upgrade

**Критерий:** Более точные рекомендации и предикция рисков.

| Шаг | Действие | Результат |
|-----|----------|-----------|
| 2.1 | Risk prediction | Оценка «вероятность регрессии» для модуля на основе history + smells ✓ |
| 2.2 | Recommendation engine | Учёт learning stats, past success rate в приоритизации операций ✓ |
| 2.3 | Контекстные подсказки | @-mentions в chat → фокус на конкретных модулях/smells |

---

## 3. Extensibility

**Критерий:** Подключение внешних анализаторов через единый контракт.

| Шаг | Действие | Результат |
|-----|----------|-----------|
| 3.1 | Plugin interface | `AnalyzerPlugin` protocol: `analyze(path) -> List[ArchSmell]` |
| 3.2 | Регистрация плагинов | `.eurika/plugins.toml` или `pyproject [tool.eurika.plugins]` |
| 3.3 | Агрегация результатов | Eurika + плагины → объединённый отчёт |

### Регистрация плагина

**`.eurika/plugins.toml`:**
```toml
[[plugins]]
entry_point = "my_package.analyzer:analyze"
```

**`pyproject.toml`:**
```toml
[tool.eurika.plugins]
custom = "my_package.analyzer:analyze"
```

Плагин — callable `analyze(project_root: Path) -> List[ArchSmell]`. Пример: `tests/fixtures/eurika_plugin_example.py`.

API: `GET /api/smells_with_plugins` — объединённый список smells (eurika + плагины).

---

## 4. Порядок выполнения

| Фаза | Поток | Оценка |
|------|-------|--------|
| **Фаза A** | Self-guard: SELF-GUARD блок, --strict, trend alarms | 1–2 итерации |
| **Фаза B** | Intelligence: risk prediction, recommendation tuning | 2–3 итерации |
| **Фаза C** | Extensibility: plugin protocol, регистрация | 2–3 итерации |

Старт: **Фаза A** (Self-guard).

---

## 5. Критерии готовности R5

- [x] SELF-GUARD блок в self-check, `--strict` exit 1 при нарушениях
- [x] Centralization/complexity trend alarm в self-check
- [x] Complexity budget alarms (god_module >8, bottleneck >5)
- [x] Risk prediction хотя бы для top-N модулей (`get_risk_prediction`, `/api/risk_prediction`)
- [x] SELF-GUARD в Qt GUI (dashboard блок)
- [x] Plugin interface (протокол + пример): `AnalyzerPlugin`, `.eurika/plugins.toml`, `pyproject [tool.eurika.plugins]`, `tests/fixtures/eurika_plugin_example.py`
