"""QG-2 integration flow: decision gate + campaign checkpoint + undo."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _extract_last_json(stdout: str) -> dict:
    last_brace = stdout.rfind("}")
    assert last_brace >= 0, f"no JSON found in output: {stdout[:300]}"
    depth = 1
    start = last_brace
    for i in range(last_brace - 1, -1, -1):
        c = stdout[i]
        if c == "}":
            depth += 1
        elif c == "{":
            depth -= 1
            if depth == 0:
                start = i
                break
    return json.loads(stdout[start : last_brace + 1])


def test_fix_apply_with_approve_subset_and_campaign_undo(tmp_path: Path) -> None:
    """Apply subset by index, create checkpoint, then undo campaign and restore files."""
    proj = tmp_path / "proj"
    proj.mkdir()
    a = proj / "a.py"
    b = proj / "b.py"
    a.write_text("import os\n\n\ndef value_a() -> int:\n    return 1\n", encoding="utf-8")
    b.write_text("import sys\n\n\ndef value_b() -> int:\n    return 2\n", encoding="utf-8")
    (proj / "tests").mkdir()
    (proj / "tests" / "test_proj.py").write_text(
        "from a import value_a\nfrom b import value_b\n\n\ndef test_values():\n    assert value_a() == 1 and value_b() == 2\n",
        encoding="utf-8",
    )
    (proj / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8")

    before_a = a.read_text(encoding="utf-8")
    before_b = b.read_text(encoding="utf-8")

    fix = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "fix", "--quiet", "--approve-ops", "1", str(proj)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert fix.returncode == 0, f"stderr: {fix.stderr}\nstdout: {fix.stdout[:800]}"
    report = _extract_last_json(fix.stdout)

    cp = report.get("campaign_checkpoint") or {}
    assert cp.get("checkpoint_id"), f"missing checkpoint in report: {report}"
    assert cp.get("run_ids"), f"missing run_ids in checkpoint payload: {cp}"
    summary = report.get("decision_summary") or {}
    assert int(summary.get("blocked_by_human") or 0) >= 1
    skipped = report.get("skipped_reasons") or {}
    assert any(str(v) == "not_in_approved_set" for v in skipped.values())

    changed_after_apply = []
    if a.read_text(encoding="utf-8") != before_a:
        changed_after_apply.append("a.py")
    if b.read_text(encoding="utf-8") != before_b:
        changed_after_apply.append("b.py")
    assert changed_after_apply, "expected one file changed by apply"

    checkpoint_id = str(cp.get("checkpoint_id"))
    undo = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "campaign-undo", str(proj), "--checkpoint-id", checkpoint_id],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert undo.returncode == 0, f"stderr: {undo.stderr}\nstdout: {undo.stdout[:800]}"
    undo_out = _extract_last_json(undo.stdout)
    assert undo_out.get("status") == "undone"
    restored = [str(x) for x in (undo_out.get("restored") or [])]
    assert restored, f"expected restored files in undo output: {undo_out}"
    for rel in changed_after_apply:
        assert rel in restored

    # Contents are restored to pre-apply state.
    assert a.read_text(encoding="utf-8") == before_a
    assert b.read_text(encoding="utf-8") == before_b
