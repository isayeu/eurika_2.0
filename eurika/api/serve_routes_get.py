"""GET /api/* route handlers."""

from __future__ import annotations

from pathlib import Path

from report.explain_format import explain_module

from eurika.api import (
    get_diff,
    get_graph,
    get_history,
    get_knowledge,
    get_knowledge_graph,
    get_metrics,
    get_test_links,
    get_operational_metrics,
    get_patch_plan,
    get_pattern_library,
    get_pending_plan,
    get_risk_prediction,
    get_self_guard,
    get_smells_with_plugins,
    get_summary,
)
from .serve_utils import emit_route_json as _json_response


def dispatch_api_get(
    handler,
    project_root: Path,
    path: str,
    query: dict,
) -> bool:
    """Dispatch GET /api/* routes. Returns True if handled."""
    if path == "/api/summary":
        include_plugins = query.get("include_plugins", ["0"])[0].lower() in ("1", "true", "yes")
        _json_response(handler, get_summary(project_root, include_plugins=include_plugins))
        return True
    if path == "/api/metrics":
        _json_response(handler, get_metrics(project_root))
        return True
    if path == "/api/self_guard":
        _json_response(handler, get_self_guard(project_root))
        return True
    if path == "/api/risk_prediction":
        top_n = int(query.get("top_n", [10])[0])
        _json_response(handler, get_risk_prediction(project_root, top_n=top_n))
        return True
    if path == "/api/smells_with_plugins":
        include = query.get("include_plugins", ["1"])[0].lower() not in ("0", "false", "no")
        _json_response(handler, get_smells_with_plugins(project_root, include_plugins=include))
        return True
    if path == "/api/history":
        window = int(query.get("window", [5])[0])
        _json_response(handler, get_history(project_root, window=window))
        return True
    if path.rstrip("/") == "/api":
        _json_response(handler, {
            "eurika": "JSON API",
            "project_root": str(project_root),
            "endpoints": [
                "GET /api/summary?include_plugins=1 — summary (R5: merge plugin smells when 1)",
                "GET /api/metrics — MetricVector + Energy (ROADMAP §5.7 Execution Model)",
                "GET /api/self_guard — R5 SELF-GUARD health gate (violations, alarms)",
                "GET /api/risk_prediction?top_n=10 — R5 top modules by regression risk",
                "GET /api/smells_with_plugins?include_plugins=1 — R5 Eurika + plugin smells",
                "GET /api/history?window=5 — evolution history",
                "GET /api/diff?old=path/to/old.json&new=path/to/new.json — diff two self_maps",
                "GET /api/doctor?window=5&no_llm=0 — full report + architect (ROADMAP 3.5.1)",
                "GET /api/patch_plan?window=5 — planned operations",
                "GET /api/explain?module=...&window=5 — module role and risks",
                "GET /api/graph — dependency graph (nodes=modules, edges=imports)",
                "GET /api/operational_metrics?window=10 — apply-rate, rollback-rate, median verify time",
                "GET /api/pattern_library?with_samples=1 — OSS pattern library (Learning from GitHub 3.0.5)",
                "GET /api/test_links — R10: test_file→module links",
                "GET /api/knowledge_graph — R10: code + test_links facade",
                "GET /api/knowledge?topic=...&online=0 — Knowledge Layer query",
                "GET /api/pending_plan — team-mode plan for approve UI (ROADMAP 3.5.6)",
                "GET /api/market — paper Market panel (portfolio, opens, journal)",
                "GET /api/learning — paper learning snapshot (trades, model, bank)",
                "GET /api/file?path=... — read file content (for diff preview)",
                "GET /api/activity?after=0 — live API/agent work for Chat/Terminal/Desktop",
                "POST /api/operation_preview — preview single-file op diff (ROADMAP 3.6.7)",
                "POST /api/approve — save approve/reject decisions to pending_plan.json",
                "POST /api/exec — run whitelisted eurika command (scan, doctor, fix, cycle, ...)",
                "POST /api/ask_architect — architect interpretation (returns architect_text from doctor)",
                "POST /api/chat — chat with Eurika (message → LLM via Eurika layer; logs to .eurika/chat_history/)",
            ],
        })
        return True
    if path == "/api/diff":
        old_q, new_q = query.get("old", []), query.get("new", [])
        if not old_q or not new_q:
            _json_response(handler, {"error": "query params 'old' and 'new' (paths to self_map.json) required"}, status=400)
            return True
        old_path = project_root / old_q[0] if not Path(old_q[0]).is_absolute() else Path(old_q[0])
        new_path = project_root / new_q[0] if not Path(new_q[0]).is_absolute() else Path(new_q[0])
        _json_response(handler, get_diff(old_path, new_path))
        return True
    if path == "/api/doctor":
        window = int(query.get("window", [5])[0])
        no_llm = query.get("no_llm", ["0"])[0].lower() in ("1", "true", "yes")
        from eurika.orchestration.doctor import run_doctor_cycle
        _json_response(handler, run_doctor_cycle(project_root, window=window, no_llm=no_llm))
        return True
    if path == "/api/patch_plan":
        window = int(query.get("window", [5])[0])
        plan = get_patch_plan(project_root, window=window)
        _json_response(handler, plan if plan else {"error": "patch plan not available", "hint": "run eurika scan first"})
        return True
    if path == "/api/graph":
        _json_response(handler, get_graph(project_root))
        return True
    if path == "/api/operational_metrics":
        window = int(query.get("window", [10])[0])
        _json_response(handler, get_operational_metrics(project_root, window=window))
        return True
    if path == "/api/pattern_library":
        samples = query.get("with_samples", ["1"])[0].lower() not in ("0", "false", "no")
        _json_response(handler, get_pattern_library(project_root, with_samples=samples))
        return True
    if path == "/api/test_links":
        _json_response(handler, get_test_links(project_root))
        return True
    if path == "/api/knowledge_graph":
        _json_response(handler, get_knowledge_graph(project_root))
        return True
    if path == "/api/knowledge":
        topic_q = query.get("topic", [])
        if not topic_q:
            _json_response(handler, {"error": "query param 'topic' required (e.g. ?topic=python)"}, status=400)
            return True
        online = query.get("online", ["0"])[0].lower() in ("1", "true", "yes")
        _json_response(handler, get_knowledge(project_root, topic_q[0], online=online))
        return True
    if path == "/api/pending_plan":
        _json_response(handler, get_pending_plan(project_root))
        return True
    if path == "/api/market":
        from eurika.agent.panels import PanelService
        from eurika.agent.workspace import WorkspaceTools

        _json_response(handler, PanelService(WorkspaceTools(project_root)).state("market"))
        return True
    if path == "/api/learning":
        from eurika.ml.learning_status import market_learning_status

        _json_response(handler, market_learning_status(project_root))
        return True
    if path == "/api/file":
        file_q = query.get("path", [])
        if not file_q:
            _json_response(handler, {"error": "query param 'path' required (e.g. ?path=cli/handlers.py)"}, status=400)
            return True
        rel = file_q[0]
        if not str(rel).strip() or ".." in rel or rel.startswith("/"):
            _json_response(handler, {"error": "invalid path"}, status=400)
            return True
        fpath = (project_root / rel).resolve()
        if not str(fpath).startswith(str(project_root.resolve())):
            _json_response(handler, {"error": "path outside project"}, status=400)
            return True
        try:
            if not fpath.is_file():
                _json_response(handler, {"error": "not a file or not found"}, status=404)
                return True
            content = fpath.read_text(encoding="utf-8", errors="replace")
            _json_response(handler, {"path": rel, "content": content})
        except OSError as e:
            _json_response(handler, {"error": str(e)}, status=500)
        return True
    if path == "/api/explain":
        module_q = query.get("module", [])
        if not module_q:
            _json_response(handler, {"error": "query param 'module' required (e.g. ?module=cli/handlers.py)"}, status=400)
            return True
        window = int(query.get("window", [5])[0])
        text, err = explain_module(project_root, module_q[0], window=window)
        _json_response(handler, {"text": text, "module": module_q[0]} if not err else {"error": err, "text": text})
        return True
    if path == "/api/activity":
        from eurika.agent.live_activity import recent as live_recent

        try:
            after = int((query.get("after") or ["0"])[0])
        except (TypeError, ValueError):
            after = 0
        if after < 0:
            after = 0
        try:
            limit = int((query.get("limit") or ["80"])[0])
        except (TypeError, ValueError):
            limit = 80
        _json_response(handler, live_recent(project_root, after_offset=after, limit=limit))
        return True
    return False
