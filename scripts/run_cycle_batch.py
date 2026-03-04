#!/usr/bin/env python3
"""
Batch fix cycles for CYCLE_REPORT ritual (BOUNDED_EVOLUTION §6).

Runs eurika fix . in a loop; every --report-every cycles prints CYCLE_REPORT metrics.

Usage:
  python scripts/run_cycle_batch.py . --max-cycles 500 --report-every 100
  python scripts/run_cycle_batch.py /path/to/project --dry-run  # dry-run only

Output: metrics block per report interval → paste into docs/CYCLE_REPORT.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _print_report_snippet(project_root: Path, cycle: int) -> None:
    """Print CYCLE_REPORT metrics block for cycle N."""
    from eurika.api import get_learning_insights
    from eurika.storage import aggregate_operational_metrics
    from eurika.storage.experience_store import (
        get_recent_failures,
        get_kind_plan_failure_counts,
    )

    root = Path(project_root).resolve()
    ops_metrics = aggregate_operational_metrics(root, window=10) or {}
    insights = get_learning_insights(root, top_n=10)
    failures = get_recent_failures(root, limit=5)
    kind_plan = get_kind_plan_failure_counts(root, limit=20)

    apply_rate = ops_metrics.get("apply_rate")
    rollback_rate = ops_metrics.get("rollback_rate")
    total_ops = ops_metrics.get("total_ops") or 0
    total_mod = ops_metrics.get("total_modified") or 0
    success_rate = (total_mod / total_ops * (1 - rollback_rate)) if total_ops else None

    # Top failure reason (simplified)
    top_failure = "N/A"
    if failures:
        reasons = [f[2] for f in failures if len(f) > 2]
        if reasons:
            from collections import Counter
            top_failure = Counter(reasons).most_common(1)[0][0][:60]

    # Most deprioritized (kind,plan with most failures)
    most_deprior = "N/A"
    if kind_plan:
        kp = max(kind_plan.items(), key=lambda x: x[1])
        most_deprior = f"{kp[0][0]}|{kp[0][1]}"

    # Most successful action
    best_action = "N/A"
    if insights and "by_action_kind" in insights:
        by_kind = insights["by_action_kind"]
        if by_kind:
            best = None
            best_rate = 0.0
            for k, v in by_kind.items():
                if not isinstance(v, dict) or v.get("total", 0) < 2:
                    continue
                total = v.get("total") or 1
                rate = (v.get("verify_success") or 0) / total
                if rate > best_rate:
                    best_rate = rate
                    best = k
            if best is not None:
                best_action = f"{best} ({best_rate * 100:.0f}%)"

    # Memory size
    events_path = root / ".eurika" / "events.json"
    events_size = events_path.stat().st_size / 1024 if events_path.exists() else 0
    pl_path = root / ".eurika" / "pattern_library.json"
    pl_size = pl_path.stat().st_size / 1024 if pl_path.exists() else 0

    print(f"\n## CYCLE_REPORT @ cycle {cycle}")
    print("| Метрика | Значение |")
    print("|---------|---------|")
    print(f"| success_rate (overall) | {success_rate if success_rate is not None else 'N/A'} |")
    print(f"| apply_rate (window) | {apply_rate} |")
    print(f"| rollback_rate | {rollback_rate} |")
    print(f"| top_failure_reason | {top_failure} |")
    print(f"| most_deprioritized_goal | {most_deprior} |")
    print(f"| most_successful_action_kind | {best_action} |")
    print(f"| events.json (KB) | {events_size:.1f} |")
    print(f"| pattern_library.json (KB) | {pl_size:.1f} |")
    print("| **Был ли сдвиг поведения?** | (Yes/No + комментарий) |")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch fix cycles for CYCLE_REPORT ritual")
    parser.add_argument("project", type=Path, help="Project root")
    parser.add_argument("--max-cycles", type=int, default=500, help="Max cycles (default 500)")
    parser.add_argument("--report-every", type=int, default=100, help="Report interval (default 100)")
    parser.add_argument("--dry-run", action="store_true", help="Only dry-run (no apply)")
    parser.add_argument("-q", "--quiet", action="store_true", default=True, help="Quiet mode")
    args = parser.parse_args()

    project = args.project.resolve()
    if not (project / ".eurika").exists() and not (project / "eurika").exists():
        print(f"Not a Eurika project: {project}", file=sys.stderr)
        return 1

    from eurika.orchestration.entry import run_cycle

    for i in range(1, args.max_cycles + 1):
        out = run_cycle(
            project,
            mode="fix",
            quiet=args.quiet,
            non_interactive=True,
            dry_run=args.dry_run,
            allow_low_risk_campaign=True,
        )
        err = out.get("error")
        if err:
            print(f"Cycle {i}: error={err}", file=sys.stderr)

        if i % args.report_every == 0:
            _print_report_snippet(project, i)

    return 0


if __name__ == "__main__":
    sys.exit(main())
