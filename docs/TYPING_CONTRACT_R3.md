# R3 Typing Contract — mypy optional-gate

**Цель:** ошибки типов не накапливаются в core-контрактах.

## Запуск

```bash
pip install -e ".[typecheck]"
mypy eurika cli
```

Или через pyproject-скрипт (если добавлен):

```bash
pip install -e ".[typecheck]"
python -m mypy eurika cli
```

## Конфигурация

`pyproject.toml` → `[tool.mypy]`:
- `follow_imports = "skip"` — не проверять сторонние пакеты
- `check_untyped_defs = true`
- `disallow_incomplete_defs = true`
- Список модулей в `[[tool.mypy.overrides]]` — строгая проверка core

## CI

Рекомендуется добавить в CI (опционально, не блокирует merge):

```yaml
- run: pip install -e ".[typecheck]" && mypy eurika cli
```
