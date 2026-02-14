"""AgentCore-related CLI handlers.

Extracted from cli.handlers to reduce its size and fan-out.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from action_plan import ActionPlan
from agent_core import InputEvent
from agent_core_arch_review import ArchReviewAgentCore
from eurika.evolution.diff import diff_architecture_snapshots
from eurika.storage import ProjectMemory
from eurika.core.pipeline import build_snapshot_from_self_map
from executor_sandbox import ExecutorSandbox
from patch_apply import BACKUP_DIR, apply_patch_plan
from patch_engine import apply_and_verify, list_backups, rollback
from runtime_scan import run_scan


def handle_agent_arch_review(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return 1

    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(
        type="arch_review",
        payload={"path": str(path), "window": args.window},
        source="cli",
    )
    result = agent.handle(event)
    print(json.dumps(result.output, indent=2, ensure_ascii=False))
    return 0 if result.success else 1


def handle_agent_arch_evolution(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return 1

    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(
        type="arch_evolution_query",
        payload={"path": str(path), "window": args.window},
        source="cli",
    )
    result = agent.handle(event)
    print(json.dumps(result.output, indent=2, ensure_ascii=False))
    return 0 if result.success else 1


def handle_agent_prioritize_modules(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return 1

    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(
        type="arch_review",
        payload={"path": str(path), "window": args.window},
        source="cli",
    )
    result = agent.handle(event)
    if not result.success:
        print(json.dumps(result.output, indent=2, ensure_ascii=False))
        return 1

    proposals = result.output.get("proposals", [])
    prioritized = next(
        (p for p in proposals if p.get("action") == "prioritize_modules"), None
    )
    if not prioritized:
        print(
            "No prioritize_modules proposal available in AgentCore response.",
            file=sys.stderr,
        )
        return 1

    modules = prioritized.get("arguments", {}).get("modules", [])
    print(json.dumps({"modules": modules}, indent=2, ensure_ascii=False))
    return 0


def handle_agent_feedback_summary(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return 1

    memory = ProjectMemory(path)
    stats = memory.feedback.aggregate_by_action()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


def handle_agent_action_dry_run(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return 1

    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(
        type="arch_action_dry_run",
        payload={"path": str(path), "window": args.window},
        source="cli",
    )
    result = agent.handle(event)
    print(json.dumps(result.output, indent=2, ensure_ascii=False))
    return 0 if result.success else 1


def handle_agent_action_simulate(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return 1

    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(
        type="arch_action_simulate",
        payload={"path": str(path), "window": args.window},
        source="cli",
    )
    result = agent.handle(event)
    print(json.dumps(result.output, indent=2, ensure_ascii=False))
    return 0 if result.success else 1


def handle_agent_action_apply(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return 1

    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(
        type="arch_action_dry_run",
        payload={"path": str(path), "window": getattr(args, "window", 5)},
        source="cli",
    )
    result = agent.handle(event)
    if not result.success:
        print(json.dumps(result.output, indent=2, ensure_ascii=False))
        return 1

    proposals = result.output.get("proposals", [])
    action_plan_proposal = next(
        (p for p in proposals if p.get("action") == "suggest_action_plan"),
        None,
    )
    if not action_plan_proposal:
        print("No suggest_action_plan in response.", file=sys.stderr)
        return 1

    plan_dict = action_plan_proposal.get("arguments", {}).get("action_plan", {})
    if not plan_dict.get("actions"):
        print("Action plan has no actions.", file=sys.stderr)
        return 0

    plan = ActionPlan.from_dict(plan_dict)
    backup = not getattr(args, "no_backup", False)
    report = ExecutorSandbox(project_root=path).execute(plan, backup=backup)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not report.get("errors") else 1


def handle_agent_patch_plan(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return 1

    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(
        type="arch_review",
        payload={"path": str(path), "window": args.window},
        source="cli",
    )
    result = agent.handle(event)
    if not result.success:
        print(json.dumps(result.output, indent=2, ensure_ascii=False))
        return 1

    proposals = result.output.get("proposals", [])
    patch_proposal = next(
        (p for p in proposals if p.get("action") == "suggest_patch_plan"),
        None,
    )
    if not patch_proposal:
        print(
            "No suggest_patch_plan proposal in AgentCore response.",
            file=sys.stderr,
        )
        return 1

    patch_plan = patch_proposal.get("arguments", {}).get("patch_plan", {})
    out_path = getattr(args, "output", None)

    if out_path is not None:
        out_path = Path(out_path).resolve()
        out_path.write_text(
            json.dumps(patch_plan, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Patch plan written to {out_path}", file=sys.stderr)
    else:
        print(json.dumps({"patch_plan": patch_plan}, indent=2, ensure_ascii=False))
    return 0


def handle_agent_patch_apply(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return 1

    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(
        type="arch_review",
        payload={"path": str(path), "window": args.window},
        source="cli",
    )
    result = agent.handle(event)
    if not result.success:
        print(json.dumps(result.output, indent=2, ensure_ascii=False))
        return 1

    proposals = result.output.get("proposals", [])
    patch_proposal = next(
        (p for p in proposals if p.get("action") == "suggest_patch_plan"),
        None,
    )
    if not patch_proposal:
        print(
            "No suggest_patch_plan proposal in AgentCore response.",
            file=sys.stderr,
        )
        return 1

    patch_plan = patch_proposal.get("arguments", {}).get("patch_plan", {})
    dry_run = not getattr(args, "apply", False)
    backup = not getattr(args, "no_backup", False)
    if dry_run:
        report = apply_patch_plan(path, patch_plan, dry_run=True, backup=backup)
    elif getattr(args, "verify", False):
        report = apply_and_verify(path, patch_plan, backup=backup, verify=True)
        try:
            memory = ProjectMemory(path)
            summary = result.output.get("summary", {}) if result.success else {}
            risks = list(summary.get("risks", []))
            modules = list(report.get("modified", []))
            operations = list(patch_plan.get("operations", []))
            verify_success = report["verify"]["success"]
            memory.learning.append(
                project_root=path,
                modules=modules,
                operations=operations,
                risks=risks,
                verify_success=verify_success,
            )
            memory.events.append_event(
                type="patch",
                input={"operations_count": len(operations)},
                output={
                    "modified": report.get("modified", []),
                    "run_id": report.get("run_id"),
                    "verify_success": verify_success,
                },
                result=verify_success,
            )
        except Exception:
            pass
    else:
        report = apply_patch_plan(path, patch_plan, dry_run=False, backup=backup)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get("errors"):
        return 1
    if report.get("verify") and not report["verify"].get("success"):
        return 1
    return 0


def _print_fix_summary(
    operations: list,
    modified: list,
    verify_success: bool | None,
    dry_run: bool = False,
) -> None:
    """Print human-readable fix summary (Killer UX)."""
    kind_counts: dict[str, int] = {}
    for op in operations:
        k = op.get("kind") or "refactor_module"
        kind_counts[k] = kind_counts.get(k, 0) + 1
    parts = [f"{n} {k}" for k, n in sorted(kind_counts.items())]
    ops_str = ", ".join(parts) if parts else "0"
    print("--- Eurika fix complete ---", file=sys.stderr)
    if dry_run:
        print(f"Would apply: {ops_str}", file=sys.stderr)
        targets = [op.get("target_file", "?") for op in operations if op.get("target_file")]
        if targets:
            print(f"Targets: {', '.join(targets[:5])}{'...' if len(targets) > 5 else ''}", file=sys.stderr)
    else:
        print(f"Modified: {len(modified)} file(s) — {', '.join(modified[:5])}{'...' if len(modified) > 5 else ''}", file=sys.stderr)
        print(f"Operations: {ops_str}", file=sys.stderr)
        if kind_counts.get("remove_cyclic_import", 0) > 0:
            print(f"  → Broke {kind_counts['remove_cyclic_import']} cyclic dependency(ies)", file=sys.stderr)
        status = "✓ passed" if verify_success else "✗ failed"
        print(f"Verify: {status}", file=sys.stderr)
    print(file=sys.stderr)


def handle_agent_cycle(args: Any) -> int:
    """Run full cycle: scan → arch-review → patch-apply --apply --verify."""
    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return 1

    quiet = getattr(args, "quiet", False)

    if not quiet:
        print("--- Step 1/4: scan ---", file=sys.stderr)
        print("eurika fix: scan → diagnose → plan → patch → verify", file=sys.stderr)
    if quiet:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            if run_scan(path) != 0:
                return 1
    else:
        if run_scan(path) != 0:
            return 1

    if not quiet:
        print("--- Step 2/4: diagnose ---", file=sys.stderr)
    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(
        type="arch_review",
        payload={"path": str(path), "window": getattr(args, "window", 5)},
        source="cli",
    )
    result = agent.handle(event)
    if not result.success:
        print(json.dumps(result.output, indent=2, ensure_ascii=False))
        return 1

    proposals = result.output.get("proposals", [])
    patch_proposal = next(
        (p for p in proposals if p.get("action") == "suggest_patch_plan"),
        None,
    )
    if not patch_proposal:
        print(
            "No suggest_patch_plan proposal in AgentCore response. Cycle complete (nothing to apply).",
            file=sys.stderr,
        )
        return 0

    patch_plan = patch_proposal.get("arguments", {}).get("patch_plan", {})
    operations = patch_plan.get("operations", [])
    if not operations:
        print("Patch plan has no operations. Cycle complete.", file=sys.stderr)
        return 0

    if getattr(args, "dry_run", False):
        if not quiet:
            print("--- Step 3/3: plan (dry-run, no apply) ---", file=sys.stderr)
            _print_fix_summary(operations, modified=[], verify_success=None, dry_run=True)
        print(json.dumps({"patch_plan": patch_plan}, indent=2, ensure_ascii=False))
        return 0

    if not quiet:
        print("--- Step 3/4: patch & verify ---", file=sys.stderr)
    self_map_path = path / "self_map.json"
    rescan_before = path / BACKUP_DIR / "self_map_before.json"
    if self_map_path.exists():
        (path / BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        rescan_before.write_text(self_map_path.read_text(encoding="utf-8"), encoding="utf-8")

    report = apply_and_verify(path, patch_plan, backup=True, verify=True)

    if report["verify"]["success"] and rescan_before.exists():
        if not quiet:
            print("--- Step 4/4: rescan (compare before/after) ---", file=sys.stderr)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            run_scan(path)
        self_map_after = path / "self_map.json"
        if self_map_after.exists():
            try:
                old_snap = build_snapshot_from_self_map(rescan_before)
                new_snap = build_snapshot_from_self_map(self_map_after)
                diff = diff_architecture_snapshots(old_snap, new_snap)
                report["rescan_diff"] = {
                    "structures": diff["structures"],
                    "smells": diff["smells"],
                    "maturity": diff["maturity"],
                    "centrality_shifts": diff.get("centrality_shifts", [])[:10],
                }
            except Exception:
                report["rescan_diff"] = {"error": "diff failed"}

    modified = report.get("modified", [])
    verify_success = report["verify"]["success"]
    if not quiet:
        _print_fix_summary(operations, modified=modified, verify_success=verify_success, dry_run=False)

    try:
        memory = ProjectMemory(path)
        summary = result.output.get("summary", {}) or {}
        risks = list(summary.get("risks", []))
        modules = list(modified)
        memory.learning.append(
            project_root=path,
            modules=modules,
            operations=operations,
            risks=risks,
            verify_success=verify_success,
        )
        memory.events.append_event(
            type="patch",
            input={"operations_count": len(operations)},
            output={
                "modified": report.get("modified", []),
                "run_id": report.get("run_id"),
                "verify_success": verify_success,
            },
            result=verify_success,
        )
    except Exception:
        pass

    print(json.dumps(report, indent=2, ensure_ascii=False))

    if report.get("errors"):
        return 1

    if not report["verify"].get("success"):
        run_id = report.get("run_id")
        stderr = (report.get("verify") or {}).get("stderr") or ""
        print(file=sys.stderr)
        print("Tests failed. To restore files from backup:", file=sys.stderr)
        if run_id:
            print(f"  eurika agent patch-rollback --run-id {run_id} .", file=sys.stderr)
        else:
            print("  eurika agent patch-rollback .", file=sys.stderr)
        if "No module named pytest" in stderr or "pytest: command not found" in stderr:
            print("To run verification after fix, install pytest: pip install pytest", file=sys.stderr)
        return 1

    return 0


def handle_agent_patch_rollback(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return 1

    if getattr(args, "list", False):
        info = list_backups(path)
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return 0

    run_id = getattr(args, "run_id", None)
    report = rollback(path, run_id=run_id)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get("errors"):
        return 1
    return 0


def handle_agent_learning_summary(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"Error: path is not a directory: {path}", file=sys.stderr)
        return 1

    memory = ProjectMemory(path)
    by_action = memory.learning.aggregate_by_action_kind()
    by_smell_action = memory.learning.aggregate_by_smell_action()
    out = {
        "by_action_kind": by_action,
        "by_smell_action": by_smell_action,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0



# TODO: Refactor cli/agent_handlers.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.

# TODO: Refactor cli/agent_handlers.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Extract from imports: action_plan.py, agent_core.py, agent_core_arch_review.py.
