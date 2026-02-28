# Stabilization feedback (v1.2.0)

Рунинг на реальных проектах для сбора наблюдений.

## Проекты

| Проект | scan | doctor | clean-imports | fix --dry-run | explain |
|--------|------|--------|---------------|---------------|---------|
| **farm_helper** | ✓ | ✓ | — | — | — |
| **rozygrysh** | ✓ | — | — | ✓ | — |
| **eurika** (v1) | ✓ | — | ✓ (4 файла) | — | ✓ |
| **eurika_2.0** | ✓ | — | — | ✓ | — |
| **optweb** | ✓* | — | — | — | — |

\* optweb: venv excluded, ~38 файлов, scan завершается.

## Наблюдения

### Ожидаемо

- **farm_helper, rozygrysh:** Dependencies: 0 — плоская структура или пакетный импорт (`from backend.x`) не разрешается в рёбра графа.
- **eurika v1:** god_module, bottleneck, hub — рекомендации осмысленны.
- **clean-imports:** нашёл 4 файла с unused импортами в eurika v1.
- **fix --dry-run:** создаёт split_module для god_module в eurika_2.0.
- **explain:** выводит роль, fan-in/fan-out, smells.

### Потенциальные улучшения

1. **Dependencies: 0** для farm_helper — возможно, self_map/import resolution не учитывает `from backend.models import X` как зависимость между backend/models.py и backend/main.py. Требует проверки логики self_map.
2. **optweb:** scan может быть медленным на Django-проектах с migrations (много файлов).

### Баги (исправлено в v1.2.1)

- **clean-imports --apply:** удалял импорты, нужные для `if TYPE_CHECKING:` и для `__all__` фасадов. Исправлено в remove_unused_import: учёт `TYPE_CHECKING` и имён из `__all__`.

## Дата

2025-02-14
