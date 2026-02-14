# Eurika AgentCore — Design v0.2 (Draft)

> Этот документ описывает **контракт** будущего AgentCore v0.2,
> основываясь на уже существующем Architecture Awareness Engine v0.1.
> **Реализации нет**, только интерфейсы и ограничения.

---

## 1. Позиция AgentCore в системе

В v0.1 ядро Eurika — это **Architecture Awareness Engine**:

- `code_awareness.py` — структура и code smells
- `project_graph.py` + `graph_analysis.py` — граф зависимостей
- `architecture_smells.py` — архитектурные smells
- `architecture_summary.py` — системный портрет
- `architecture_advisor.py` — рекомендации
- `architecture_history.py` + `architecture_diff.py` — история и эволюция

AgentCore v0.2 не заменяет этот слой, а **строится поверх него**:

```text
Human
  ↑
AgentCore (v0.2)
  ↑
Architecture Awareness Engine (v0.1)
  ↑
Codebase
```

---

## 2. Входные артефакты AgentCore v0.2

AgentCore не ходит напрямую в файловую систему и AST. Он работает с уже
подготовленными артефактами.

### 2.1 Обязательные входы

- **Self-map** (`self_map.json`)
  - файлы, строки, функции, классы, зависимости.
- **Architecture summary** (output `build_summary(...)`)
  - `system`: modules/dependencies/cycles,
  - `central_modules`,
  - `risks`,
  - `syntactic maturity`.
- **Architecture smells**
  - список `ArchSmell` из `architecture_smells.detect_smells(...)`.
- **Architecture history**
  - `architecture_history.json`,
  - тренды (`trend()`),
  - регрессии (`detect_regressions()`),
  - dynamic maturity (`evolution_report(...)`).
- **Последние observations**
  - данные из `eurika_observations.json` (что и когда сканировали).

### 2.2 Формат входного события

На уровне AgentCore базовое событие (InputEvent v0.2) для архитектурного домена
может выглядеть так:

```python
class InputEvent:
    type: Literal["arch_scan", "arch_review", "arch_evolution_query"]
    payload: dict        # параметры, фильтры, контекст задачи
    source: str          # "cli", "api", "scheduler"
    timestamp: float
```

- `arch_scan` — инициировать новый scan (но сам scan всё ещё делает v0.1 engine).
- `arch_review` — запросить анализ/объяснение текущего состояния.
- `arch_evolution_query` — запросить оценку траектории/рисков.

---

## 3. Выходы AgentCore v0.2

AgentCore в v0.2 **не модифицирует код** и **не выполняет действия**, он:

- формирует **решения/предложения** (DecisionProposal),
- обосновывает их (rationale),
- маркирует приоритет/уверенность.

### 3.1 DecisionProposal (архитектурный домен)

```python
class DecisionProposal:
    action: str          # "explain_risk", "suggest_refactor_plan", "prioritize_modules"
    arguments: dict      # структурированные данные по действию
    confidence: float    # [0.0, 1.0]
    rationale: str       # человеческое объяснение
```

Примеры `action`:

- `"explain_risk"` — объяснить выбранный архитектурный smell/узел.
- `"suggest_refactor_plan"` — предложить план высокоуровневой архитектурной доработки.
- `"prioritize_modules"` — отсортировать модули по архитектурному риску/ценности.
- `"summarize_evolution"` — кратко описать эволюцию архитектуры за период.

### 3.2 Результат шага AgentCore

Executor v0.2 по‑прежнему **ничего не выполняет во внешнем мире**. Его задача —
вернуть Result в виде структурированного ответа:

```python
class Result:
    success: bool
    output: dict     # данные для пользователя (отчёт, план, список модулей)
    side_effects: list[str]  # лог сообщений, никаких реальных эффектов
```

---

## 4. Разрешённые и запрещённые действия AgentCore v0.2

В рамках SPEC v0.1/v0.2 AgentCore:

