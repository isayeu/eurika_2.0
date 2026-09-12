"""POST /api/exec whitelist for Stage 3–5 CLI surfaces."""
from __future__ import annotations

from pathlib import Path

from eurika.api.serve_exec import EXEC_WHITELIST, exec_eurika_command


def test_exec_whitelist_includes_self_model_hypotheses_ab() -> None:
    assert {"self-model", "hypotheses", "ab-compare", "init"} <= EXEC_WHITELIST


def test_exec_hypotheses_runs(tmp_path: Path) -> None:
    (tmp_path / ".eurika").mkdir()
    out = exec_eurika_command(tmp_path, "hypotheses --json", timeout=60)
    assert out.get("exit_code") == 0, out
    assert out.get("ok") is True
    assert "error" not in out or not out.get("error")
    assert "rank" in (out.get("stdout") or "").lower() or "hypothesis" in (out.get("stdout") or "").lower() or "{" in (out.get("stdout") or "")


def test_exec_fix_allows_no_llm_flag(tmp_path: Path) -> None:
    # Normalization only — dry-run on empty project may still exit 0/1; flag must be accepted.
    out = exec_eurika_command(tmp_path, "fix --dry-run --no-llm -q", timeout=90)
    assert "flag not allowed" not in str(out.get("error") or "")


def test_exec_doctor_allows_quiet_flag(tmp_path: Path) -> None:
    out = exec_eurika_command(tmp_path, "doctor -q --no-llm", timeout=90)
    assert "flag not allowed" not in str(out.get("error") or "")
