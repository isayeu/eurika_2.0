"""R3/R4 Quality Gates: edge-case matrix, dependency firewall (ROADMAP R3, R4)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_r4_dependency_firewall_passes() -> None:
    """R4: dependency firewall (layer + subsystem bypass) must pass in strict mode."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_dependency_guard.py", "tests/test_dependency_firewall.py", "-q", "--tb=short"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "EURIKA_STRICT_LAYER_FIREWALL": "1"},
    )
    assert result.returncode == 0, (
        f"R4 dependency firewall failed (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_r3_edge_case_matrix_passes() -> None:
    """R3: edge-case tests (empty/huge input, model error, memory) must pass."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "edge_case", "-q", "--tb=short"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"pytest -m edge_case failed (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
