# Eurika v0.1 — Минимальная архитектура и разбор agent_core

Два шага по результатам аудита:
1. Предложение минимальной v0.1 без агентных паттернов
2. Разбор agent_core — что лишнее и почему

---

## Шаг 1. Минимальная v0.1 архитектура

### Принцип

> v0.1 = **OBSERVE ONLY**
> No proposals. No actions. No execution.

Порядок: сначала интеллект (анализ), потом агент.

---

### Целевой пайплайн

```
cli
  ↓
project_map (introspection)
  ↓
code_awareness (analysis)
  ↓
report (format output)
  ↓
memory (store observation)
```

**Без:** selector, reasoner, executor, sandbox.

---

### Один идеальный сценарий

```
eurika scan .
```

или

```
eurika scan
```

**Что происходит:**
1. CLI принимает команду `scan`
2. Project map — сканирует структуру (.py файлы, зависимости)
3. Code awareness — AST, smells, метрики
4. Report — форматирует человекочитаемый отчёт
5. Memory — сохраняет наблюдение (event + результат анализа)

**Выход:** отчёт в stdout + запись в memory. Никаких «предложений» и «действий».

---

### Состав модулей v0.1 (минимальный)

| Модуль | Статус | Назначение |
|--------|--------|------------|
| `code_awareness.py` | ✅ Оставить | Сканирование, AST, smells |
| `memory.py` | ✅ Оставить | Хранение наблюдений (упростить: event + observation) |
| `report.py` | ➕ Создать | Форматирование отчёта |
| `project_map.py` | ➕ Создать или встроить в code_awareness | Карта проекта, self_map |
| `eurika_cli.py` | ➕ Заменить agent_runtime | Точка входа: `eurika scan` |

**Убрать из активного цикла (положить на полку):**
- `agent_core.py` — не использовать в v0.1
- `agent_runtime.py` — заменить на eurika_cli
- `reasoner_dummy.py` — не нужен
- `selector.py` — не нужен
- `executor_sandbox.py` — не нужен в observe-only фазе

**Файлы можно не удалять** — перенести в `_shelved/` или оставить, но не вызывать.

---

### Контракт memory для v0.1

Текущий: `record(event, decision, result)` — завязан на агентный цикл.

Для observe-only:

```python
def record_observation(self, trigger: str, observation: dict) -> None:
    """trigger = "scan", observation = {structure, smells, summary}"""
```

Memory хранит только факты: что сканнули, что увидели. Без decision/result.

---

### Структура eurika_cli.py (эскиз)

```python
# eurika_cli.py
def main():
    args = parse_args()  # "scan" или позиционный путь
    if args.command == "scan":
        root = Path(args.path or ".")
        analyzer = CodeAwareness(root)
        observation = analyzer.analyze_project()
        report = format_report(observation)
        print(report)
        memory.record_observation("scan", observation)
```

Никаких event → context → propose → select → execute. Прямой вызов.

---

## Шаг 2. Разбор agent_core.py — что лишнее и почему

### Текущая структура

```
InputEvent → Context → Reasoner.propose → Selector.select → Executor.execute → Result → Memory.record
```

### Построчный разбор

| Элемент | Строки | Назначение | Лишнее? | Почему |
|---------|--------|------------|---------|--------|
| `InputEvent` | 18–23 | Обёртка входа | ❌ Пока нет | В v0.1 можно обойтись `(command, path)` |
| `Context` | 26–29 | event + memory_snapshot + system_state | ⚠️ Да для v0.1 | memory_snapshot нужен только reasoner'у. Без reasoner — не нужен |
| `DecisionProposal` | 33–37 | action, arguments, confidence, rationale | ⚠️ Да для v0.1 | Нет «решений» в observe-only. Есть только observation |
| `Result` | 40–44 | success, output, side_effects | ⚠️ Частично | В v0.1 достаточно dict с observation |
| `Memory` Protocol | 51–53 | snapshot, record | ⚠️ Перегружен | record(event, decision, result) — агентный контракт |
| `Reasoner` Protocol | 56–57 | propose(context) | ⚠️ Да для v0.1 | Нет reasoning — есть прямой анализ |
| `DecisionSelector` Protocol | 60–61 | select(proposals) | ⚠️ Да для v0.1 | Нет выбора между предложениями |
| `Executor` Protocol | 64–65 | execute(decision) | ⚠️ Да для v0.1 | Нет исполнения |
| `AgentCore` | 72–121 | step(event) — весь цикл | ⚠️ Да для v0.1 | Вся логика завязана на agent pipeline |
| `FORBIDDEN` | 129–134 | Список запретов | ✅ Оставить | Документация, не код |

---

### Итог по agent_core

**Для v0.1 observe-only:**
- `AgentCore`, `Context`, `DecisionProposal`, `Result` — не используются
- Протоколы `Reasoner`, `DecisionSelector`, `Executor` — не используются
- `InputEvent` — можно заменить на простой `(command, path)`
- `Memory` — нужен упрощённый контракт `record_observation()`

**Что сохранить как основу для v0.2+:**  
Контракты и протоколы — не удалять, а отложить. Когда появится фаза «propose/select/execute», они пригодятся.

**Главная причина «лишнего»:**  
agent_core решает задачу *оркестрации выбора и исполнения*. В observe-only нет ни выбора, ни исполнения — только цепочка: scan → analyze → report → store.

---

## Рекомендуемый порядок действий

1. Добавить в SPEC: `v0.1 = observation-only stage`
2. Создать `eurika_cli.py` с командой `scan`
3. Создать `report.py` (или вынести `_format_analysis` из executor)
4. Упростить memory: `record_observation(trigger, observation)`
5. Перевести agent_runtime, reasoner, selector, executor в «shelved» — не вызывать из main
6. Проверить один сценарий: `eurika scan .` → отчёт → запись в memory

---

*Документ создан по результатам инженерного аудита.*
