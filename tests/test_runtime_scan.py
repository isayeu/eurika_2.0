import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_scan import run_scan


def test_run_scan_on_minimal_project(tmp_path: Path):
    # Create a minimal python project: one file with a trivial function.
    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "main.py").write_text("def foo():\n    return 42\n", encoding="utf-8")

    buf_out = io.StringIO()
    with redirect_stdout(buf_out):
        code = run_scan(project_root)

    out = buf_out.getvalue()
    assert code == 0
    # Basic sanity checks on output (report to stdout; self_map path may go to logger)
    assert "Eurika Scan Report" in out
    assert "Files:" in out

    # Check that artifacts were created (.eurika/ for memory, self_map in root)
    assert (project_root / "self_map.json").exists()
    assert (project_root / ".eurika" / "history.json").exists()
    assert (project_root / ".eurika" / "observations.json").exists()


def test_scan_excludes_venv_and_node_modules(tmp_path: Path):
    """venv, .venv, node_modules are excluded from scan."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "main.py").write_text("x = 1\n")
    (proj / "venv" / "lib" / "site-packages").mkdir(parents=True)
    (proj / "venv" / "lib" / "site-packages" / "foo.py").write_text("y = 2\n")
    (proj / "node_modules" / "pkg").mkdir(parents=True)
    (proj / "node_modules" / "pkg" / "bar.py").write_text("z = 3\n")

    from code_awareness import CodeAwareness

    aw = CodeAwareness(proj)
    files = aw.scan_python_files()
    paths = [str(p.relative_to(proj)) for p in files]
    assert "main.py" in paths
    assert not any("venv" in p for p in paths)
    assert not any("node_modules" in p for p in paths)

