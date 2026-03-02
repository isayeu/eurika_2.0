# Onboarding ≤ 10 мин (B.9)

Сценарий для новичка: clone → scan → doctor → fix за 10 минут.

## Предварительно

- Python 3.10+ (рекомендуется 3.12+)
- Git

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

## Qt-путь (альтернатива CLI)

```bash
eurika-qt .
```

1. Выбрать project root (Browse)
2. Commands → scan → Run
3. Commands → doctor → Run
4. Commands → fix (--dry-run) → Run

## Критерий B.9

Новичок выполняет clone → scan → doctor → fix (или fix --dry-run) за ≤ 10 минут следуя этой инструкции.
