# Eurika 2.0 — SPECIFICATION (v0.2 draft)

## 1. Назначение v0.2

v0.2 добавляет поверх Architecture Awareness Engine v0.1:

- **AgentCore-слой для архитектурного домена**;
- формирование структурированных архитектурных предложений (`DecisionProposal`);
- использование истории (`architecture_history`) как источника контекста.

По-прежнему:

- **нет исполнения**,
- **нет модификации кода**,
- **нет автономных действий**.

## 2. Границы ответственности v0.2

### 2.1 Что добавляет v0.2

- чтение уже подготовленных артефактов:
  - `self_map.json`,
  - `architecture_history.json`,
  - `eurika_observations.json`,
  - результаты `architecture_summary` и `architecture_smells`;
- сборка этих данных в:
  - объяснение архитектурных рисков (explain_risk),
  - описание эволюции (summarize_evolution),
  - (в будущем) приоритезацию модулей и планы рефакторинга.

### 2.2 Что НЕ добавляет v0.2

- никакого исполнения (Executor остаётся “пустым” с точки зрения внешнего мира);
- никакого изменения кода или артефактов (`self_map.json`, `architecture_history.json`);
- никакого LLM‑driven reasoning в ядре — только детерминированные эвристики поверх уже вычисленных метрик.

## 3. Позиция AgentCore v0.2 в системе

Точка встраивания:

```text
Human
  ↑
AgentCore (v0.2)
  ↑
Architecture Awareness Engine (v0.1)
  ↑
Codebase
```

v0.1:

- `code_awareness.py` — структура и code smells;
- `project_graph.py` + `graph_analysis.py` — граф зависимостей;
- `architecture_smells.py` / `architecture_diagnostics.py` — архитектурные smells;
- `architecture_summary.py` — системный портрет;
- `architecture_advisor.py` — рекомендации;
- `architecture_history.py` + `architecture_diff.py` — история и эволюция.

v0.2:

- **не трогает** эти модули,
- использует их как “сенсоры” для построения выводов.

## 4. Базовые сущности v0.2

Используются определения из `agent_core.py` и `AGENT_DESIGN_v0.2.md`.

### 4.1 InputEvent (архитектурный домен)

```python
class InputEvent:
    type: Literal["arch_review", "arch_evolution_query"]
    payload: dict        # параметры, фильтры, контекст задачи
    source: str          # "cli", "api", "scheduler", "test"
    timestamp: float
```

- `arch_review` — запрос на анализ текущего архитектурного состояния (риски + эволюция);
- `arch_evolution_query` — запрос только на оценку траектории/трендов.

### 4.2 DecisionProposal

```python
class DecisionProposal:
    action: str          # "explain_risk", "summarize_evolution", ...
    arguments: dict      # структурированные данные по действию
    confidence: float    # [0.0, 1.0]
    rationale: str       # человеческое объяснение
```

В v0.2 (минимальный набор):

- `"explain_risk"` — объяснить архитектурные риски на основе smells + summary;
- `"summarize_evolution"` — описать архитектурную эволюцию по истории.

### 4.3 Result

```python
class Result:
    success: bool
    output: dict         # данные для пользователя (отчёт/структурированный ответ)
    side_effects: list[str]  # лог сообщений, никаких реальных эффектов
```

Result v0.2 **не выполняет действий** — только упаковывает предложения в удобный формат.

## 5. AgentCore v0.2 — разрешённые действия

### 5.1 Можно

- читать:
  - `self_map.json`,
  - `architecture_history.json`,
  - `eurika_observations.json`,
  - результаты модулей архитектурного движка (summary, smells, metrics);
- агрегировать и фильтровать:
  - выделять центральные узлы,
  - вычислять тренды и регрессии по истории,
  - строить списки топ‑рисковых модулей;
- формировать **предложения/отчёты**, которые:
  - читает человек‑инженер,
  - используются как вход для ручного рефакторинга.

### 5.2 Нельзя

- модифицировать:
  - исходный код проекта,
  - `self_map.json`,
  - `architecture_history.json`,
  - любые другие артефакты анализа;
- выполнять:
  - shell‑команды,
  - сетевые запросы;
- принимать автономные решения без подтверждения человеком.

## 6. Конкретные сценарии v0.2 (минимальный набор)

### 6.1 `arch_review`

Поток:

1. CLI вызывает `eurika agent arch-review [path]`.
2. Формируется `InputEvent(type="arch_review", payload={"path", "window"}, source="cli")`.
3. AgentCore:
   - читает `self_map.json` для проекта;
   - строит `ProjectGraph` и список `ArchSmell`;
   - читает `architecture_history.json`;
   - собирает summary (central modules, risks, syntactic maturity);
   - формирует два `DecisionProposal`:
     - `"explain_risk"`,
     - `"summarize_evolution"`.
4. CLI печатает `Result.output` как JSON.

### 6.2 `arch_evolution_query`

Поток:

1. CLI вызывает `eurika agent arch-evolution [path]`.
2. Формируется `InputEvent(type="arch_evolution_query", payload={"path", "window"}, source="cli")`.
3. AgentCore:
   - читает `architecture_history.json`;
   - вычисляет тренды (complexity, smells, centralization);
   - детектирует регрессии;
   - формирует один `DecisionProposal("summarize_evolution", ...)`.
4. CLI печатает `Result.output` как JSON.

## 7. Требования к реализации v0.2

1. **Детерминированность**  
   При одинаковых артефактах (self_map, history, observations, config) результат должен быть одинаковым.

2. **Traceability**  
   Каждое предложение должно быть объяснимо через:
   - какие smells/метрики/узлы графа к нему привели;
   - какие точки истории использовались.

3. **Read-only режим**  
   AgentCore читает только файлы, записанные v0.1‑движком, и формирует текст/JSON.

4. **Композиция с v0.1**  
   Никакого дублирования анализа: AgentCore — это надстройка над:
   - `code_awareness`,
   - `project_graph` + `graph_analysis`,
   - `architecture_smells` / `architecture_diagnostics`,
   - `architecture_summary` / `architecture_history` / `architecture_diff`,
   - `observation_memory`.

## 8. Критерии успеха v0.2

v0.2 считается успешной, если:

- инженер может:
  - запустить `eurika agent arch-review .` и получить **осмысленное объяснение рисков** (explain_risk);
  - запустить `eurika agent arch-evolution .` и получить **осмысленное описание траектории** (summarize_evolution);
- эти ответы:
  - воспроизводимы,
  - опираются на измеримые метрики (граф, smells, history),
  - не выходят за рамки домена архитектуры Eurika.

