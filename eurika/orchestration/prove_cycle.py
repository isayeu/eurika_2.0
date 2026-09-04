"""Deterministic closed-loop proof: patch → verify → learning (no LLM, no approvals).

Proves that Eurika's execution stack works end-to-end on a synthetic drill file
under `.eurika/prove_cycle/`. Use before trusting full `eurika fix` on production code.

C.14 HITL mode (`propose=True` / CLI `--propose [--drill …]`): seed a polygon
drill (`imports` or `extractable_block`), park one op in Approvals, do not apply.
Human approves → `eurika fix . --apply-approved`.
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
from .team_mode import PENDING_PLAN_FILE, save_pending_plan

DRILL_REL_PATH = ".eurika/prove_cycle/drill_unused.py"
POLYGON_IMPORTS_REL = "eurika/polygon/imports_ok.py"
POLYGON_EXTRACTABLE_REL = "eurika/polygon/extractable_block.py"
PROPOSE_DRILLS = ("imports", "extractable_block")
DEFAULT_PROPOSE_DRILL = "imports"

_DRILL_SEED = '''import os
from pathlib import Path


def prove_drill_target() -> Path:
    """Synthetic target: remove_unused_import must drop `os`, keep Path."""
    return Path(".")
'''

_POLYGON_SEED = '''"""DRILL_UNUSED_IMPORTS: remove_unused_import — неиспользуемые импорты, fix удалит."""
import os
from pathlib import Path


def polygon_imports_ok() -> Path:
    """После fix остаётся только Path."""
    return Path(".")
'''

_POLYGON_EXTRACTABLE_SEED = '''"""DRILL_EXTRACTABLE_BLOCK: extract_block_to_helper — блок if с 5+ строками без return."""


def polygon_extractable_block(x: int) -> int:
    """Внутренний блок if (5+ строк) без return — подходит для suggest_extract_block.

    Нужно depth > 4 (5+ вложенных if) чтобы CodeAwareness пометил deep_nesting.
    """
    result = 0
    if x > 0:
        if x < 10:
            if x > 1:
                if x < 9:
                    a = x + 1
                    b = a * 2
                    c = b + x
                    d = c * 2
                    result = d
    return result
'''

_DRILL_DESCRIPTION = "Prove-cycle: remove unused import `os` from synthetic drill module."
_POLYGON_DESCRIPTION = (
    "C.14 polygon propose: remove unused import `os` from eurika/polygon/imports_ok.py"
)
_POLYGON_EXTRACTABLE_DESCRIPTION = (
    "C.14 polygon propose: extract_block_to_helper on "
    "eurika/polygon/extractable_block.py"
)


def normalize_propose_drill(drill: str | None) -> str:
    """Map aliases to a supported propose drill id."""
    raw = str(drill or DEFAULT_PROPOSE_DRILL).strip().lower().replace("-", "_")
    aliases = {
        "imports": "imports",
        "import": "imports",
        "imports_ok": "imports",
        "unused_import": "imports",
        "polygon_unused_import": "imports",
        "extractable_block": "extractable_block",
        "extractable": "extractable_block",
        "extract": "extractable_block",
        "extract_block": "extractable_block",
        "second": "extractable_block",
    }
    resolved = aliases.get(raw, raw)
    if resolved not in PROPOSE_DRILLS:
        raise ValueError(
            f"Unknown propose drill {drill!r}; expected one of {', '.join(PROPOSE_DRILLS)}"
        )
    return resolved


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


def seed_polygon_imports_ok(root: Path) -> Path:
    """Reseed polygon drill with unused `import os` for C.14 HITL propose."""
    root = root.resolve()
    target = root / POLYGON_IMPORTS_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_POLYGON_SEED, encoding="utf-8")
    return target


def seed_polygon_extractable_block(root: Path) -> Path:
    """Reseed extractable_block drill (inline body, no helper yet)."""
    root = root.resolve()
    target = root / POLYGON_EXTRACTABLE_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_POLYGON_EXTRACTABLE_SEED, encoding="utf-8")
    return target


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


def build_polygon_propose_operation(
    root: Path,
    *,
    drill: str = DEFAULT_PROPOSE_DRILL,
) -> OperationRecord:
    """Build a pending polygon op for Approvals (HITL)."""
    drill_id = normalize_propose_drill(drill)
    if drill_id == "extractable_block":
        return _build_extractable_propose_operation(root)
    seed_polygon_imports_ok(root)
    return {
        "target_file": POLYGON_IMPORTS_REL,
        "kind": "remove_unused_import",
        "smell_type": "unused_import",
        "params": {},
        "description": _POLYGON_DESCRIPTION,
        "approval_state": "pending",
        "critic_verdict": "allow",
        "decision_source": "prove_cycle_propose",
        "team_decision": "pending",
    }


def _build_extractable_propose_operation(root: Path) -> OperationRecord:
    from eurika.refactor.extract_function import suggest_extract_block

    seed_polygon_extractable_block(root)
    target = root.resolve() / POLYGON_EXTRACTABLE_REL
    suggestion = suggest_extract_block(
        target, "polygon_extractable_block", min_lines=5
    )
    if suggestion is None:
        raise RuntimeError(
            "suggest_extract_block found no extractable block in "
            f"{POLYGON_EXTRACTABLE_REL} after seed"
        )
    helper_name, block_line, _line_count, extra = suggestion
    return {
        "target_file": POLYGON_EXTRACTABLE_REL,
        "kind": "extract_block_to_helper",
        "smell_type": "deep_nesting",
        "params": {
            "location": "polygon_extractable_block",
            "block_start_line": int(block_line),
            "helper_name": str(helper_name),
            "extra_params": list(extra) if extra else [],
        },
        "description": _POLYGON_EXTRACTABLE_DESCRIPTION,
        "approval_state": "pending",
        "critic_verdict": "allow",
        "decision_source": "prove_cycle_propose",
        "team_decision": "pending",
    }


def run_prove_propose(
    project_root: Path,
    *,
    dry_run: bool = False,
    drill: str = DEFAULT_PROPOSE_DRILL,
) -> dict[str, Any]:
    """Seed polygon drill and park the op in Approvals; never apply."""
    path = Path(project_root).resolve()
    try:
        drill_id = normalize_propose_drill(drill)
    except ValueError as exc:
        return {
            "ok": False,
            "prove_cycle": True,
            "propose": True,
            "error": str(exc),
            "modified": [],
            "verify_success": None,
            "return_code": 1,
        }
    if dry_run:
        if drill_id == "extractable_block":
            preview: OperationRecord = {
                "target_file": POLYGON_EXTRACTABLE_REL,
                "kind": "extract_block_to_helper",
                "smell_type": "deep_nesting",
                "params": {"location": "polygon_extractable_block"},
                "description": _POLYGON_EXTRACTABLE_DESCRIPTION,
                "approval_state": "pending",
                "critic_verdict": "allow",
                "decision_source": "prove_cycle_propose",
                "team_decision": "pending",
            }
            drill_name = "polygon_extractable_block"
            target_rel = POLYGON_EXTRACTABLE_REL
        else:
            preview = {
                "target_file": POLYGON_IMPORTS_REL,
                "kind": "remove_unused_import",
                "smell_type": "unused_import",
                "params": {},
                "description": _POLYGON_DESCRIPTION,
                "approval_state": "pending",
                "critic_verdict": "allow",
                "decision_source": "prove_cycle_propose",
                "team_decision": "pending",
            }
            drill_name = "polygon_unused_import"
            target_rel = POLYGON_IMPORTS_REL
        return {
            "ok": True,
            "dry_run": True,
            "prove_cycle": True,
            "propose": True,
            "drill": drill_name,
            "drill_id": drill_id,
            "target_file": target_rel,
            "pending_plan": PENDING_PLAN_FILE,
            "operations": [preview],
            "modified": [],
            "verify_success": None,
            "return_code": 0,
            "seeded_has_unused_import": None,
        }
    try:
        operation = build_polygon_propose_operation(path, drill=drill_id)
    except Exception as exc:
        return {
            "ok": False,
            "prove_cycle": True,
            "propose": True,
            "drill_id": drill_id,
            "error": str(exc),
            "modified": [],
            "verify_success": None,
            "return_code": 1,
        }
    operations: list[OperationRecord] = [operation]
    patch_plan: PatchPlan = {"operations": operations}
    target_rel = str(operation.get("target_file") or "")
    seeded = path / target_rel
    seeded_text = seeded.read_text(encoding="utf-8") if seeded.is_file() else ""
    pending_path = save_pending_plan(
        path,
        patch_plan,
        operations,
        policy_decisions=[{"index": 1, "decision": "allow", "reason": "prove_cycle_propose"}],
        session_id=f"prove_cycle_propose_{drill_id}",
    )
    try:
        pending_rel = str(pending_path.relative_to(path))
    except ValueError:
        pending_rel = str(pending_path)
    drill_name = (
        "polygon_extractable_block"
        if drill_id == "extractable_block"
        else "polygon_unused_import"
    )
    return {
        "ok": True,
        "prove_cycle": True,
        "propose": True,
        "drill": drill_name,
        "drill_id": drill_id,
        "target_file": target_rel,
        "pending_plan": pending_rel,
        "pending_plan_path": str(pending_path),
        "operations": operations,
        "modified": [],
        "verify_success": None,
        "return_code": 0,
        "seeded_has_unused_import": (
            "import os" in seeded_text if drill_id == "imports" else None
        ),
        "seeded_extractable": (
            "_extracted_block_" not in seeded_text
            if drill_id == "extractable_block"
            else None
        ),
        "instructions": (
            "Review Approvals / .eurika/pending_plan.json, set team_decision=approve, "
            "then: eurika fix . --apply-approved"
        ),
    }


def run_prove_cycle(
    project_root: Path,
    *,
    dry_run: bool = False,
    quiet: bool = False,
    verify_timeout: int | None = 60,
    propose: bool = False,
    drill: str = DEFAULT_PROPOSE_DRILL,
) -> dict[str, Any]:
    """
    Run one deterministic prove cycle on project_root.

    Returns fix-cycle style payload with verify_success, modified, delta_score.
    With propose=True: seed polygon + save pending plan (HITL), no apply.
    """
    if propose:
        return run_prove_propose(project_root, dry_run=dry_run, drill=drill)

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

    result = type(
        "ProveAgentResult",
        (),
        {
            "output": {
                "policy_decisions": [{"decision": "allow", "reason": "prove_cycle"}],
                "critic_decisions": [],
                "summary": {"risks": []},
                "execution_context": None,
            },
        },
    )()

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
    if payload.get("propose"):
        drill_label = payload.get("drill") or "polygon"
        target = payload.get("target_file") or POLYGON_IMPORTS_REL
        lines = [
            "## Prove propose (polygon → Approvals HITL)",
            "",
            f"- drill: `{drill_label}` → `{target}`",
            f"- drill_id: `{payload.get('drill_id') or DEFAULT_PROPOSE_DRILL}`",
            f"- pending_plan: `{payload.get('pending_plan') or PENDING_PLAN_FILE}`",
            "- modified: (none — waiting for approve)",
        ]
        if payload.get("seeded_has_unused_import") is not None:
            lines.append(
                f"- seeded unused `os`: **{payload.get('seeded_has_unused_import')}**"
            )
        if payload.get("seeded_extractable") is not None:
            lines.append(
                f"- seeded extractable (no helper yet): **{payload.get('seeded_extractable')}**"
            )
        if payload.get("error"):
            lines.append(f"- error: {payload.get('error')}")
        if payload.get("dry_run"):
            lines.append("- dry-run: pending plan not written; re-run without `--dry-run`")
        else:
            lines.append(
                "- next: Approvals → approve → `eurika fix . --apply-approved` "
                "(or edit `team_decision` in pending_plan.json)"
            )
        return "\n".join(lines)

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
