# R2 — Централизованное логирование

## Что сделано

Критический цикл (doctor, fix, architect, orchestration) переведён на единый logging-контур. «Слепые» `print` заменены на `logging`.

### Изменённые модули

| Модуль | Было | Стало |
|--------|------|-------|
| `cli/orchestration/doctor.py` | `print(..., sys.stderr)` | `get_logger("orchestration.doctor").info()` |
| `eurika/reasoning/architect.py` | `print(..., sys.stderr)` | `logging.getLogger("eurika.reasoning.architect").info()` |
| `eurika/api/__init__.py` | `print(..., sys.stderr)` | `logging.getLogger("eurika.api").info()` |
| `cli/core_handlers.py` | `print(..., sys.stderr)` (doctor progress) | `get_logger("core_handlers").info()` |

### Конфигурация

- **`cli/orchestration/logging.py`**
  - `configure_cli_logging(quiet=..., verbose=...)` — вызывается при dispatch
  - `--quiet` → уровень WARNING (прогресс скрыт)
  - `--verbose` → уровень DEBUG
  - `EURIKA_LOG_LEVEL` (env) → приоритет, если не заданы флаги

### Флаги

- `eurika doctor --quiet` — только stdout-репорт, без прогресса
- `eurika doctor --verbose` — DEBUG-сообщения
- `eurika fix --quiet` / `eurika cycle --quiet` — как раньше
- `eurika fix --verbose` / `eurika cycle --verbose` — verbose

### Критерий R2

> Отсутствуют «слепые» print-пути в критическом цикле.

- [x] doctor: progress через logging
- [x] architect: trace через logging
- [x] eurika.api get_patch_plan: trace через logging
- [x] core_handlers doctor: progress через logging
- [x] orchestration (prepare, apply_stage, fix_cycle, full_cycle) уже использовали get_logger
- [x] runtime_scan: "self_map.json written" через eurika.scan logger
- [x] core_handlers: _err, self-check, fix/cycle project headers через _clog
- [x] agent_handlers: fix summary, decision summary, verify-failure help, _run_cycle_with_mode через _ALOG
