"""Doctor-cycle helpers for orchestration layer. ROADMAP 2.9.3: smell→topic mapping."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from eurika.knowledge import SMELL_TO_KNOWLEDGE_TOPICS


def _parse_smell_for_knowledge(risk: str) -> str | None:
    """Extract smell type from risk for knowledge mapping (broader than architect's)."""
    if not risk or not isinstance(risk, str):
        return None
    parts = risk.strip().split()
    if not parts:
        return None
    first = parts[0].lower()
    return first if first in SMELL_TO_KNOWLEDGE_TOPICS else None


def knowledge_topics_from_env_or_summary(summary: Any) -> list[str]:
    """Topics for Knowledge: from EURIKA_KNOWLEDGE_TOPIC or derived from summary (ROADMAP 2.9.3)."""
    env = os.environ.get("EURIKA_KNOWLEDGE_TOPIC", "").strip()
    if env:
        return [t.strip() for t in env.split(",") if t.strip()]
    topics: list[str] = ["python", "python_3_14"]
    sys_info = summary.get("system") or {}
    if (sys_info.get("cycles") or 0) > 0:
        topics.append("cyclic_imports")
    risks = summary.get("risks") or []
    seen_topics: set[str] = set(topics)
    for r in risks:
        smell = _parse_smell_for_knowledge(str(r))
        if smell and smell in SMELL_TO_KNOWLEDGE_TOPICS:
            for t in SMELL_TO_KNOWLEDGE_TOPICS[smell]:
                if t not in seen_topics:
                    seen_topics.add(t)
                    topics.append(t)
    risk_str = " ".join(str(r) for r in risks).lower()
    if "deprecated" in risk_str and "version_migration" not in seen_topics:
        topics.append("version_migration")
    return topics


def load_suggested_policy_for_apply(path: Path) -> dict[str, str]:
    """Load suggested policy from doctor or fix report for --apply-suggested-policy (ROADMAP 2.9.4)."""
    doctor_path = path / "eurika_doctor_report.json"
    if doctor_path.exists():
        try:
            doc = json.loads(doctor_path.read_text(encoding="utf-8"))
            sugg = (doc.get("suggested_policy") or {}).get("suggested") or {}
            if isinstance(sugg, dict):
                return {k: str(v) for k, v in sugg.items()}
        except Exception:
            pass
    fix_path = path / "eurika_fix_report.json"
    if fix_path.exists():
        try:
            fix = json.loads(fix_path.read_text(encoding="utf-8"))
            telemetry = fix.get("telemetry") or {}
            if telemetry:
                from eurika.agent.config import suggest_policy_from_telemetry

                return suggest_policy_from_telemetry(telemetry)
        except Exception:
            pass
    return {}


def _suggested_policy_from_last_fix(path: Path) -> dict[str, Any]:
    """Load last fix telemetry and suggest policy (ROADMAP 2.9.4)."""
    fix_path = path / "eurika_fix_report.json"
    if not fix_path.exists():
        return {}
    try:
        fix = json.loads(fix_path.read_text(encoding="utf-8"))
        telemetry = fix.get("telemetry") or {}
        if not telemetry:
            return {}
        from eurika.agent.config import suggest_policy_from_telemetry

        suggested = suggest_policy_from_telemetry(telemetry)
        return {
            "suggested": suggested,
            "telemetry": {
                "apply_rate": telemetry.get("apply_rate"),
                "rollback_rate": telemetry.get("rollback_rate"),
                "no_op_rate": telemetry.get("no_op_rate"),
            },
        }
    except Exception:
        return {}


def _operational_metrics_from_events(path: Path, window: int = 10) -> dict[str, Any] | None:
    """Aggregate rolling metrics from patch events (ROADMAP 2.7.8)."""
    try:
        from eurika.storage import aggregate_operational_metrics

        return aggregate_operational_metrics(path, window=window)
    except Exception:
        return None


def run_doctor_cycle(
    path: Path,
    *,
    window: int = 5,
    no_llm: bool = False,
    online: bool = False,
    quiet: bool = False,
) -> dict[str, Any]:
    """Run diagnostics cycle: summary + history + patch_plan + architect. ROADMAP 2.9.4, 3.0.3."""
    from eurika.api import get_summary, get_history, get_patch_plan, get_recent_events

    from .logging import get_logger

    _log = get_logger("orchestration.doctor")

    _log.info("eurika: doctor — loading summary...")
    from eurika.knowledge import (
        CompositeKnowledgeProvider,
        LocalKnowledgeProvider,
        OfficialDocsProvider,
        OSSPatternProvider,
        PEPProvider,
        ReleaseNotesProvider,
    )
    from eurika.reasoning.architect import interpret_architecture_with_meta

    summary = get_summary(path)
    if summary.get("error"):
        from .cycle_state import with_cycle_state
        return with_cycle_state({"error": summary.get("error", "unknown")}, is_error=True)
    _log.info("eurika: doctor — loading history...")
    history = get_history(path, window=window)
    _log.info("eurika: doctor — loading patch plan (LLM hints disabled for speed)...")
    prev = os.environ.pop("EURIKA_USE_LLM_HINTS", None)
    try:
        os.environ["EURIKA_USE_LLM_HINTS"] = "0"
        patch_plan = get_patch_plan(path, window=window)
    finally:
        if prev is not None:
            os.environ["EURIKA_USE_LLM_HINTS"] = prev
        else:
            os.environ.pop("EURIKA_USE_LLM_HINTS", None)
    _log.info("eurika: doctor — loading recent events...")
    recent_events = get_recent_events(path, limit=5, types=("patch", "learn"))
    _log.info("eurika: doctor — building knowledge provider...")
    use_llm = not no_llm
    cache_dir = path / ".eurika" / "knowledge_cache"
    ttl = float(os.environ.get("EURIKA_KNOWLEDGE_TTL", "86400"))
    rate_limit = float(os.environ.get("EURIKA_KNOWLEDGE_RATE_LIMIT", "1.0" if online else "0"))
    oss_path = path / ".eurika" / "pattern_library.json"
    knowledge_provider = CompositeKnowledgeProvider([
        LocalKnowledgeProvider(path / "eurika_knowledge.json"),
        OSSPatternProvider(oss_path),
        PEPProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=online, rate_limit_seconds=rate_limit),
        OfficialDocsProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=online, rate_limit_seconds=rate_limit),
        ReleaseNotesProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=online, rate_limit_seconds=rate_limit),
    ])
    _log.info("eurika: doctor — resolving knowledge topics...")
    knowledge_topic = knowledge_topics_from_env_or_summary(summary)
    _log.info("eurika: doctor — step 3/4: calling architect (LLM)" if use_llm else "eurika: doctor — step 3/4: calling architect (template)")
    architect_text, architect_meta = interpret_architecture_with_meta(
        summary, history, use_llm=use_llm, patch_plan=patch_plan,
        knowledge_provider=knowledge_provider, knowledge_topic=knowledge_topic,
        recent_events=recent_events,
    )
    out: dict[str, Any] = {
        "summary": summary,
        "history": history,
        "patch_plan": patch_plan,
        "context_sources": (patch_plan or {}).get("context_sources") if isinstance(patch_plan, dict) else {},
        "architect_text": architect_text,
        "runtime": {
            "degraded_mode": bool((architect_meta or {}).get("degraded_mode")),
            "degraded_reasons": list((architect_meta or {}).get("degraded_reasons", [])),
            "llm_used": bool((architect_meta or {}).get("llm_used")),
            "use_llm": bool(use_llm),
        },
    }
    suggested_info = _suggested_policy_from_last_fix(path)
    if suggested_info.get("suggested"):
        out["suggested_policy"] = suggested_info
    ops_metrics = _operational_metrics_from_events(path, window=10)
    if ops_metrics:
        out["operational_metrics"] = ops_metrics
    try:
        from eurika.storage.campaign_checkpoint import latest_campaign_checkpoint

        checkpoint = latest_campaign_checkpoint(path)
        if checkpoint:
            out["campaign_checkpoint"] = checkpoint
    except Exception:
        pass
    from .cycle_state import with_cycle_state
    return with_cycle_state(out, is_error=False)


# TODO (eurika): refactor long_function 'run_doctor_cycle' — consider extracting helper
