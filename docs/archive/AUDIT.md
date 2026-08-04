# Eurika 2.0 — AUDIT (v0.1)

Внешний аудит кодовой базы. Цель: что есть, что лишнее, расхождения со SPEC.

---

## 1. Структура модулей

| Файл | Назначение |
|------|------------|
| `agent_core.py` | Контракты, AgentCore, pipeline step |
| `agent_runtime.py` | Точка входа, CLI, EurikaRuntime |
| `memory.py` | SimpleMemory, MemoryRecord, TTL/pruning |
| `reasoner_dummy.py` | DummyReasoner: echo, analyze, anti-loop |
| `selector.py` | SimpleSelector: max confidence |
| `executor_sandbox.py` | ExecutorSandbox: simulate, log |
| `code_awareness.py` | CodeAwareness: read-only анализ кода |

---

## 2. Используемые классы

### agent_core
- `InputEvent` — входное событие
- `Context` — контекст шага
- `DecisionProposal` — предложение
- `Result` — результат выполнения
- `AgentCore` — оркестратор
- `Memory`, `Reasoner`, `DecisionSelector`, `Executor` — протоколы

### memory
- `MemoryRecord` — запись (event, decision, result)
- `SimpleMemory` — реализация Memory

### reasoner_dummy
- `DummyReasoner` — реализация Reasoner

### selector
- `SimpleSelector` — реализация DecisionSelector

### executor_sandbox
- `ExecutorSandbox` — реализация Executor

### code_awareness
- `CodeAwareness` — анализ кода
- `FileInfo`, `Smell` — структуры данных

### agent_runtime
- `EurikaRuntime` — сборка и CLI

---

## 3. Мёртвый / слабо используемый код

| Элемент | Статус |
|---------|--------|
| `agent_core.FORBIDDEN` | Не используется в runtime, только декларация |
| `executor_sandbox.last_actions()` | Не вызывается агентом, но полезен для отладки |
| `executor_sandbox.reset_history()` | Аналогично |
| `InputEvent.payload` | Тип `dict`, но в runtime передаётся `str` — несоответствие типов |

**Рекомендация:** оставить как есть; FORBIDDEN — документирование, last_actions/reset_history — API для будущего.

---

## 4. Зависимости (явные и неявные)

```
agent_runtime
  ├── agent_core
  ├── memory → agent_core
  ├── reasoner_dummy → agent_core, code_awareness (lazy)
  ├── selector → agent_core
  └── executor_sandbox → agent_core

code_awareness — stdlib only (ast, pathlib)
```

Неявная: `reasoner_dummy` импортирует `code_awareness` внутри `propose()` (ленивый импорт), чтобы избежать циклической зависимости.

---

## 5. Расхождения со SPEC

| SPEC | Текущее состояние |
|------|-------------------|
| **6.2 Self-Introspection** — `self_map.json` | Нет. CodeAwareness выдаёт structure в dict, но не пишет JSON-файл |
| **6.3 Code Analysis** — поиск дублирования | Нет. Есть long_function, deep_nesting; дублирование не ищется |
| **6.4 Memory** — findings, decisions, errors | Используем event, decision, result (сопоставимо, но другая терминология) |
| **6.5 Report Module** | Нет отдельного модуля. Форматирование в `_format_analysis()` внутри executor |
| **LLM** | Не используется (SPEC допускает ограниченное использование) |

---

## 6. Итог

**Сохраняем:**
- Всю текущую структуру модулей
- Core pipeline, memory, sandbox, code_awareness

**Доработать (приоритет):**
1. Self-Introspection: добавить запись `self_map.json` (или явно решить, что не нужен)
2. Report Module: вынести форматирование в отдельный модуль
3. Code Analysis: добавить поиск дублирования (опционально)

**Выбросить:** ничего критичного.

---

*Аудит выполнен по TASKS.md, Этап 1.*
