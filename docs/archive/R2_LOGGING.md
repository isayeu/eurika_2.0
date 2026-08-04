# R2 — Централизованное логирование

Централизованное логирование в критическом цикле (ROADMAP R2). Критерий: *отсутствуют «слепые» print-пути в критическом цикле*.

## 1. Orchestration (fix/doctor cycle)

Модули `eurika/orchestration/` и `cli/orchestration/` используют `get_logger`:

| Модуль | Logger | Статус |
|--------|--------|--------|
| doctor.py | `eurika.orchestration.doctor` | _log.info() |
| prepare.py | `eurika.orchestration.prepare` | _LOG |
| fix_cycle_impl.py | `eurika.orchestration.fix_cycle` | _LOG |
| full_cycle.py | `eurika.orchestration.full_cycle` | _LOG |
| apply_stage.py | `eurika.orchestration.apply_stage` | _LOG |
| hybrid_approval.py | `eurika.orchestration.hybrid_approval` | _LOG |

**Слепые print в orchestration:** 0.

## 2. Конфигурация

- `EURIKA_LOG_LEVEL` — DEBUG, INFO, WARNING, ERROR
- `configure_cli_logging(quiet=..., verbose=...)` — `--quiet` → WARNING, `--verbose` → DEBUG

## 3. Флаги

- `eurika doctor --quiet` / `eurika fix --quiet` / `eurika cycle --quiet` — прогресс скрыт
- `--verbose` — DEBUG

## 4. Критерий R2 (чеклист)

- [x] doctor: progress через logging
- [x] architect: trace через logging
- [x] eurika.api get_patch_plan: trace через logging
- [x] core_handlers: doctor progress, _err, self-check через _clog
- [x] orchestration: prepare, apply_stage, fix_cycle, full_cycle — get_logger
- [x] runtime_scan, agent_handlers — через logging

## 5. CLI output vs logging

- **stdout** — преднамеренный вывод (report, learning-kpi, doctor report). Не заменяется на logging.
- **stderr** — ошибки в core_handlers/agent_handlers; допустимо.

## 6. Progress traces (diagnose)

При `eurika fix` / `eurika doctor` шаг diagnose выводит: architect (LLM), planner hints, время ожидания.
