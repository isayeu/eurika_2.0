"""Pending plan load, approvals table, save handlers. ROADMAP 3.1-arch.3."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QComboBox, QMessageBox, QTableWidgetItem

if TYPE_CHECKING:
    from ..main_window import MainWindow


def load_pending_plan(main: MainWindow) -> None:
    payload = main._api.get_pending_plan()
    if payload.get("error"):
        QMessageBox.warning(
            main, "Pending plan", payload.get("error", "Unknown error")
        )
        return
    operations = payload.get("operations") or []
    if not isinstance(operations, list):
        QMessageBox.warning(main, "Pending plan", "Invalid operations payload")
        return
    main._pending_operations = [op for op in operations if isinstance(op, dict)]
    render_approvals_table(main)


def render_approvals_table(main: MainWindow) -> None:
    main.approvals_table.setRowCount(len(main._pending_operations))
    for index, op in enumerate(main._pending_operations):
        expl = op.get("explainability") or {}
        risk = str(expl.get("risk") or op.get("risk") or "")
        main.approvals_table.setItem(
            index, 0, QTableWidgetItem(str(index + 1))
        )
        main.approvals_table.setItem(
            index, 1, QTableWidgetItem(str(op.get("target_file", "")))
        )
        main.approvals_table.setItem(
            index, 2, QTableWidgetItem(str(op.get("kind", "")))
        )
        main.approvals_table.setItem(index, 3, QTableWidgetItem(risk))
        combo = QComboBox()
        combo.addItems(["pending", "approve", "reject"])
        current = str(op.get("team_decision", "pending")).lower()
        combo.setCurrentText(
            current if current in {"pending", "approve", "reject"} else "pending"
        )
        main.approvals_table.setCellWidget(index, 4, combo)


def on_approval_row_selected(main: MainWindow) -> None:
    rows = main.approvals_table.selectionModel().selectedRows()
    if not rows or not main._pending_operations:
        main.approvals_diff_text.setPlainText("")
        return
    row = rows[0].row()
    if row < 0 or row >= len(main._pending_operations):
        main.approvals_diff_text.setPlainText("")
        return
    op = main._pending_operations[row]
    try:
        result = main._api.preview_operation(op)
    except Exception as e:
        main.approvals_diff_text.setPlainText(f"Preview error: {e}")
        return
    if result.get("error"):
        main.approvals_diff_text.setPlainText(
            f"Error: {result['error']}\n\n{result.get('old_content', '')[:2000]}"
        )
        return
    diff = result.get("unified_diff", "")
    oss_examples = result.get("oss_examples") or []
    if diff:
        main.approvals_diff_text.setPlainText(diff)
    else:
        main.approvals_diff_text.setPlainText(
            "(no diff — operation would produce no change)"
        )
    if oss_examples:
        ref_block = "\n\n--- OSS Reference (Learning from GitHub) ---\n\n" + "\n\n".join(oss_examples[:3])
        main.approvals_diff_text.appendPlainText(ref_block)


def save_approvals(main: MainWindow) -> None:
    if not main._pending_operations:
        QMessageBox.information(main, "Approvals", "No pending operations loaded.")
        return
    payload_ops: list[dict[str, Any]] = []
    for index, op in enumerate(main._pending_operations):
        decision_widget = main.approvals_table.cellWidget(index, 4)
        decision = "pending"
        if isinstance(decision_widget, QComboBox):
            decision = decision_widget.currentText()
        payload_ops.append(
            {
                "index": index + 1,
                "team_decision": decision,
                "approved_by": "qt-user",
                "target_file": op.get("target_file"),
                "kind": op.get("kind"),
            }
        )
    result = main._api.save_approvals(payload_ops)
    if result.get("error"):
        QMessageBox.warning(
            main, "Approvals", result.get("error", "Failed to save approvals")
        )
        return
    QMessageBox.information(
        main, "Approvals", json.dumps(result, ensure_ascii=True, indent=2)
    )
