# Onboarding ≤ 10 мин (B.9)

Сценарий для новичка: clone → **eurika-qt** (или scan → doctor → fix) за 10 минут.

Продуктовая цель: [VISION.md](VISION.md) — Cursor-подобная оболочка + самообучение + paper Market.

## Предварительно

- Python 3.10+ (рекомендуется 3.12+)
- Git
- Железо: см. [HARDWARE.md](HARDWARE.md) — минимум (CPU/8 GB RAM) и оптимум под GPU/Ollama; PyTorch — для Market ML

## Шаги (≈10 мин)

### 1. Clone (≈1 мин)

```bash
git clone <repo_url>
cd eurika_2.0.Qt
```

### 2. Установка (≈2 мин)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[test,qt]"
```

### 2b. Qt shell (рекомендуется)

```bash
eurika-qt .
```

Укажите project root = этот репозиторий. Chat → Market — paper learning (без live-ордеров). См. [UI.md](UI.md), [CHAT.md](CHAT.md).

### 3. Scan — полный скан проекта (≈2–3 мин)


```bash
eurika scan .
```

Результат: `self_map.json`, отчёты по smells, summary.

### 4. Doctor — диагностика без патчей (≈2 мин)

```bash
eurika doctor .
```

Результат: report, архитектурные рекомендации. Опция `--no-llm` для быстрого шаблонного вывода без LLM.

### 5. Fix — план и применение (≈2–3 мин)

Сначала dry-run:

```bash
eurika fix . --dry-run
```

Просмотрите план. Для применения:

```bash
eurika fix .
```

Или через Qt: `eurika-qt .` → вкладка Commands → scan/doctor/fix, Run.

**Опционально:** для обогащения architect локальными заметками — скопируйте `docs/eurika_knowledge.example.json` в корень проекта как `eurika_knowledge.json` и при необходимости отредактируйте темы. Примеры вызова API: `examples/knowledge/`.

## Qt-путь (альтернатива CLI)

```bash
eurika-qt .
```

1. Выбрать project root (Browse)
2. Models → при необходимости выбрать Ollama model (для fix, release check)
3. Commands → scan → Run
4. Commands → doctor → Run
5. Commands → fix (--dry-run) → Run

## Критерий B.9

Новичок выполняет clone → scan → doctor → fix (или fix --dry-run) за ≤ 10 минут следуя этой инструкции.

При ошибках (verify timeout, ModuleNotFoundError, LLM fallback, self_map missing) см. [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Chat (eurika-qt)

1. Укажите **Project root** (папка с `.py` — не обязательно `pyproject.toml`).
2. Вкладка **Chat**: «что за проект?», «покажи дерево», «сколько файлов?» — ответ без LLM.
3. Свободные вопросы — через Ollama/OpenAI (вкладка **Models**).
4. Полный список команд и переменных `.env`: [CHAT.md](CHAT.md).

## Опционально (продвинутое)

- **EURIKA_WEIGHT_ADAPTATION=0** — отключить адаптацию весов (по умолчанию включено: Energy-based loop, W -= lr×ΔE).
- **EURIKA_META_CONTROLLER=1** — при включённой weight adaptation: meta-controller переключает стратегию при деградации (низкий success rate, серия регрессий).
- **refactor_code_smell + LLM:** `eurika learn-github . --light --build-patterns` → `EURIKA_USE_LLM_EXTRACT=1 eurika fix .` — OSS-примеры улучшают LLM extract. См. docs/archive/REFACTOR_CODE_SMELL_PLAN.md.
