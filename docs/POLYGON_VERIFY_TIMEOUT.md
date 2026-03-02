# Polygon verify timeout — диагноз

## Причина verify_fail для polygon

**Корневая причина:** verify (pytest) **превышает таймаут**, а не ошибка кода.

При `apply_and_verify` с планом только polygon:
- apply успешно (remove_unused_import применяется)
- verify запускает `pytest -q` на **всей** тест-сьюте
- pytest на полном прогоне занимает >90s (часто >300s)
- `verify command timed out after 90s` → success=False → rollback
- learning получает verify_fail, хотя фикс корректен

## Решение для тренировочных циклов

Использовать быстрый verify только для затронутых тестов. **Важно:** запускать через `python -m pytest`, иначе возможен `ModuleNotFoundError: architecture_pipeline` (другой sys.path).

```bash
eurika fix . --no-code-smells --allow-low-risk-campaign \
  --verify-cmd "python -m pytest tests/test_clean_imports_cli.py -q"
```

В `pyproject.toml` по умолчанию задан быстрый verify:

```toml
[tool.eurika]
verify_timeout = 300
verify_cmd = ".venv/bin/python -m pytest tests/test_clean_imports_cli.py tests/test_remove_unused_import.py -q"
```

Для полного прогона — переопределить: `--verify-cmd ".venv/bin/pytest tests/ -q"` или временно закомментировать `verify_cmd` в pyproject.

Либо env для разовой сессии:

```bash
EURIKA_VERIFY_TIMEOUT=600 eurika fix . --no-code-smells --allow-low-risk-campaign
```
