# R4 — Modular Platform: детальный план

**Цель:** подготовить Eurika к масштабированию без архитектурного долга.

---

## 1. Subsystem Decomposition

**Критерий:** Нет прямых «соседских» обходов мимо публичных API.

### 1.1 Аудит текущего состояния

| Шаг | Действие | Результат |
|-----|----------|-----------|
| 1.1.1 | Пройтись по пакетам: `eurika.storage`, `eurika.agent`, `eurika.reasoning`, `eurika.refactor`, `eurika.knowledge`, `eurika.analysis`, `eurika.smells`, `eurika.evolution`, `eurika.reporting`, `eurika.core`, `cli.orchestration` | Список модулей, у которых нет `__all__` или он неполный |
| 1.1.2 | Найти импорты «через соседа» (например, `eurika.agent` импортирует из `eurika.storage.event_engine` напрямую вместо `eurika.storage`) | Таблица нарушений |
| 1.1.3 | Сверить Architecture.md §0.7 API Boundaries с фактическими `__all__` | Расхождения |

### 1.2 Действия по подсистемам

| Подсистема | Текущий `__all__` | План |
|------------|-------------------|------|
| **eurika.storage** | Проверить экспорт `ProjectMemory`, `event_engine`, `SessionMemory` | Добавить недостающее, убрать лишнее из публичного API |
| **eurika.agent** | `run_agent_cycle`, `DefaultToolContract` | Убедиться, что внутренние модули (`policy`, `tools`, `runtime`) не импортируются извне напрямую |
| **eurika.reasoning** | `advisor`, `architect`, `planner` | Проверить: кто импортирует `planner_patch_ops`, `context_sources` — только фасады? |
| **eurika.refactor** | Модули по действиям | Единый фасад `refactor` с `__all__` по типам операций |
| **eurika.knowledge** | `SMELL_TO_KNOWLEDGE_TOPICS`, providers | Проверить импорты `eurika.knowledge.base` извне — только через `eurika.knowledge` |
| **cli.orchestration** | Фасады doctor, fix, full_cycle, prepare, apply_stage | Проверить: handlers импортируют только через `cli.orchestrator` или orchestration `__all__`? |

### 1.3 Конкретные шаги

1. **Добавить тест `test_subsystem_imports_via_public_api`**  
   Проверка: модули вне пакета X импортируют только символы из `X.__all__` (или `X.submodule` если submodule — публичный фасад). Можно начать с «запрещённых» импортов: `eurika.knowledge.base` из `eurika.reasoning`, `eurika.storage.event_engine` из `eurika.agent` и т.п.

2. **Дополнить `dependency_firewall`**  
   Новые правила типа: «клиенты `eurika.reasoning` не импортируют `eurika.knowledge.base`» (только `eurika.knowledge`).

3. **Документировать публичные API**  
   В `Architecture.md` или `docs/API_BOUNDARIES.md` — таблица: пакет → публичные точки входа → как импортировать.

---

## 2. Dependency Firewall

**Критерий:** CI падает при нарушении firewall-правил.

### 2.1 Текущее состояние

- `eurika/checks/dependency_firewall.py` — `DEFAULT_RULES`, `DEFAULT_LAYER_PATH_RULES`, `DEFAULT_LAYER_IMPORT_RULES`, `DEFAULT_LAYER_EXCEPTIONS`
- `tests/test_dependency_guard.py` — `test_no_forbidden_imports`, `test_layer_firewall_contract_soft_start`
- Soft-start: при violation тест делает `pytest.skip`, если `EURIKA_STRICT_LAYER_FIREWALL!=1`
- R1: 0 violations, 0 waivers

### 2.2 План по шагам

