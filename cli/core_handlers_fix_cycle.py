"""Fix and cycle handlers (P0.4 split)."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any

from .core_handlers_common import _aggregate_multi_repo_fix_reports, _clog, _paths_from_args


def handle_fix(args: Any) -> int:
    """Full cycle: scan → plan → patch-apply --apply --verify (3.0.1: multi-repo)."""
    from cli.agent_handlers import handle_agent_cycle
    from eurika.orchestration.doctor import load_suggested_policy_for_apply

    paths = _paths_from_args(args)
    exit_code = 0
    for i, path in enumerate(paths):
        if len(paths) > 1:
            _clog().info("\n--- Project %s/%s: %s ---\n", i + 1, len(paths), path)
        if getattr(args, "apply_suggested_policy", False):
            sugg = load_suggested_policy_for_apply(path)
            if sugg:
                os.environ.update(sugg)
            os.environ["EURIKA_IGNORE_CAMPAIGN"] = "1"
        fix_args = SimpleNamespace(
            path=path,
            window=getattr(args, "window", 5),
            dry_run=getattr(args, "dry_run", False),
            quiet=getattr(args, "quiet", False),
            no_clean_imports=getattr(args, "no_clean_imports", False),
            no_code_smells=getattr(args, "no_code_smells", False),
            verify_cmd=getattr(args, "verify_cmd", None),
            verify_timeout=getattr(args, "verify_timeout", None),
            interval=getattr(args, "interval", 0),
            runtime_mode=getattr(args, "runtime_mode", "assist"),
            non_interactive=getattr(args, "non_interactive", False),
            session_id=getattr(args, "session_id", None),
            allow_campaign_retry=getattr(args, "allow_campaign_retry", False),
            allow_low_risk_campaign=getattr(args, "allow_low_risk_campaign", False),
            online=getattr(args, "online", False),
            team_mode=getattr(args, "team_mode", False),
            apply_approved=getattr(args, "apply_approved", False),
            approve_ops=getattr(args, "approve_ops", None),
            reject_ops=getattr(args, "reject_ops", None),
        )
        if handle_agent_cycle(fix_args) != 0:
            exit_code = 1
    if len(paths) > 1:
        agg = _aggregate_multi_repo_fix_reports(paths)
        if agg:
            out_path = paths[0] / "eurika_fix_report_aggregated.json"
            try:
                out_path.write_text(json.dumps(agg, indent=2, ensure_ascii=False), encoding="utf-8")
                _clog().info("eurika: eurika_fix_report_aggregated.json written to %s", out_path)
            except Exception:
                pass
    return exit_code


def handle_cycle(args: Any) -> int:
    """Full ritual: scan → doctor → fix (3.0.1: multi-repo)."""
    from cli.agent_handlers import _run_cycle_with_mode
    from eurika.orchestration.doctor import load_suggested_policy_for_apply

    paths = _paths_from_args(args)
    exit_code = 0
    for i, path in enumerate(paths):
        if len(paths) > 1:
            _clog().info("\n--- Project %s/%s: %s ---\n", i + 1, len(paths), path)
        if getattr(args, "apply_suggested_policy", False):
            sugg = load_suggested_policy_for_apply(path)
            if sugg:
                os.environ.update(sugg)
            os.environ["EURIKA_IGNORE_CAMPAIGN"] = "1"
        cycle_args = SimpleNamespace(
            path=path,
            window=getattr(args, "window", 5),
            dry_run=getattr(args, "dry_run", False),
            quiet=getattr(args, "quiet", False),
            no_llm=getattr(args, "no_llm", False),
            no_clean_imports=getattr(args, "no_clean_imports", False),
            no_code_smells=getattr(args, "no_code_smells", False),
            verify_cmd=getattr(args, "verify_cmd", None),
            verify_timeout=getattr(args, "verify_timeout", None),
            interval=getattr(args, "interval", 0),
            runtime_mode=getattr(args, "runtime_mode", "assist"),
            non_interactive=getattr(args, "non_interactive", False),
            session_id=getattr(args, "session_id", None),
            allow_campaign_retry=getattr(args, "allow_campaign_retry", False),
            allow_low_risk_campaign=getattr(args, "allow_low_risk_campaign", False),
            online=getattr(args, "online", False),
            team_mode=getattr(args, "team_mode", False),
            apply_approved=getattr(args, "apply_approved", False),
            approve_ops=getattr(args, "approve_ops", None),
            reject_ops=getattr(args, "reject_ops", None),
        )
        if _run_cycle_with_mode(cycle_args, mode="full") != 0:
            exit_code = 1
    if len(paths) > 1:
        agg = _aggregate_multi_repo_fix_reports(paths)
        if agg:
            out_path = paths[0] / "eurika_fix_report_aggregated.json"
            try:
                out_path.write_text(json.dumps(agg, indent=2, ensure_ascii=False), encoding="utf-8")
                _clog().info("eurika: eurika_fix_report_aggregated.json written to %s", out_path)
            except Exception:
                pass
    return exit_code
