"""Deterministic closed-loop proof: patch → verify → learning (no LLM, no approvals).

Proves that Eurika's execution stack works end-to-end on a synthetic drill file
under `.eurika/prove_cycle/`. Use before trusting full `eurika fix` on production code.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import Any

from .apply_stage import (
    build_fix_cycle_result,
    build_fix_dry_run_result,
    execute_fix_apply_stage,
)
from .contracts import OperationRecord, PatchPlan
from .deps import load_fix_cycle_deps
from .pipeline_model import PipelineStage, attach_pipeline_trace

DRILL_REL_PATH = ".eurika/prove_cycle/drill_unused.py"

_DRILL_SEED = '''import os
from pathlib import Path


def prove_drill_target() -> Path:
    """Synthetic target: remove_unused_import must drop `os`, keep Path."""
    return Path(".")
'''

_DRILL_DESCRIPTION = "Prove-cycle: remove unused import `os` from synthetic drill module."


_VERIFY_SCRIPT = '''"""Verify prove-cycle unused_import drill."""
from __future__ import annotations

import ast
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    drill = root / ".eurika/prove_cycle/drill_unused.py"
    if not drill.is_file():
        print(f"drill missing: {drill}", file=sys.stderr)
        return 1
    tree = ast.parse(drill.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    if "os" in names:
        print("os still imported", file=sys.stderr)
        return 1
    if "Path" not in names:
        print("Path import missing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _ensure_verify_script(root: Path) -> Path:
    root = root.resolve()
    script = root / ".eurika/prove_cycle/_verify_unused_import.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    if not script.exists() or script.read_text(encoding="utf-8") != _VERIFY_SCRIPT:
        script.write_text(_VERIFY_SCRIPT, encoding="utf-8")
    return script


def _drill_verify_cmd(root: Path) -> str:
    script = _ensure_verify_script(root)
    return " ".join(shlex.quote(x) for x in [sys.executable, str(script), str(root.resolve())])


def seed_prove_drill_file(root: Path) -> Path:
    """Create or refresh synthetic drill with an unused import."""
    root = root.resolve()
    drill_path = root / DRILL_REL_PATH
    drill_path.parent.mkdir(parents=True, exist_ok=True)
    drill_path.write_text(_DRILL_SEED, encoding="utf-8")
    return drill_path


def build_prove_operation(root: Path) -> OperationRecord:
    """Build a single remove_unused_import op for the drill file."""
    seed_prove_drill_file(root)
    return {
        "target_file": DRILL_REL_PATH,
        "kind": "remove_unused_import",
        "smell_type": "unused_import",
        "params": {},
        "description": _DRILL_DESCRIPTION,
        "approval_state": "approved",
        "critic_verdict": "allow",
        "decision_source": "prove_cycle",
    }


def run_prove_cycle(
    project_root: Path,
    *,
    dry_run: bool = False,
    quiet: bool = False,
    verify_timeout: int | None = 60,
) -> dict[str, Any]:
    """
    Run one deterministic prove cycle on project_root.

    Returns fix-cycle style payload with verify_success, modified, delta_score.
    """
    path = Path(project_root).resolve()
    operation = build_prove_operation(path)
    operations: list[OperationRecord] = [operation]
    patch_plan: PatchPlan = {"operations": operations}
    verify_cmd = _drill_verify_cmd(path)
    run_params = {
        "dry_run": dry_run,
        "prove_cycle": True,
        "runtime_mode": "auto",
        "verify_cmd": verify_cmd,
        "verify_timeout": verify_timeout,
    }

    result = type("ProveAgentResult", (), {
        "output": {
            "policy_decisions": [{"decision": "allow", "reason": "prove_cycle"}],
            "critic_decisions": [],
            "summary": {"risks": []},
            "execution_context": None,
        },
    })()

    if dry_run:
        dry = build_fix_dry_run_result(path, patch_plan, operations, result, run_params=run_params)
        dry["prove_cycle"] = True
        dry["drill"] = "unused_import"
        return dry

    deps = load_fix_cycle_deps()
    report, modified, verify_success = execute_fix_apply_stage(
        path,
        patch_plan,
        operations,
        session_id="prove_cycle",
        quiet=quiet,
        verify_cmd=verify_cmd,
        verify_timeout=verify_timeout,
        run_params=run_params,
        backup_dir=deps["BACKUP_DIR"],
        apply_and_verify=deps["apply_and_verify"],
        run_scan=deps["run_scan"],
        build_snapshot_from_self_map=deps["build_snapshot_from_self_map"],
        diff_architecture_snapshots=deps["diff_architecture_snapshots"],
        metrics_from_graph=deps["metrics_from_graph"],
        rollback_patch=deps["rollback_patch"],
        result=result,
    )
    attach_pipeline_trace(
        report,
        [PipelineStage.VALIDATE.value, PipelineStage.APPLY.value, PipelineStage.VERIFY.value],
    )
    out = build_fix_cycle_result(report, operations, modified, verify_success, result)
    out["prove_cycle"] = True
    out["drill"] = "unused_import"
    return out


def format_prove_cycle_summary(payload: dict[str, Any]) -> str:
    """Human-readable summary for CLI."""
    raw_report = payload.get("report")
    report: dict[str, Any] = raw_report if isinstance(raw_report, dict) else {}
    raw_verify = report.get("verify")
    verify: dict[str, Any] = raw_verify if isinstance(raw_verify, dict) else {}
    ok = payload.get("verify_success")
    if ok is None and verify:
        ok = verify.get("success")
    modified = payload.get("modified") or report.get("modified") or []
    delta = report.get("delta_score")
    lines = [
        "## Prove cycle (patch → verify → learning)",
        "",
        f"- drill: `unused_import` → `{DRILL_REL_PATH}`",
        f"- verify_success: **{ok}**",
        f"- modified: {', '.join(modified) if modified else '(none)'}",
    ]
    if delta is not None:
        lines.append(f"- delta_score: {delta}")
    if ok is True:
        lines.append("- learning: event appended (check `eurika learning-kpi .`)")
    elif payload.get("dry_run"):
        lines.append("- dry-run: no apply; re-run without `--dry-run` to execute")
    else:
        err = report.get("errors") or verify.get("stderr") or payload.get("error")
        if err:
            lines.append(f"- error: {str(err)[:500]}")
    return "\n".join(lines)
