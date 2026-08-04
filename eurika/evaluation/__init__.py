"""
Evaluation layer — сравнение before/after (ROADMAP §5.7, Architecture target v3.x).

Только сравнение состояний. Без мутации, без записи.
"""

from .delta_evaluator import compute_delta

__all__ = ["compute_delta"]
