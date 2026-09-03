"""Thin adapter over eurika.api for Qt desktop UI."""

from __future__ import annotations

import os
from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from report.explain_format import explain_module
from eurika.api import (
    get_chat_dialog_state,
    get_firewall_violations_detail,
    get_graph,
    get_history,
    get_learning_insights,
    get_metrics,
    get_operational_metrics,
    get_patch_plan,
    get_pending_plan,
    preview_chat_pending_plan,
    preview_operation,
    get_risk_prediction,
    get_self_guard,
    get_summary,
    save_approvals,
)
from eurika.api import get_suggest_plan_data as _get_suggest_plan_data
from eurika.api.chat import chat_send as _chat_send, save_chat_feedback as _save_chat_feedback
from eurika.api.chat_host_ops import PrivilegePrompt
from eurika.utils.env import LLM_ENV_LOCK_KEY
from qt_app.adapters.agent_gateway import AgentGatewayMixin


class EurikaApiAdapter(AgentGatewayMixin):
    """Adapter that keeps project_root handling in one place."""

    def __init__(self, project_root: str = ".") -> None:
        self._project_root = project_root
        self._agent_session_id: str | None = None

    def set_project_root(self, project_root: str) -> None:
        self._project_root = project_root

    def _root(self) -> Path:
        return Path(self._project_root).resolve()

    def get_summary(self) -> dict[str, Any]:
        return get_summary(self._root())

    def get_graph(self) -> dict[str, Any]:
        """Dependency graph for UI: {nodes, edges} in vis-network format."""
        return get_graph(self._root())

    def get_self_guard(self) -> dict[str, Any]:
        """R5: SELF-GUARD health gate (violations, trend alarms, complexity budget)."""
        return get_self_guard(self._root())

    def get_firewall_violations_detail(self) -> dict[str, Any]:
        """CR-A3: Dependency firewall violations for GUI (forbidden, layer, subsystem bypass)."""
        return get_firewall_violations_detail(self._root())

    def get_risk_prediction(self, top_n: int = 10) -> dict[str, Any]:
        """R5: Top modules by regression risk."""
        return get_risk_prediction(self._root(), top_n=top_n)

    def get_history(self, window: int = 5) -> dict[str, Any]:
        return get_history(self._root(), window=window)

    def get_metrics(self) -> dict[str, Any]:
        """MetricVector + Energy (ROADMAP §5.7 Execution Model)."""
        return get_metrics(self._root())

    def get_operational_metrics(self, window: int = 10) -> dict[str, Any]:
        return get_operational_metrics(self._root(), window=window)

    def get_learning_insights(self, top_n: int = 5) -> dict[str, Any]:
        return get_learning_insights(self._root(), top_n=top_n)

    def get_chat_dialog_state(self) -> dict[str, Any]:
        return get_chat_dialog_state(self._root())

    def get_pending_plan(self) -> dict[str, Any]:
        return get_pending_plan(self._root())

    def preview_operation(self, op: dict[str, Any]) -> dict[str, Any]:
        """Preview single-file op: returns old_content, new_content, unified_diff (ROADMAP 3.6.7)."""
        return preview_operation(self._root(), op)

    def preview_chat_pending_plan(self, pending_plan: dict[str, Any] | None = None) -> dict[str, Any]:
        """Preview chat HITL pending_plan as unified diff (Agent Diff)."""
        plan = pending_plan
        if plan is None:
            state = get_chat_dialog_state(self._root())
            plan = state.get("pending_plan") if isinstance(state, dict) else None
        return preview_chat_pending_plan(self._root(), plan if isinstance(plan, dict) else None)

    def save_approvals(self, operations: list[dict[str, Any]]) -> dict[str, Any]:
        return save_approvals(self._root(), operations)

    def get_patch_plan(self, window: int = 5) -> dict[str, Any] | None:
        return get_patch_plan(self._root(), window=window)

    def explain_module(self, module: str, window: int = 5) -> tuple[str | None, str | None]:
        return explain_module(self._root(), module, window=window)

    def get_suggest_plan_data(self, window: int = 5) -> dict[str, Any]:
        """Suggest-plan: summary, recommendations, history (ROADMAP §7)."""
        return _get_suggest_plan_data(self._root(), window=window)

    @contextmanager
    def _temporary_llm_env(
        self,
        *,
        provider: str,
        openai_model: str,
        ollama_model: str,
        timeout_sec: int,
        openai_base_url: str = "",
        cursor_model: str = "",
        cursor_optimize: str = "",
    ):
        keys = (
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "OLLAMA_OPENAI_MODEL",
            "EURIKA_LLM_TIMEOUT_SEC",
            "EURIKA_OLLAMA_CLI_TIMEOUT_SEC",
            "EURIKA_CHAT_PROVIDER",
            "CURSOR_MODEL",
            "CURSOR_OPTIMIZE_FOR",
            "EURIKA_CURSOR_CWD",
            LLM_ENV_LOCK_KEY,
        )
        old_values = {key: os.environ.get(key) for key in keys}
        try:
            os.environ[LLM_ENV_LOCK_KEY] = "1"
            os.environ["EURIKA_LLM_TIMEOUT_SEC"] = str(timeout_sec if timeout_sec > 0 else 3600)
            cli_timeout = timeout_sec if timeout_sec > 0 else 0
            if provider in {"auto", "ollama"} and cli_timeout > 0:
                cli_timeout = max(cli_timeout, 120)
            os.environ["EURIKA_OLLAMA_CLI_TIMEOUT_SEC"] = str(cli_timeout)
            os.environ["EURIKA_CHAT_PROVIDER"] = provider
            os.environ["EURIKA_CURSOR_CWD"] = str(self._root())
            base = (openai_base_url or "").strip()
            if base and provider in {"auto", "openai", "codex"}:
                os.environ["OPENAI_BASE_URL"] = base
            if provider == "cursor":
                if cursor_model.strip():
                    os.environ["CURSOR_MODEL"] = cursor_model.strip()
                if cursor_optimize.strip():
                    os.environ["CURSOR_OPTIMIZE_FOR"] = cursor_optimize.strip()
                else:
                    os.environ.pop("CURSOR_OPTIMIZE_FOR", None)
            elif provider in {"openai", "codex"}:
                if openai_model.strip():
                    os.environ["OPENAI_MODEL"] = openai_model.strip()
                elif provider == "codex" and not (os.environ.get("OPENAI_MODEL") or "").strip():
                    default = (os.environ.get("OPENAI_CODEX_MODEL") or "gpt-4o-mini").strip()
                    os.environ["OPENAI_MODEL"] = default
                os.environ.pop("OLLAMA_OPENAI_MODEL", None)
            elif provider == "ollama":
                # Force Ollama as primary path for chat call.
                os.environ.pop("OPENAI_API_KEY", None)
                os.environ.pop("OPENAI_BASE_URL", None)
                os.environ.pop("OPENAI_MODEL", None)
                if ollama_model.strip():
                    os.environ["OLLAMA_OPENAI_MODEL"] = ollama_model.strip()
            else:
                if openai_model.strip():
                    os.environ["OPENAI_MODEL"] = openai_model.strip()
                if ollama_model.strip():
                    os.environ["OLLAMA_OPENAI_MODEL"] = ollama_model.strip()
            from eurika.utils.llm_presets import apply_retired_groq_model

            apply_retired_groq_model(os.environ)
            yield
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            from eurika.utils.env import apply_qt_chat_routing

            apply_qt_chat_routing()

    def chat_send(
        self,
        *,
        message: str,
        history: list[dict[str, str]] | None,
        provider: str = "auto",
        openai_model: str = "",
        ollama_model: str = "",
        timeout_sec: int = 20,
        openai_base_url: str = "",
        cursor_model: str = "",
        cursor_optimize: str = "",
        on_system_action: Callable[[str], None] | None = None,
        run_command_with_result: Callable[[str], tuple[str, int]] | None = None,
        privilege_prompt: PrivilegePrompt | None = None,
        client_terminal_text: str | None = None,
    ) -> dict[str, Any]:
        from qt_app.ui.agent_pending import wants_local_agent

        if wants_local_agent(message):
            try:
                return self.agent_chat(message)
            except FileNotFoundError as exc:
                return {
                    "ok": False,
                    "text": "",
                    "error": (
                        "Local agent HTTP недоступен "
                        f"({exc}). Запустите Qt/Desktop с gateway "
                        "или поднимите agent HTTP; coding-запрос не "
                        "уходит в обычный chat втихую."
                    ),
                    "pendingToolCalls": [],
                    "approvalsQueued": 0,
                }
        with self._temporary_llm_env(
            provider=provider,
            openai_model=openai_model,
            ollama_model=ollama_model,
            timeout_sec=timeout_sec,
            openai_base_url=openai_base_url,
            cursor_model=cursor_model,
            cursor_optimize=cursor_optimize,
        ):
            return _chat_send(
                self._root(),
                message,
                history,
                on_system_action=on_system_action,
                run_command_with_result=run_command_with_result,
                privilege_prompt=privilege_prompt,
                client_terminal_text=client_terminal_text,
            )

    def save_chat_feedback(
        self,
        *,
        user_message: str,
        assistant_message: str,
        helpful: bool,
        clarification: str | None = None,
    ) -> None:
        """Save feedback for last chat exchange (ROADMAP 3.6.8 Phase 3)."""
        _save_chat_feedback(
            self._root(),
            user_message=user_message,
            assistant_message=assistant_message,
            helpful=helpful,
            clarification=clarification,
        )

    def list_ollama_models(self, base_url: str = "http://127.0.0.1:11434") -> list[str]:
        """Return locally installed Ollama model names from /api/tags."""
        url = f"{base_url.rstrip('/')}/api/tags"
        req = Request(url=url, method="GET")
        with urlopen(req, timeout=1.8) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        models = payload.get("models") if isinstance(payload, dict) else []
        if not isinstance(models, list):
            return []
        names: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
        return names

    def is_ollama_healthy(self, base_url: str = "http://127.0.0.1:11434") -> bool:
        """Best-effort Ollama API health check."""
        try:
            _ = self.list_ollama_models(base_url=base_url)
            return True
        except (URLError, OSError, json.JSONDecodeError, TimeoutError):
            return False

