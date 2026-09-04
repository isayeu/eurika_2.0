"""Eurika training polygon — intentional issues for KPI learning cycles.

Каталог drills по одному файлу на drill. Запуск:
  eurika prove-cycle . --propose   (C.14: seed imports_ok → Approvals, без apply)
  eurika fix . --no-code-smells --allow-low-risk-campaign   (только remove_unused_import)
  eurika fix . --allow-low-risk-campaign                    (включая extract_block_to_helper по whitelist)

Для теста Approvals diff view (3.6.7): eurika fix . --team-mode --no-code-smells
  → Load plan в Qt → выбрать файл eurika/polygon/*.py → diff preview.
  Если polygon в campaign skip: EURIKA_IGNORE_CAMPAIGN=1 или --allow-low-risk-campaign.

Drills:
  - imports_ok: DRILL_UNUSED_IMPORTS (remove_unused_import)
  - extractable_block: DRILL_EXTRACTABLE_BLOCK (extract_block_to_helper)
  - long_function: DRILL_LONG_FUNCTION (extract_nested_function)
  - long_function_extractable_block: DRILL_LONG_FUNCTION_EXTRACTABLE (long_function + extract_block)
  - deep_nesting: DRILL_DEEP_NESTING (polygon_deep_nesting_extractable — extractable)
  - split_demo: DRILL_SPLIT (CR-E3 Composer practice — split модуля)
  - refactor_code_smell_drill: DRILL_REFACTOR_CODE_SMELL (long_function без extractable; REFACTOR_CODE_SMELL_PLAN Phase 2)
  - refactor_code_smell_if_chain: if/elif с return — блоки не extractable
  - refactor_code_smell_dict_builder: dict construction
  - refactor_code_smell_try_except: try/except с return
  - refactor_code_smell_format_chain: f-string chain
"""
from eurika.polygon.imports_ok import polygon_imports_ok
from eurika.polygon.extractable_block import polygon_extractable_block
from eurika.polygon.long_function import polygon_long_function
from eurika.polygon.long_function_extractable_block import polygon_long_function_extractable_block
from eurika.polygon.deep_nesting import polygon_deep_nesting, polygon_deep_nesting_extractable
from eurika.polygon.refactor_code_smell_drill import polygon_refactor_code_smell_drill
from eurika.polygon.refactor_code_smell_if_chain import polygon_refactor_code_smell_if_chain
from eurika.polygon.refactor_code_smell_dict_builder import polygon_refactor_code_smell_dict_builder
from eurika.polygon.refactor_code_smell_try_except import polygon_refactor_code_smell_try_except
from eurika.polygon.refactor_code_smell_format_chain import polygon_refactor_code_smell_format_chain
from eurika.polygon.split_demo import polygon_split_demo

__all__ = [
    "polygon_imports_ok",
    "polygon_extractable_block",
    "polygon_long_function",
    "polygon_long_function_extractable_block",
    "polygon_deep_nesting",
    "polygon_deep_nesting_extractable",
    "polygon_refactor_code_smell_drill",
    "polygon_refactor_code_smell_if_chain",
    "polygon_refactor_code_smell_dict_builder",
    "polygon_refactor_code_smell_try_except",
    "polygon_refactor_code_smell_format_chain",
    "polygon_split_demo",
]
