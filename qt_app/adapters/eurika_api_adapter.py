"""Thin adapter over eurika.api for Qt desktop UI."""

from __future__ import annotations

import os
from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from eurika.api import (
    get_chat_dialog_state,
    explain_module,
    get_graph,
    get_history,
    get_learning_insights,
    get_operational_metrics,
    get_patch_plan,
    get_pending_plan,
    get_risk_prediction,
    get_self_guard,
    get_summary,
    save_approvals,
)
from eurika.api.chat import chat_send as _chat_send


class EurikaApiAdapter:
    """Adapter that keeps project_root handling in one place."""

    def __init__(self, project_root: str = ".") -> None:
        self._project_root = project_root

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

    def get_risk_prediction(self, top_n: int = 10) -> dict[str, Any]:
        """R5: Top modules by regression risk."""
        return get_risk_prediction(self._root(), top_n=top_n)

    def get_history(self, window: int = 5) -> dict[str, Any]:
        return get_history(self._root(), window=window)

    def get_operational_metrics(self, window: int = 10) -> dict[str, Any]:
        return get_operational_metrics(self._root(), window=window)

    def get_learning_insights(self, top_n: int = 5) -> dict[str, Any]:
        return get_learning_insights(self._root(), top_n=top_n)

    def get_chat_dialog_state(self) -> dict[str, Any]:
        return get_chat_dialog_state(self._root())

    def get_pending_plan(self) -> dict[str, Any]:
        return get_pending_plan(self._root())

    def save_approvals(self, operations: list[dict[str, Any]]) -> dict[str, Any]:
        return save_approvals(self._root(), operations)

    def get_patch_plan(self, window: int = 5) -> dict[str, Any] | None:
        return get_patch_plan(self._root(), window=window)

    def explain_module(self, module: str, window: int = 5) -> tuple[str | None, str | None]:
        return explain_module(self._root(), module, window=window)

    @contextmanager
    def _temporary_llm_env(
        self,
        *,
        provider: str,
        openai_model: str,
        ollama_model: str,
        timeout_sec: int,
    ):
        keys = (
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "OLLAMA_OPENAI_MODEL",
            "EURIKA_LLM_TIMEOUT_SEC",
            "EURIKA_OLLAMA_CLI_TIMEOUT_SEC",
        )
        old_values = {key: os.environ.get(key) for key in keys}
        try:
            os.environ["EURIKA_LLM_TIMEOUT_SEC"] = str(timeout_sec if timeout_sec > 0 else 3600)
            os.environ["EURIKA_OLLAMA_CLI_TIMEOUT_SEC"] = str(timeout_sec if timeout_sec > 0 else 0)
            if provider == "openai":
                if openai_model.strip():
                    os.environ["OPENAI_MODEL"] = openai_model.strip()
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
            yield
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def chat_send(
        self,
        *,
        message: str,
        history: list[dict[str, str]] | None,
        provider: str = "auto",
        openai_model: str = "",
        ollama_model: str = "",
        timeout_sec: int = 20,
    ) -> dict[str, Any]:
        with self._temporary_llm_env(
            provider=provider,
            openai_model=openai_model,
            ollama_model=ollama_model,
            timeout_sec=timeout_sec,
        ):
            return _chat_send(self._root(), message, history)

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

