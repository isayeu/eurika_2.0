"""Tests for eurika self-check command (self-analysis ritual)."""

import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli.handlers import handle_self_check


def test_self_check_on_minimal_project(tmp_path: Path):
    """self-check runs scan successfully on a minimal project."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "main.py").write_text("def foo():\n    return 42\n", encoding="utf-8")

    class Args:
        path = project_root

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        code = handle_self_check(Args())

    out = buf_out.getvalue()
    err = buf_err.getvalue()

    assert code == 0
    assert "eurika: self-check" in err and "analyzing project architecture" in err
    assert "Eurika Scan Report" in out
    assert (project_root / "self_map.json").exists()


def test_self_check_on_self():
    """self-check runs successfully on Eurika project root."""
    class Args:
        path = ROOT

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        code = handle_self_check(Args())

    assert code == 0
    assert "self-check" in buf_err.getvalue()
    assert "Architecture" in buf_out.getvalue()
