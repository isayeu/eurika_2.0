"""Serializable product panels shared by Desktop, Qt, and remote adapters."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

from eurika.api.diff_api import preview_operation
from eurika.api.team_api import get_pending_plan, save_approvals
from eurika.ml.root import resolve_market_root

from .protocol import ERR_APPROVAL_REQUIRED, ERR_INVALID_PARAMS, RpcError
from .workspace import EventSink, WorkspaceTools


COMMANDS = (
    "scan",
    "doctor",
    "fix",
    "cycle",
    "explain",
    "report-snapshot",
    "learning-kpi",
    "self-check",
    "bug-hunt",
    "learn-github",
    "self-model",
    "hypotheses",
    "ab-compare",
)
READ_ONLY_COMMANDS = frozenset(
    {
        "report-snapshot",
        "learning-kpi",
        "self-model",
        "hypotheses",
        "ab-compare",
    }
)


class PanelService:
    def __init__(self, tools: WorkspaceTools) -> None:
        self.tools = tools

    def state(self, panel: Any) -> dict[str, Any]:
        if panel == "approvals":
            return {"panel": panel, "data": get_pending_plan(self.tools.root)}
        if panel == "commands":
            return {
                "panel": panel,
                "commands": [
                    {
                        "id": command,
                        "requiresApproval": command not in READ_ONLY_COMMANDS,
                    }
                    for command in COMMANDS
                ],
            }
        if panel == "market":
            return {"panel": panel, "data": self._market_state()}
        if panel == "models":
            from eurika.api.models_panel import build_models_state

            return build_models_state(self.tools.root)
        if panel == "context":
            return self._context_state()
        raise RpcError(ERR_INVALID_PARAMS, f"Unknown panel: {panel}")

    def models_prefs(self, params: dict[str, Any]) -> dict[str, Any]:
        """Write allowlisted LLM/ML routing prefs (HITL). Never writes API keys."""
        self._approved(params, "models prefs")
        from eurika.api.models_panel import ALLOWED_PREF_KEYS, apply_models_prefs

        raw = params.get("prefs")
        if raw is None:
            raw = {key: value for key, value in params.items() if key in ALLOWED_PREF_KEYS}
        if not isinstance(raw, dict):
            raise RpcError(ERR_INVALID_PARAMS, "prefs must be an object")
        try:
            return apply_models_prefs(self.tools.root, raw)
        except ValueError as exc:
            raise RpcError(ERR_INVALID_PARAMS, str(exc)) from exc

    def approval_preview(self, params: dict[str, Any]) -> dict[str, Any]:
        operation = params.get("operation")
        if not isinstance(operation, dict):
            raise RpcError(ERR_INVALID_PARAMS, "operation must be an object")
        return preview_operation(self.tools.root, operation)

    def approval_save(self, params: dict[str, Any]) -> dict[str, Any]:
        self._approved(params, "approval decisions")
        operations = params.get("operations")
        if not isinstance(operations, list) or not all(isinstance(item, dict) for item in operations):
            raise RpcError(ERR_INVALID_PARAMS, "operations must be an array of objects")
        return save_approvals(self.tools.root, operations)

    def approval_apply(
        self,
        params: dict[str, Any],
        *,
        cancel: threading.Event,
        emit: EventSink,
    ) -> dict[str, Any]:
        """Persist optional decisions, then ``eurika fix . --apply-approved`` (Qt Run apply-approved)."""
        self._approved(params, "apply-approved")
        operations = params.get("operations")
        saved: dict[str, Any] | None = None
        if operations is not None:
            if not isinstance(operations, list) or not all(isinstance(item, dict) for item in operations):
                raise RpcError(ERR_INVALID_PARAMS, "operations must be an array of objects")
            saved = save_approvals(self.tools.root, operations)
            if saved.get("error"):
                return {
                    "ok": False,
                    "error": saved.get("error"),
                    "hint": saved.get("hint"),
                    "saved": saved,
                }
        argv = [
            sys.executable,
            "-m",
            "eurika_cli",
            "fix",
            str(self.tools.root),
            "--apply-approved",
        ]
        verify_cmd = params.get("verifyCmd")
        if isinstance(verify_cmd, str) and verify_cmd.strip():
            argv.extend(["--verify-cmd", verify_cmd.strip()])
        result = self.tools._run_process(
            argv,
            cwd=self.tools.root,
            timeout_ms=max(1, min(int(params.get("timeoutMs", 900_000)), 3_600_000)),
            cancel=cancel,
            emit=emit,
        )
        exit_code = int(result.get("exitCode") or 0) if isinstance(result, dict) else 1
        # CLI already announced to chat.jsonl; expose the same summary for RPC/Desktop.
        text = ""
        try:
            from eurika.api.fix_status import format_last_fix_status

            text = f"apply-approved (exit {exit_code})\n\n{format_last_fix_status(self.tools.root)}"
        except Exception:
            text = f"apply-approved (exit {exit_code})"
        return {
            "ok": exit_code == 0,
            "exitCode": exit_code,
            "stdout": result.get("stdout") if isinstance(result, dict) else "",
            "stderr": result.get("stderr") if isinstance(result, dict) else "",
            "saved": saved,
            "command": "eurika fix . --apply-approved",
            "text": text,
        }

    def command_run(
        self,
        params: dict[str, Any],
        *,
        cancel: threading.Event,
        emit: EventSink,
    ) -> dict[str, Any]:
        command = params.get("command")
        if command not in COMMANDS:
            raise RpcError(ERR_INVALID_PARAMS, f"Unsupported command: {command}")
        if command not in READ_ONLY_COMMANDS:
            self._approved(params, f"command {command}")
        extra = params.get("args", [])
        if not isinstance(extra, list) or not all(isinstance(item, str) for item in extra):
            raise RpcError(ERR_INVALID_PARAMS, "args must be a string array")
        argv = [sys.executable, "-m", "eurika_cli", str(command)]
        if command == "explain":
            module = params.get("module")
            if not isinstance(module, str) or not module:
                raise RpcError(ERR_INVALID_PARAMS, "explain requires module")
            argv.extend([module, str(self.tools.root)])
        else:
            argv.append(str(self.tools.root))
        if command == "bug-hunt" and "--propose" not in extra:
            argv.extend(["--propose", "--sandbox"])
        if command == "learn-github" and "--build-patterns" not in extra:
            argv.extend(["--light", "--limit-repos", "2", "--scan", "--build-patterns"])
        argv.extend(extra)
        return self.tools._run_process(
            argv,
            cwd=self.tools.root,
            timeout_ms=max(1, min(int(params.get("timeoutMs", 900_000)), 3_600_000)),
            cancel=cancel,
            emit=emit,
        )

    def product_chat(self, params: dict[str, Any]) -> dict[str, Any]:
        """Qt Chat path: ``chat_send`` (intents, host-admin, scaffolds). Not session/chat."""
        message = params.get("message")
        if not isinstance(message, str) or not message.strip():
            raise RpcError(ERR_INVALID_PARAMS, "message must be a non-empty string")
        from eurika.api.chat import chat_send

        terminal = params.get("terminalText") or params.get("client_terminal_text")
        result = chat_send(
            self.tools.root,
            message.strip(),
            persist_history=True,
            client_terminal_text=str(terminal) if terminal not in (None, "") else None,
        )
        if not isinstance(result, dict):
            return {"ok": False, "text": "", "error": "empty chat result"}
        text = str(result.get("text") or "")
        error = result.get("error")
        return {
            "ok": error in (None, "", False),
            "text": text,
            "error": error,
            "terminal_cmd": result.get("terminal_cmd") or "",
            "terminal_output": result.get("terminal_output") or "",
            "terminal_exit_code": result.get("terminal_exit_code"),
            "open_project": result.get("open_project"),
        }

    def mentions_suggest(self, params: dict[str, Any]) -> dict[str, Any]:
        """@-mention catalog filter (same as Qt ChatInput)."""
        from eurika.api.chat_mentions import mention_candidates

        prefix = str(params.get("prefix") or "")
        limit = params.get("limit", 12)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise RpcError(ERR_INVALID_PARAMS, "limit must be a positive integer")
        return {
            "prefix": prefix.lstrip("@"),
            "candidates": mention_candidates(self.tools.root, prefix, limit=min(limit, 40)),
        }

    def project_create(self, params: dict[str, Any]) -> dict[str, Any]:
        """Sibling project + scaffold. Refuses to re-init the open workspace."""
        self._approved(params, "project create")
        raw = str(params.get("name") or params.get("path") or "").strip()
        if not raw:
            raise RpcError(ERR_INVALID_PARAMS, "name is required")
        if raw.startswith("/") or raw.startswith("~") or "/" in raw or "\\" in raw:
            raise RpcError(
                ERR_INVALID_PARAMS,
                "use a bare sibling name (no path separators)",
            )
        from eurika.api.project_bootstrap import (
            create_project,
            format_create_project_text,
            resolve_create_project_path,
        )

        dest = resolve_create_project_path(self.tools.root, raw)
        if dest == self.tools.root.resolve():
            raise RpcError(ERR_INVALID_PARAMS, "refusing to re-init the open workspace")
        scaffold = str(params.get("scaffold") or "minimal")
        result = create_project(dest, name=raw, scaffold=scaffold)
        return {
            **result,
            "text": format_create_project_text(result),
        }

    @staticmethod
    def _approved(params: dict[str, Any], operation: str) -> None:
        if params.get("approval") is not True:
            raise RpcError(
                ERR_APPROVAL_REQUIRED,
                f"Explicit approval is required for {operation}",
                {"operation": operation, "requiresApproval": True},
            )

    def _market_state(self) -> dict[str, Any]:
        root = resolve_market_root() / ".eurika" / "ml"
        portfolio = self._read_json(root / "paper_portfolio.json", {})
        opens = self._read_json(root / "open_paper.json", {})
        shadows = self._read_json(root / "shadow_open.json", {})
        pending = self._read_json(root / "pending_orders.json", [])
        gate = self._read_json(root / "weights" / "entry_cost_gate.json", {})
        events: list[dict[str, Any]] = []
        journal = root / "market_journal.jsonl"
        try:
            lines = journal.read_text(encoding="utf-8").splitlines()[-100:]
        except OSError:
            lines = []
        for line in lines:
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                events.append(value)
        return {
            "portfolio": portfolio,
            "openPositions": self._items(opens, "positions"),
            "shadowPositions": self._items(shadows, "positions"),
            "pendingOrders": pending if isinstance(pending, list) else [],
            "costGate": gate,
            "events": events,
        }

    def _context_state(self) -> dict[str, Any]:
        """Qt-parity Agent «Контекст» text from dialog_state.json."""
        from eurika.api.chat_context import format_agent_context_panel
        from eurika.api.diff_api import preview_chat_pending_plan
        from eurika.api.learning_api import get_chat_dialog_state
        from eurika.api.task_executor import is_pending_plan_valid

        state = get_chat_dialog_state(self.tools.root)
        pending = state.get("pending_plan") if isinstance(state, dict) else {}
        pending = pending if isinstance(pending, dict) else {}
        plan_valid = bool(pending and is_pending_plan_valid(pending))
        plan_stale = bool(pending and not plan_valid)
        text = format_agent_context_panel(
            state,
            plan_valid=plan_valid,
            plan_stale=plan_stale,
            project_root=self.tools.root,
        )
        token = str(pending.get("token") or "").strip()
        fingerprint = ""
        if pending:
            fingerprint = f"plan:{token}" if token else (
                f"plan:{str(pending.get('intent') or '').strip()}:"
                f"{str(pending.get('target') or '').strip()}"
            )
        preview: dict[str, Any] | None = None
        if pending:
            preview = preview_chat_pending_plan(self.tools.root, pending)
        raw_git = state.get("pending_git_commit") if isinstance(state, dict) else None
        pending_git = raw_git if isinstance(raw_git, dict) else {}
        has_pending_git = bool(pending_git.get("message"))
        if has_pending_git and not fingerprint:
            git_token = str(pending_git.get("token") or "").strip()
            fingerprint = (
                f"git:{git_token}"
                if git_token
                else f"git:{str(pending_git.get('message') or '')[:64]}"
            )
        host_admin = self._host_admin_state()
        has_host_admin = bool(host_admin.get("commands"))
        if has_host_admin and not fingerprint:
            fingerprint = str(host_admin.get("fingerprint") or "host:pending")
        if has_host_admin and not preview:
            preview = {
                "intent": "host_admin",
                "target": "os",
                "unified_diff": str(host_admin.get("preview") or ""),
            }
        return {
            "panel": "context",
            "text": text,
            "data": state,
            "planValid": plan_valid,
            "planStale": plan_stale,
            "token": token,
            "fingerprint": fingerprint,
            "preview": preview,
            "hasPendingGit": has_pending_git,
            "hasPendingHostAdmin": has_host_admin,
            "hostAdmin": host_admin if has_host_admin else None,
            "canReject": bool(pending) or has_pending_git or has_host_admin,
            "canApply": plan_valid or has_pending_git or has_host_admin,
        }

    def _host_admin_state(self) -> dict[str, Any]:
        """Queued OS mutate HITL — same queue Qt Chat «одобрить» applies."""
        try:
            from eurika.api.host_admin import (
                format_pending_host_admin_text,
                load_pending_host_admin,
            )

            pending = load_pending_host_admin(self.tools.root)
        except Exception:
            return {}
        if not isinstance(pending, dict):
            return {}
        cmds = [str(c).strip() for c in (pending.get("commands") or []) if str(c).strip()]
        if not cmds:
            return {}
        updated = str(pending.get("updated_at") or pending.get("created_at") or "")
        return {
            "commands": cmds,
            "updated_at": updated,
            "fingerprint": f"host:{updated}:{cmds[0]}"[:120],
            "preview": format_pending_host_admin_text(pending),
        }

    def context_preview(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Refresh unified diff for dialog_state pending_plan (not Approvals JSON)."""
        del params  # reserved for future filters
        state = self._context_state()
        preview = state.get("preview")
        if not isinstance(preview, dict):
            preview = {"error": "no pending plan"}
        return {
            "panel": "context",
            "token": state.get("token") or "",
            "fingerprint": state.get("fingerprint") or "",
            "planValid": bool(state.get("planValid")),
            "planStale": bool(state.get("planStale")),
            "hasPendingGit": bool(state.get("hasPendingGit")),
            "hasPendingHostAdmin": bool(state.get("hasPendingHostAdmin")),
            "hostAdmin": state.get("hostAdmin"),
            "preview": preview,
        }

    def context_decide(self, params: dict[str, Any]) -> dict[str, Any]:
        """Apply or reject chat HITL pending_plan via chat_send (Qt Apply/Reject)."""
        from eurika.api.chat import chat_send

        decision = str(params.get("decision") or "").strip().lower()
        if decision not in {"apply", "reject"}:
            raise RpcError(ERR_INVALID_PARAMS, "decision must be apply or reject")
        state = self._context_state()
        if decision == "apply":
            self._approved(params, "context apply")
            if not state.get("canApply"):
                raise RpcError(
                    ERR_INVALID_PARAMS,
                    "no valid pending plan to apply",
                    {"planValid": state.get("planValid"), "planStale": state.get("planStale")},
                )
            token = str(params.get("token") or state.get("token") or "").strip()
            expected = str(state.get("token") or "").strip()
            if expected and token and token != expected:
                raise RpcError(
                    ERR_INVALID_PARAMS,
                    "token does not match current pending plan",
                    {"expected": expected},
                )
            message = f"применяй token:{token}" if token else "применяй"
        else:
            if not state.get("canReject"):
                raise RpcError(ERR_INVALID_PARAMS, "no pending plan to reject")
            message = "отклонить"
        result = chat_send(self.tools.root, message)
        text = str(result.get("text") or "") if isinstance(result, dict) else ""
        error = result.get("error") if isinstance(result, dict) else None
        refreshed = self._context_state()
        return {
            "ok": error is None,
            "decision": decision,
            "text": text,
            "error": error,
            "context": refreshed,
        }

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    @staticmethod
    def _items(value: Any, key: str) -> list[Any]:
        if isinstance(value, dict) and isinstance(value.get(key), list):
            return value[key]
        return []