| Шаг | Действие | Результат |
|-----|----------|-----------|
| 2.2.1 | Запустить `EURIKA_STRICT_LAYER_FIREWALL=1 pytest tests/test_dependency_guard.py` | Если есть violations — зафиксировать список |
| 2.2.2 | Исправить все layer violations или добавить `LayerException` с `reason` в `LAYER_FIREWALL_EXCEPTIONS` | 0 violations в strict mode |
| 2.2.3 | Включить strict mode в CI (GitHub Actions / GitLab CI) | `env: EURIKA_STRICT_LAYER_FIREWALL: "1"` |
| 2.2.4 | Добавить coverage firewall-тестов в regression | `pytest tests/test_dependency_guard.py tests/test_dependency_firewall.py` |
| 2.2.5 | Дополнить rules для qt_app, eurika/api, runtime_scan | Новые path_pattern при необходимости |
| 2.2.6 | Документировать: как добавлять rule, как добавлять exception | Обновить Architecture.md §0.6 или отдельный `docs/DEPENDENCY_FIREWALL.md` |

### 2.3 CI-интеграция

```yaml
# Пример для GitHub Actions
- name: Dependency firewall (strict)
  env:
    EURIKA_STRICT_LAYER_FIREWALL: "1"
  run: pytest tests/test_dependency_guard.py -v
```

---

## 3. Release Hygiene

**Критерий:** Релизный чеклист выполняется как обязательный gate.

### 3.1 Чеклист (релизный gate)

| # | Проверка | Команда / действие |
|---|----------|---------------------|
| 1 | Tests pass | `pytest tests/ -q` |
| 2 | Edge-case tests | `pytest -m edge_case -v` |
| 3 | Dependency firewall (strict) | `EURIKA_STRICT_LAYER_FIREWALL=1 pytest tests/test_dependency_guard.py` |
| 4 | Lint (ruff) | `ruff check eurika cli` (если настроен) |
| 5 | Type check (mypy) | `mypy eurika cli` |
| 6 | File size limits | `eurika self-check .` (блок FILE SIZE LIMITS) |
| 7 | Layer discipline | `eurika self-check .` (блок LAYER DISCIPLINE) |
| 8 | Dead code / TODO hygiene | Ручной аудит или скрипт: `rg "TODO|FIXME|XXX" --type py -g '!test*'` |
| 9 | Clean-start check | `pip install -e . && eurika scan . && eurika doctor . --no-llm` (smoke) |
| 10 | CHANGELOG updated | Проверить, что версия и изменения описаны |

### 3.2 Действия

| Шаг | Действие | Результат |
|-----|----------|-----------|
| 3.2.1 | Создать `scripts/release_check.sh` или `make release-check` | Один скрипт, который прогоняет пункты 1–9 |
| 3.2.2 | Добавить в `docs/RELEASE_CHECKLIST.md` | Документированный чеклист с командами |
| 3.2.3 | Опционально: pre-commit или CI job `release-hygiene` | Запуск перед merge в main / перед тегом |
| 3.2.4 | TODO hygiene: собрать `TODO`/`FIXME` по критичным пакетам | Список для постепенного закрытия |
| 3.2.5 | Dead code: `ruff` / `vulture` / ручной обзор | Удалить неиспользуемый код в core |

### 3.3 Приоритет скриптов

1. `release_check.sh` — основные пункты (tests, dependency guard, self-check, smoke)
2. Отдельные команды для lint/mypy — если ещё не в CI
3. Документация в `RELEASE_CHECKLIST.md`

---

## 4. Порядок выполнения

| Фаза | Поток | Оценка |
|------|-------|--------|
| **Фаза A** | Dependency firewall (2.2.1–2.2.4) | 1–2 итерации |
| **Фаза B** | Subsystem decomposition (1.1, 1.3) | 2–3 итерации |
| **Фаза C** | Release hygiene (3.2.1–3.2.3) | 1 итерация |
| **Фаза D** | CI-интеграция (2.2.3, 3.2.3) | 1 итерация |

Рекомендуемый старт: **Фаза A** (Dependency firewall) — быстрый и измеримый результат, затем **Фаза C** (Release hygiene) для фиксации процесса.

---

## 5. Критерии готовности R4

- [x] `EURIKA_STRICT_LAYER_FIREWALL=1` — 0 violations
- [x] CI запускает dependency firewall в strict mode (`.github/workflows/ci.yml`)
- [x] `scripts/release_check.sh` существует
- [x] `docs/RELEASE_CHECKLIST.md` описан
- [x] Аудит выполнён; добавлены SubsystemBypassRule, test_subsystem_imports_via_public_api; cli/agent, api/prepare используют фасады; architecture_planner — exception
