from pathlib import Path
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

