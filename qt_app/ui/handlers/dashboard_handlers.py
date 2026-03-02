"""Dashboard refresh handler. ROADMAP 3.1-arch.3."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from ..main_window import MainWindow


def show_firewall_violations_detail(main: "MainWindow") -> None:
    """CR-A3: Show dependency firewall violations in dialog (forbidden, layer, subsystem bypass)."""
    detail = main._api.get_firewall_violations_detail()
    forbidden = detail.get("forbidden") or []
    layer = detail.get("layer_violations") or []
    bypass = detail.get("subsystem_bypass") or []
    lines: list[str] = []
    if forbidden:
        lines.append("Forbidden imports:")
        for v in forbidden[:20]:
            lines.append(f"  {v.get('path', '?')} → {v.get('forbidden_module', '?')}")
        if len(forbidden) > 20:
            lines.append(f"  ... и ещё {len(forbidden) - 20}")
    if layer:
        lines.append("")
        lines.append("Layer violations (Lx → Ly, x < y):")
        for v in layer[:20]:
            lines.append(f"  {v.get('path', '?')} → {v.get('imported_module', '?')} (L{v.get('source_layer')}→L{v.get('target_layer')})")
        if len(layer) > 20:
            lines.append(f"  ... и ещё {len(layer) - 20}")
    if bypass:
        lines.append("")
        lines.append("Subsystem bypass:")
        for v in bypass[:20]:
            lines.append(f"  {v.get('path', '?')} → {v.get('imported_module', '?')}")
        if len(bypass) > 20:
            lines.append(f"  ... и ещё {len(bypass) - 20}")
    text = "\n".join(lines) if lines else "0 violations (PASS)"
    msg = QMessageBox(main)
    msg.setWindowTitle("Dependency firewall (L0–L6)")
    msg.setText(text)
    msg.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg.exec()


def refresh_dashboard(main: MainWindow) -> None:
    summary = main._api.get_summary()
    history = main._api.get_history(window=main.window_spin.value())
    if summary.get("error"):
        main.dashboard_modules.setText("-")
        main.dashboard_deps.setText("-")
        main.dashboard_cycles.setText("-")
        main.dashboard_risk.setText("-")
        main.dashboard_maturity.setText(summary.get("error", "-"))
        main.dashboard_trends.setText("-")
        main.dashboard_risks_text.setPlainText("")
        guard = main._api.get_self_guard()
        if guard.get("pass"):
            main.dashboard_self_guard_text.setPlainText("PASS")
        else:
            parts = []
            if guard.get("must_split_count", 0) > 0:
                parts.append(f"{guard['must_split_count']} must-split")
            if guard.get("complexity_budget_alarms"):
                parts.extend(guard["complexity_budget_alarms"])
            main.dashboard_self_guard_text.setPlainText(
                "; ".join(parts) if parts else "Scan required"
            )
        main.dashboard_risk_pred_text.setPlainText("")
        main.dashboard_apply_rate.setText("-")
        main.dashboard_rollback_rate.setText("-")
        main.dashboard_median_verify.setText("-")
        main.learning_widget_text.setPlainText(
            "Run eurika scan . first, then fix/cycle for learning data."
        )
        return
    system = summary.get("system", {})
    main.dashboard_modules.setText(str(system.get("modules", "-")))
    main.dashboard_deps.setText(str(system.get("dependencies", "-")))
    main.dashboard_cycles.setText(str(system.get("cycles", "-")))
    main.dashboard_maturity.setText(str(summary.get("maturity", "-")))
    main.dashboard_risk.setText(str(system.get("risk_score", "-")))
    trends = history.get("trends", {}) if isinstance(history, dict) else {}
    trend_parts = [
        f"complexity={trends.get('complexity', '-')}",
        f"smells={trends.get('smells', '-')}",
        f"centralization={trends.get('centralization', '-')}",
    ]
    main.dashboard_trends.setText(", ".join(trend_parts))
    risks = summary.get("risks") or []
    if isinstance(risks, list) and risks:
        risk_lines = [str(r)[:120] for r in risks[:8]]
        main.dashboard_risks_text.setPlainText("\n".join(risk_lines))
    else:
        main.dashboard_risks_text.setPlainText("")
    guard = main._api.get_self_guard()
    if guard.get("pass"):
        main.dashboard_self_guard_text.setPlainText("PASS (0 violations, 0 alarms)")
    else:
        lines = []
        if guard.get("must_split_count", 0) > 0:
            lines.append(f"Violations: {guard['must_split_count']} must-split")
        if guard.get("forbidden_count", 0) > 0:
            lines.append(f"{guard['forbidden_count']} forbidden imports")
        if guard.get("layer_viol_count", 0) > 0:
            lines.append(f"{guard['layer_viol_count']} layer violations")
        if guard.get("subsystem_bypass_count", 0) > 0:
            lines.append(f"{guard['subsystem_bypass_count']} subsystem bypass")
        if guard.get("trend_alarms"):
            lines.append("Trend alarms: " + "; ".join(guard["trend_alarms"]))
        if guard.get("complexity_budget_alarms"):
            lines.append("Complexity budget: " + "; ".join(guard["complexity_budget_alarms"]))
        main.dashboard_self_guard_text.setPlainText("\n".join(lines) if lines else "-")
    rp = main._api.get_risk_prediction(top_n=5)
    preds = rp.get("predictions") or []
    if preds:
        rp_lines = [
            f"{p.get('module', '?')}: {p.get('score', 0)} ({', '.join(p.get('reasons', [])[:3])})"
            for p in preds
        ]
        main.dashboard_risk_pred_text.setPlainText("\n".join(rp_lines))
    else:
        main.dashboard_risk_pred_text.setPlainText("")
    metrics = main._api.get_operational_metrics(window=10)
    if isinstance(metrics, dict) and not metrics.get("error"):
        main.dashboard_apply_rate.setText(str(metrics.get("apply_rate", "-")))
        main.dashboard_rollback_rate.setText(str(metrics.get("rollback_rate", "-")))
        med = metrics.get("median_verify_time_ms")
        main.dashboard_median_verify.setText(str(med) if med is not None else "-")
    else:
        main.dashboard_apply_rate.setText("-")
        main.dashboard_rollback_rate.setText("-")
        main.dashboard_median_verify.setText("-")
    learning = main._api.get_learning_insights(top_n=5)
    worked = learning.get("what_worked") or []
    prioritized = learning.get("prioritized_smell_actions") or []
    recs = learning.get("recommendations") or {}
    white = recs.get("whitelist_candidates") or []
    deny = recs.get("policy_deny_candidates") or []
    chat_white = recs.get("chat_whitelist_hints") or []
    chat_review = recs.get("chat_policy_review_hints") or []
    learning_lines: list[str] = []
    if prioritized:
        learning_lines.append("Prioritized smell|action (OSS patterns first):")
        for item in prioritized[:5]:
            learning_lines.append(
                f"- {item.get('smell_type')}|{item.get('action_kind')} "
                f"rate={item.get('verify_success_rate')} total={item.get('total')}"
            )
    if worked:
        learning_lines.append("What worked (top targets):")
        for item in worked:
            learning_lines.append(
                f"- {item.get('target_file')} | {item.get('smell_type')}|{item.get('action_kind')} "
                f"rate={item.get('verify_success_rate')} total={item.get('total')}"
            )
    if white:
        learning_lines.append("")
        learning_lines.append("Whitelist suggestions:")
        for item in white:
            learning_lines.append(
                f"- {item.get('target_file')} | {item.get('action_kind')} "
                f"(rate={item.get('verify_success_rate')}, total={item.get('total')})"
            )
    if deny:
        learning_lines.append("")
        learning_lines.append("Policy deny/review suggestions:")
        for item in deny:
            learning_lines.append(
                f"- {item.get('target_file')} | {item.get('action_kind')} "
                f"(rate={item.get('verify_success_rate')}, total={item.get('total')})"
            )
    if chat_white:
        learning_lines.append("")
        learning_lines.append("Chat-driven whitelist hints (review only):")
        for item in chat_white:
            learning_lines.append(
                f"- intent={item.get('intent')} target={item.get('target')} "
                f"(success_rate={item.get('success_rate')}, total={item.get('total')})"
            )
    if chat_review:
        learning_lines.append("")
        learning_lines.append("Chat-driven policy review hints:")
        for item in chat_review:
            learning_lines.append(
                f"- intent={item.get('intent')} target={item.get('target')} "
                f"(success_rate={item.get('success_rate')}, fail={item.get('fail')}, total={item.get('total')})"
            )
    if not learning_lines:
        learning_lines.append("No learning data yet. Run eurika fix/cycle to collect outcomes.")
    main.learning_widget_text.setPlainText("\n".join(learning_lines))
