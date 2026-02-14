"""Tests for architecture_learning module."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from architecture_learning import LearningStore  # noqa: E402


def test_learning_store_append_and_aggregate(tmp_path: Path) -> None:
    store = LearningStore(storage_path=tmp_path / "architecture_learning.json")

    store.append(
        project_root=tmp_path,
        modules=["m1.py"],
        operations=[
            {"kind": "refactor_module", "target_file": "m1.py", "smell_type": "god_module"},
            {"kind": "introduce_facade", "target_file": "m2.py", "smell_type": "bottleneck"},
        ],
        risks=["god_module @ m1.py"],
        verify_success=True,
    )
    store.append(
        project_root=tmp_path,
        modules=["m2.py"],
        operations=[
            {"kind": "refactor_module", "target_file": "m2.py", "smell_type": "bottleneck"},
        ],
        risks=["bottleneck @ m2.py"],
        verify_success=False,
    )

    stats = store.aggregate_by_action_kind()
    assert stats["refactor_module"]["total"] == 2
    assert stats["refactor_module"]["success"] == 1
    assert stats["refactor_module"]["fail"] == 1
    assert stats["introduce_facade"]["total"] == 1
    assert stats["introduce_facade"]["success"] == 1

    by_smell = store.aggregate_by_smell_action()
    assert by_smell["god_module|refactor_module"]["total"] == 1
    assert by_smell["god_module|refactor_module"]["success"] == 1
    assert by_smell["bottleneck|introduce_facade"]["total"] == 1
    assert by_smell["bottleneck|refactor_module"]["total"] == 1
    assert by_smell["bottleneck|refactor_module"]["fail"] == 1