### Разрешено

- читать:
  - `self_map.json`,
  - `architecture_history.json`,
  - `eurika_observations.json`,
  - результаты `architecture_summary` и `architecture_smells`.
- комбинировать и фильтровать эти данные:
  - выбирать подсети графа,
  - фокусироваться на конкретных модулях/слоях,
  - строить агрегаты (например, top‑N рисковых модулей).
- генерировать **предложения/отчёты/планы**, которые:
  - человек читает и оценивает,
  - могут служить входом для ручного рефакторинга или будущего sandbox‑цикла.

### Запрещено

- модифицировать:
  - исходный код,
  - `self_map.json`,
  - историю (`architecture_history.json`) напрямую.
- выполнять:
  - любые shell‑команды, кроме явно разрешённых в sandbox,
  - любые сетевые вызовы к внешнему миру.
- принимать:
  - автономные решения без подтверждения человеком.

AgentCore v0.2 — это **архитектурный советник**, а не исполнитель.

---

## 5. Взаимодействие с существующими модулями

### 5.1 Поток для `arch_review`

1. Человек запускает что‑то вроде:

   ```bash
   eurika agent arch-review
   ```

2. CLI формирует `InputEvent(type="arch_review", payload=...)` и передаёт в AgentCore.
3. AgentCore:
   - читает свежий `self_map.json` (или инициирует новый scan),
   - строит/загружает `ProjectGraph` и smells,
   - читает `architecture_history.json`,
   - вызывает `architecture_summary.build_summary` и `architecture_advisor.build_recommendations`.
4. Формирует один или несколько `DecisionProposal` типа:
   - `"explain_risk"` по top‑3 модулям,
   - `"suggest_refactor_plan"` на уровне подсистем.
5. Executor упаковывает это в `Result` (JSON/текст), выводится пользователю.

### 5.2 Поток для `arch_evolution_query`

1. AgentCore читает несколько последних точек из `architecture_history`.
2. Анализирует тренды (complexity / smells / centralization).
3. Возвращает:
   - summary эволюции,
   - список предупреждений (regressions),
   - возможные шаги по снижению риска.

---

## 6. Требования к реализации AgentCore v0.2

1. **Детерминированность**
   - при одинаковых входных артефактах (self_map, history, config) AgentCore должен
     выдавать одинаковые предложения.

2. **Traceability**
   - каждое предложение (`DecisionProposal`) должно быть объяснимо через:
     - какие smells/метрики к нему привели,
     - какие модули/рёбра графа участвовали.

3. **Read-only режим**
   - любые действия ограничены чтением уже подготовленных артефактов и формированием
     текстовых/структурированных отчётов.

4. **Композиция с v0.1**
   - AgentCore не дублирует логику анализа (AST, граф, smells), а использует
     существующие модули как «сенсоры».

---

## 7. Out-of-scope для v0.2

То, что **не** должно появиться в AgentCore v0.2:

- генерация или применение патчей к коду;
- автономный запуск formatters/linters/refactoring‑tools;
- произвольные shell‑команды и сетевые запросы;
- self‑modifying behavior (менять свои же правила).

Эти направления возможны только после:

1. полного Freeze архитектурного движка,
2. явного расширения SPEC и контракта безопасности.

---

## 8. Резюме

v0.1 уже даёт Eurika:

- зрение (self_map + code_awareness),
- архитектурное восприятие (graph + smells + summary),
- память и чувство времени (history + diff + evolution).

v0.2 AgentCore **не добавляет действий**, он добавляет:

- структурированное мышление поверх этих артефактов,
- умение формировать осмысленные архитектурные предложения,
- возможность обсуждать эволюцию системы как последовательность
  обоснованных решений, а не только как набор метрик.

Это даёт чёткий переход:

> v0.1 — *что есть и куда всё идёт*  
> v0.2 — *что с этим архитектурно делать* (но всё ещё руками человека).

