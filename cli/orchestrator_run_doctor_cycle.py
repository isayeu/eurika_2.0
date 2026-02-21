"""Extracted from parent module to reduce complexity."""
from pathlib import Path
from typing import Any
from cli.orchestration.doctor import run_doctor_cycle as _doctor_run_doctor_cycle

def run_doctor_cycle(path: Path, *, window: int=5, no_llm: bool=False, online: bool=False) -> dict[str, Any]:
    """Compatibility wrapper; delegated to orchestration.doctor."""
    return _doctor_run_doctor_cycle(path, window=window, no_llm=no_llm, online=online)