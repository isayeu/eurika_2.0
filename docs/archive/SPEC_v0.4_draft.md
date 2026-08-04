# Eurika 2.0 — SPECIFICATION (v0.4 draft)

## 1. Назначение v0.4

v0.4 строится поверх:

- **v0.1** — Architecture Awareness Engine (scan → analyze → explain → log);
- **v0.2** — AgentCore (arch_review, arch_evolution_query, feedback);
- **v0.3** — Prioritization (prioritize_modules, architecture_planner).

Цель v0.4:

- добавить **слой действий**: ActionPlan, PatchPlan, применение с бэкапами и verify;
- **Learning Loop**: учёт исходов patch-apply + verify для коррекции ожидаемой пользы;
- **Rescan**: сравнение архитектуры до/после применения;
- при этом **модификация кода — только opt-in** (явный `--apply`), с бэкапами и rollback.

## 2. Граница возможностей v0.4

### 2.1 Что добавляет v0.4

- **Action Plan**: структурированный список действий (type, target, description, risk, expected_benefit); dry-run через ExecutorSandbox без изменения кода; **execute** — реальное выполнение (конвертация в patch и apply_patch_plan, бэкапы в .eurika_backups).
- **Patch Plan**: операции по файлам (target_file, kind, smell_type, diff); diff — текстовые подсказки (TODO-блоки), с шаблонами по паре (smell_type, action_kind).
- **Patch Apply**: применение diff к файлам; бэкапы в `.eurika_backups/<run_id>/`; опционально pytest после apply; пропуск операции, если diff уже присутствует в файле.
- **Rollback**: восстановление из бэкапа по run_id.
- **Learning Store**: запись после patch-apply --apply --verify; агрегация по action_kind и по паре (smell_type, action_kind); использование в planner для коррекции expected_benefit.
- **Cycle**: цепочка scan → arch-review → patch-apply --apply --verify; при успехе verify — rescan и сравнение до/после (rescan_diff в отчёте); при падении тестов — подсказка по rollback.
- **Cycle --dry-run**: только scan → arch-review → patch-plan (без apply/verify).
- **Cycle --quiet**: подавление вывода scan/arch; только итоговый JSON на stdout.

### 2.2 Чего v0.4 по-прежнему НЕ делает

- **не** применяет изменения без явного `--apply`;
- **не** выполняет произвольный код/shell;
- **не** меняет логику без бэкапа (при apply бэкап создаётся по умолчанию);
- patch-операции — только **добавление текста** (diff) в конец файла; никакого парсинга unified diff или AST-редактирования.

## 3. Позиция v0.4 относительно v0.3

v0.3 даёт приоритизацию и план (PlanStep, suggest_refactor_plan, suggest_patch_plan как предложения).

v0.4 добавляет:

- **исполнение плана** (patch-apply с бэкапами и verify);
- **обучение на результатах** (LearningStore, aggregate_by_smell_action);
- **измерение эффекта** (rescan, rescan_diff).

Это уровень **действия с защитой**: человек явно включает `--apply`, система создаёт бэкап и может откатить.

## 4. Базовые сущности v0.4

### 4.1 Action Plan

```python
# action_plan.py
@dataclass
class Action:
    type: str       # refactor_module, introduce_facade, refactor_dependencies
    target: str
    description: str
    risk: float
    expected_benefit: float

@dataclass
class ActionPlan:
    actions: List[Action]
    priority: List[int]
    total_risk: float
    expected_gain: float
```

- Строится из ArchitecturePlan через `architecture_planner.build_action_plan`.
- При наличии LearningStore: для пар (smell_type, action_kind) с success_rate ≥ 0.5 ожидаемая польза слегка повышается.

### 4.2 Patch Plan

```python
# patch_plan.py
@dataclass
class PatchOperation:
    target_file: str
    kind: str          # refactor_module, introduce_facade, refactor_dependencies
    description: str
    diff: str          # текст для добавления в конец файла
    smell_type: Optional[str] = None  # для learning по (smell_type, action_kind)

@dataclass
class PatchPlan:
    project_root: str
    operations: List[PatchOperation]
```

- Строится через `architecture_planner.build_patch_plan`; шаблоны diff заданы в `DIFF_HINTS` по (smell_type, action_kind).
- При передаче `learning_stats` (например, из LearningStore.aggregate_by_smell_action) операции в плане **сортируются по убыванию success rate** пары (smell_type, action_kind) — сначала те, по которым в прошлом чаще проходил verify.

### 4.3 Patch Apply

- Вход: project_root, plan (dict), dry_run, backup.
- Выход: `{ dry_run, modified, skipped, errors, backup_dir, run_id }`.
- При backup: копии файлов в `project_root/.eurika_backups/<run_id>/`.
- Если `diff.strip()` уже содержится в файле — операция пропускается (файл в `skipped`).

### 4.4 Learning Store

- Файл: `architecture_learning.json`.
- Запись: после patch-apply --apply --verify (modules, operations, risks, verify_success).
- Агрегаты: `aggregate_by_action_kind()`, `aggregate_by_smell_action()` — ключи вида `smell_type|action_kind`, значения `{ total, success, fail }`.

### 4.5 Rescan

- Перед apply: копия `self_map.json` → `.eurika_backups/self_map_before.json`.
- После успешного verify: повторный run_scan; diff между старым и новым self_map через `architecture_diff.diff_snapshots`.
- В отчёт cycle добавляется `rescan_diff`: structures, smells, maturity, centrality_shifts.

## 5. CLI v0.4

| Команда | Назначение |
|--------|------------|
| `eurika agent action-dry-run [path]` | ActionPlan из диагностики, вывод без выполнения |
| `eurika agent action-simulate [path]` | ActionPlan + ExecutorSandbox.dry_run |
| `eurika agent action-apply [path]` [--no-backup] | ActionPlan + ExecutorSandbox.execute (append TODO, backup по умолчанию) |
| `eurika agent patch-plan [path]` [-o FILE] | Patch plan (JSON или в файл) |
| `eurika agent patch-apply [path]` [--apply] [--verify] [--no-backup] | Применение; по умолчанию dry-run |
| `eurika agent patch-rollback [path]` [--run-id] [--list] | Восстановление из бэкапа |
| `eurika agent cycle [path]` [--dry-run] [--quiet] [--window N] | Полный цикл с опциональным rescan |
| `eurika agent learning-summary [path]` | by_action_kind + by_smell_action |

## 6. Ограничения безопасности v0.4

- Изменение файлов только при явном `--apply`.
- При apply по умолчанию создаётся бэкап; откат через patch-rollback.
- Никакого выполнения произвольного кода; verify — только запуск pytest в проекте.
- Learning — только чтение/запись локального `architecture_learning.json`.

## 7. Критерии успеха v0.4

v0.4 достигнута, если:

- инженер может выполнить полный цикл: scan → arch-review → patch-apply --apply --verify и при успехе получить rescan_diff;
- при падении тестов выводится подсказка по rollback с run_id;
- learning-summary показывает агрегаты по action_kind и по (smell_type, action_kind);
- cycle --dry-run и cycle --quiet работают как описано.
