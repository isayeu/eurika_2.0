"""RV3: Reasoning consolidation — analyzer, generator, evaluator (TARGET_V3_STRUCTURE)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_reasoning_analyzer_import() -> None:
    """RV3: reasoning.analyzer exposes build_graph_and_summary."""
    from eurika.reasoning.analyzer import (
        build_graph_and_summary,
        build_graph_and_summary_from_self_map,
    )

    assert callable(build_graph_and_summary)
    assert callable(build_graph_and_summary_from_self_map)


def test_reasoning_generator_import() -> None:
    """RV3: reasoning.generator exposes generate_candidates, build_patch_operations."""
    from eurika.reasoning.generator import build_patch_operations, generate_candidates

    assert callable(generate_candidates)
    assert callable(build_patch_operations)


def test_reasoning_evaluator_import() -> None:
    """RV3: reasoning.evaluator exposes compute_delta."""
    from eurika.reasoning.evaluator import compute_delta

    assert callable(compute_delta)
