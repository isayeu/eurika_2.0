# Документация Eurika

Навигация. Продуктовая цель — Cursor-подобная оболочка + самообучение + paper Market: [VISION.md](VISION.md).

## 1. Продукт

| Документ | Описание |
|----------|----------|
| [VISION.md](VISION.md) | Цель продукта, окно наблюдения, чеклист journal |
| [ONBOARDING.md](ONBOARDING.md) | ≤ 10 мин: clone → Qt / scan → doctor → fix |
| [UI.md](UI.md) | Qt UI: вкладки, тема, Chat/Market |
| [CHAT.md](CHAT.md) | Chat: интенты, LLM/Ollama, `.env` |
| [MEMORY.md](MEMORY.md) | EventLog, LearningStore, Market ML на диске |

## 2. Архитектура

| Документ | Описание |
|----------|----------|
| [Architecture.md](Architecture.md) | Слои L0–L6, fix-cycle, Execution Model |
| [COGNITIVE_LOOP.md](COGNITIVE_LOOP.md) | R8: контракты 8 этапов |
| [API_BOUNDARIES.md](API_BOUNDARIES.md) | Публичные фасады подсистем |
| [DEPENDENCY_FIREWALL.md](DEPENDENCY_FIREWALL.md) | Правила layer/subsystem |
| [RISKS.md](RISKS.md) | Архитектурные риски |
| [BOUNDED_EVOLUTION.md](BOUNDED_EVOLUTION.md) | Дисциплина роста, caps |

## 3. Knowledge и плагины

| Документ | Описание |
|----------|----------|
| [KNOWLEDGE_LAYER.md](KNOWLEDGE_LAYER.md) | Knowledge Provider |
| [KNOWLEDGE_GRAPH_DESIGN.md](KNOWLEDGE_GRAPH_DESIGN.md) | Code/Arch/Knowledge графы |
| [R5_PLUGIN_INTERFACE.md](R5_PLUGIN_INTERFACE.md) | Контракт плагинов |

## 4. План и операции

| Документ | Описание |
|----------|----------|
| [ROADMAP.md](ROADMAP.md) | Единый план задач |
| [CLI.md](CLI.md) | Справочник команд |
| [DOGFOODING.md](DOGFOODING.md) | Ритуал self-check |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Типовые ошибки |
| [HARDWARE.md](HARDWARE.md) | Железо, Ollama, PyTorch |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Зависимости |
| [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) | Чеклист перед релизом |
| [TYPING_CONTRACT.md](TYPING_CONTRACT.md) | mypy optional-gate |
| [POLYGON_VERIFY_PLAYBOOK.md](POLYGON_VERIFY_PLAYBOOK.md) | Polygon drills / verify timeout |
| [CYCLE_REPORT.md](CYCLE_REPORT.md) | Журнал циклов (ритуал, не продуктовый индекс) |
| [archive/](archive/) | Исторические ревью и закрытые планы |
