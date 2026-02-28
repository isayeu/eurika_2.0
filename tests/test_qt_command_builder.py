from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qt_app.services.command_builder import build_cli_args


def test_build_cli_args_scan() -> None:
    args = build_cli_args(command="scan", project_root=".")
    assert args[0] == "scan"
    assert args[1] == str(Path(".").resolve())


def test_build_cli_args_explain_requires_module() -> None:
    with pytest.raises(ValueError):
        build_cli_args(command="explain", project_root=".", module="")


def test_build_cli_args_fix_options() -> None:
    args = build_cli_args(
        command="fix",
        project_root=".",
        window=7,
        dry_run=True,
        no_clean_imports=True,
    )
    assert "--window" in args
    assert "7" in args
    assert "--dry-run" in args
    assert "--no-clean-imports" in args


def test_build_cli_args_doctor_no_llm() -> None:
    args = build_cli_args(
        command="doctor",
        project_root=".",
        window=5,
        no_llm=True,
    )
    assert args[0] == "doctor"
    assert "--no-llm" in args
    assert "--window" in args


def test_doctor_no_llm_runs_from_ui_args() -> None:
    """Verify doctor --no-llm completes when invoked as the Qt UI would."""
    args = build_cli_args(
        command="doctor",
        project_root=str(ROOT),
        window=5,
        no_llm=True,
    )
    full_args = [sys.executable, "-m", "eurika_cli"] + args
    result = subprocess.run(
        full_args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, f"doctor --no-llm failed: {result.stderr}"

