# R2 Logging

Централизованное логирование в критическом цикле (ROADMAP R2). Критерий: *отсутствуют «слепые» print-пути в критическом цикле*.

## Orchestration (fix/doctor cycle)

Модули `cli/orchestration/` используют `get_logger` из `cli/orchestration/logging.py`:

| Модуль | Logger | Статус |
|--------|--------|--------|
| doctor.py | `eurika.orchestration.doctor` | _log.info() |
| prepare.py | `eurika.orchestration.prepare` | _LOG |
| fix_cycle_impl.py | `eurika.orchestration.fix_cycle` | _LOG |
| full_cycle.py | `eurika.orchestration.full_cycle` | _LOG |
| apply_stage.py | `eurika.orchestration.apply_stage` | _LOG |
| hybrid_approval.py | `eurika.orchestration.hybrid_approval` | _LOG |

**Слепые print в orchestration:** 0. Все сообщения — через logging.

## CLI output vs logging

- **stdout** (json, text) — преднамеренный вывод команд (report, learning-kpi, doctor report). Не заменяется на logging.
- **stderr** (ошибки) — `print(..., file=sys.stderr)` в core_handlers/agent_handlers. Допустимо; при необходимости можно мигрировать на `logging.error`.

## Конфигурация

- `EURIKA_LOG_LEVEL` — DEBUG, INFO, WARNING, ERROR
- `configure_cli_logging(quiet=..., verbose=...)` — --quiet → WARNING, --verbose → DEBUG
