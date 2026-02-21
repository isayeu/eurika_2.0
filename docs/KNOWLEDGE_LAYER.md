# Knowledge Layer — проектирование (после 1.0)

По **review.md**: онлайн-ресурсы и внешний knowledge подключаются **только после** детерминированного ядра (Patch Engine, Verify, rollback). Иначе — хаос и потеря воспроизводимости.

## Контракт

Не «LLM + поиск в интернете», а **Knowledge Provider Layer**.

```python
class KnowledgeProvider(ABC):
    def query(self, topic: str) -> StructuredKnowledge: ...
```

**StructuredKnowledge** — структурированный ответ (источник, фрагменты, метаданные), не сырой HTML.

## Провайдеры (по review)

| Провайдер | Назначение |
|-----------|------------|
| **LocalKnowledgeProvider** | Локальный кэш, сохранённые сниппеты документации |
| **OfficialDocsProvider** | Официальная документация по фиксированному allow-list URL (topic → url); запрос через stdlib urllib, без произвольного поиска. |
| **ReleaseNotesProvider** | Release notes / What's New по фиксированному allow-list URL (topic → url), stdlib urllib. |
| **StaticAnalyzerProvider** | Результаты mypy, pylint, flake8, AST-проверки |

StackOverflow — слабый источник для автономного агента. Официальная документация — сильный.

## Схема интеграции

```
LLM → формулирует гипотезу
  ↓
Knowledge layer → query(topic) через выбранный провайдер
  ↓
LLM → уточняет план с учётом StructuredKnowledge
  ↓
Patch engine → применяет детерминированный патч
  ↓
Verify stage
```

## Где даёт эффект (review)

1. **Обновление зависимостей** — устаревшие API, breaking changes.
2. **Синтаксические патчи** — актуальная версия Python (по умолчанию 3.14), новые async-паттерны.
3. **Безопасность** — уязвимости, deprecated.

## Реализация

- **eurika.knowledge** — пакет: `KnowledgeProvider`, `StructuredKnowledge`, `LocalKnowledgeProvider` (JSON-кэш), **OfficialDocsProvider** (опционально запрос по curated URL: `OFFICIAL_DOCS_TOPIC_URLS`, например `python_3_14`/whatsnew; stdlib urllib, timeout 5s), **ReleaseNotesProvider** (curated URL, как OfficialDocs); заглушка `StaticAnalyzerProvider`. **Кэширование сетевых ответов (2.2.2):** при указании `cache_dir` (например `path/.eurika/knowledge_cache`) и `ttl_seconds` (по умолчанию 24h) провайдеры сохраняют результат fetch в JSON; при повторном doctor без сети или в пределах TTL используется сохранённый контент.
- **Интеграция:** команды `doctor` и `architect` используют **CompositeKnowledgeProvider**: Local (eurika_knowledge.json) + OfficialDocsProvider + ReleaseNotesProvider. Фрагменты от всех провайдеров объединяются; в заголовке фрагмента указывается источник (`[local]`, `[official_docs]`, `[release_notes]`). Темы по умолчанию: `python`, `python_3_14` (чтобы OfficialDocs/ReleaseNotes подтягивали актуальный What's New по сети), при циклах — `cyclic_imports`, при рисках — `architecture_refactor`; либо задаются через `EURIKA_KNOWLEDGE_TOPIC`.

### Формат локального кэша (eurika_knowledge.json)

Файл в корне проекта (опционально). Формат:

```json
{
  "topics": {
    "python": [
      { "title": "PEP 701", "content": "f-strings can contain quotes." },
      { "title": "What's New 3.14", "content": "..." }
    ],
    "python_3_14": [ { "title": "...", "content": "..." } ]
  }
}
```

Ключ темы нормализуется: пробелы → `_`, lowercase. Запрос по теме `"PEP 701"` ищет ключ `pep_701`.

**Пример файла:** скопируйте `docs/eurika_knowledge.example.json` в корень проекта как `eurika_knowledge.json` и при необходимости отредактируйте. Темы в примере: `python`, `python_3_14`, `architecture_refactor`, `deprecated_api`, `typing`, `cyclic_imports`, `version_migration`, `security`, `async_patterns`.

### Кэш сетевых ответов (.eurika/knowledge_cache)

При `eurika doctor` и `eurika architect` провайдеры OfficialDocs и ReleaseNotes сохраняют ответы по URL в `path/.eurika/knowledge_cache/`. TTL — 24 часа. При повторном запуске без сети или в пределах TTL используется сохранённый контент. Каталог `.eurika/` в `.gitignore`.

### Online Knowledge (ROADMAP 3.0.3)

- **`--online`** — в `eurika doctor`, `eurika cycle`, `eurika fix`, `eurika architect`: принудительный свежий fetch, bypass кэша. Используйте при обновлении документации или для актуальных PEP/Release Notes.
- **EURIKA_KNOWLEDGE_TTL** — TTL кэша в секундах (по умолчанию 86400 = 24h).
- **EURIKA_KNOWLEDGE_RATE_LIMIT** — минимальный интервал между сетевыми запросами в секундах. При `--online` по умолчанию 1.0; без `--online` — 0 (нет лимита).

См. также **review.md** (блок «Онлайн-ресурсы / Knowledge Layer»), **ROADMAP.md** (§ После 1.0).
