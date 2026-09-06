"""Cursor SDK: model catalog, chat completions, and eval judge.

Requires ``CURSOR_API_KEY`` in the environment or project ``.env``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_CURSOR_MODEL = "composer-2.5"
ROUTER_MODEL_IDS = frozenset({"auto-smart"})
OPTIMIZE_FOR_VALUES = ("cost", "balanced", "intelligence")
STUB_CURSOR_MODELS: tuple[tuple[str, str], ...] = (
    ("composer-2.5", "Composer 2.5"),
    ("composer-2", "Composer 2"),
    ("default", "Auto"),
)


def _workspace(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def load_cursor_key(workspace: str | Path) -> str:
    from eurika.utils.env import CURSOR_SECRET_ENV_KEYS, load_project_dotenv

    root = _workspace(workspace)
    load_project_dotenv(root, keys=CURSOR_SECRET_ENV_KEYS)
    key = (os.environ.get("CURSOR_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "CURSOR_API_KEY is not set. Put it in the project .env (gitignored) "
            "or export it in the shell."
        )
    return key


def cursor_key_status(workspace: str | Path = ".") -> dict[str, Any]:
    """Presence check — never returns the secret."""
    from eurika.utils.env import CURSOR_SECRET_ENV_KEYS, load_project_dotenv

    root = _workspace(workspace)
    load_project_dotenv(root, keys=CURSOR_SECRET_ENV_KEYS)
    key = (os.environ.get("CURSOR_API_KEY") or "").strip()
    return {"api_key_set": bool(key), "prefix": (key[:4] + "…") if key else ""}


def list_models(workspace: str | Path = ".") -> list[str]:
    return [item["id"] for item in list_model_catalog(workspace)]


def list_model_catalog(workspace: str | Path = ".") -> list[dict[str, str]]:
    """Live catalog from Cursor. Falls back to stubs if the SDK call fails."""
    from cursor_sdk import Cursor

    load_cursor_key(workspace)
    models = Cursor.models.list()
    out: list[dict[str, str]] = []
    for item in models:
        mid = getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else None)
        if not mid:
            continue
        label = (
            getattr(item, "display_name", None)
            or (item.get("display_name") if isinstance(item, dict) else None)
            or str(mid)
        )
        if str(mid) == "auto-smart":
            label = "Auto + Router"
        elif str(mid) in {"default", "auto"}:
            label = "Auto"
        out.append({"id": str(mid), "label": str(label)})
    return out


def stub_model_catalog() -> list[dict[str, str]]:
    return [{"id": mid, "label": label} for mid, label in STUB_CURSOR_MODELS]


def selected_cursor_model() -> str:
    return (os.environ.get("CURSOR_MODEL") or DEFAULT_CURSOR_MODEL).strip() or DEFAULT_CURSOR_MODEL


def selected_optimize_for() -> str:
    raw = (os.environ.get("CURSOR_OPTIMIZE_FOR") or "").strip().lower()
    return raw if raw in OPTIMIZE_FOR_VALUES else ""


def is_router_model(model_id: str) -> bool:
    return (model_id or "").strip().lower() == "auto-smart"


def normalize_cursor_model(model_id: str | None) -> str:
    mid = (model_id or selected_cursor_model()).strip() or DEFAULT_CURSOR_MODEL
    if mid == "auto":
        return "default"
    return mid


def build_agent_model(model_id: str | None = None, optimize_for: str | None = None) -> Any:
    """SDK ``model=``. ``default`` is Auto; ``auto-smart`` is Router (Teams only)."""
    mid = normalize_cursor_model(model_id)
    opt = (optimize_for if optimize_for is not None else selected_optimize_for()).strip().lower()
    if mid == "auto-smart" and opt in OPTIMIZE_FOR_VALUES:
        from cursor_sdk import ModelParameterValue, ModelSelection

        return ModelSelection(
            id="auto-smart",
            params=[ModelParameterValue(id="optimize_for", value=opt)],
        )
    return mid


def _unavailable_model_id(error: str) -> str | None:
    import re

    match = re.search(r"Cannot use this model:\s*([A-Za-z0-9_-]+)", error or "", flags=re.I)
    return match.group(1) if match else None


def _fallback_cursor_model(failed: str) -> str:
    if failed in {"auto-smart", "auto"}:
        return "default"
    if failed == "default":
        return DEFAULT_CURSOR_MODEL
    return DEFAULT_CURSOR_MODEL


def complete_chat(
    prompt: str,
    *,
    workspace: str | Path | None = None,
    model: str | None = None,
    optimize_for: str | None = None,
    lease_priority: str = "interactive",
    lease_purpose: str = "chat",
    lease_holder: str | None = None,
) -> tuple[str | None, str | None]:
    """Text-only Cursor completion for Eurika Chat (no workspace tools)."""
    root = _workspace(workspace or os.environ.get("EURIKA_CURSOR_CWD") or ".")
    result = prompt_local(
        prompt,
        workspace=root,
        model=model or selected_cursor_model(),
        optimize_for=optimize_for,
        tools=(),
        lease_priority=lease_priority,
        lease_purpose=lease_purpose,
        lease_holder=lease_holder,
    )
    if result.get("ok"):
        text = str(result.get("text") or "").strip()
        return (text or None, None if text else "Cursor вернул пустой ответ")
    err = str(result.get("error") or result.get("status") or "Cursor SDK error")
    return (None, err)


def prompt_local(
    message: str,
    *,
    workspace: str | Path = ".",
    model: str = DEFAULT_CURSOR_MODEL,
    optimize_for: str | None = None,
    tools: tuple[str, ...] | None = None,
    lease_priority: str = "interactive",
    lease_purpose: str = "cursor",
    lease_holder: str | None = None,
) -> dict[str, Any]:
    """One-shot local Cursor agent against ``workspace``. Always call wait via prompt()."""
    from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions

    from eurika.orchestration.llm_lease import acquire, release

    root = _workspace(workspace)
    holder = (lease_holder or f"cursor:{lease_purpose}:{os.getpid()}").strip()
    got = acquire(
        root,
        holder=holder,
        priority=lease_priority,
        purpose=lease_purpose,
    )
    if not got.get("ok"):
        who = got.get("holder") or got.get("purpose") or "other"
        return {
            "ok": False,
            "status": "lease_busy",
            "error": f"LLM lease busy ({who})",
            "retryable": True,
            "lease": got,
        }
    try:
        api_key = load_cursor_key(root)
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "model": build_agent_model(model, optimize_for),
            "local": LocalAgentOptions(cwd=root),
        }
        if tools is not None:
            kwargs["tools"] = list(tools)
        try:
            result = Agent.prompt(message, AgentOptions(**kwargs))
        except CursorAgentError as err:
            failed = _unavailable_model_id(str(err))
            fallback = _fallback_cursor_model(failed) if failed else ""
            wanted = normalize_cursor_model(model)
            if failed and fallback and fallback != wanted and fallback != failed:
                kwargs["model"] = build_agent_model(fallback, None)
                try:
                    result = Agent.prompt(message, AgentOptions(**kwargs))
                except CursorAgentError as retry_err:
                    return {
                        "ok": False,
                        "status": "startup_error",
                        "error": str(retry_err),
                        "retryable": bool(getattr(retry_err, "is_retryable", False)),
                        "request_id": getattr(retry_err, "request_id", None),
                    }
            else:
                return {
                    "ok": False,
                    "status": "startup_error",
                    "error": str(err),
                    "retryable": bool(getattr(err, "is_retryable", False)),
                    "request_id": getattr(err, "request_id", None),
                }
        payload = getattr(result, "result", None)
        text = payload if isinstance(payload, str) else str(payload or "")
        status = str(getattr(result, "status", "") or "")
        return {
            "ok": status in {"finished", "ok", "success", ""} and bool(text),
            "status": status or "finished",
            "text": text,
            "run_id": getattr(result, "id", None),
            "agent_id": getattr(result, "agent_id", None),
        }
    finally:
        release(root, holder=holder)


def judge_eurika_answer(
    *,
    task: str,
    answer: str,
    workspace: str | Path = ".",
    model: str = DEFAULT_CURSOR_MODEL,
) -> dict[str, Any]:
    """Score a Eurika reply. Read-only: do not edit, commit, or push."""
    rubric = (
        "You are the judge for Eurika eval. The student is Eurika's own chat/agent.\n"
        "Read the repo if needed. Do not edit files. Do not run git write commands.\n"
        "Return JSON only: "
        '{"verdict":"pass"|"fail"|"partial","score":0-5,"feedback":"...","expected":"..."}\n'
        "Score grounding (cited real files/functions) and whether the parity gap is correct.\n"
        f"TASK:\n{task.strip()}\n\nEURIKA_ANSWER:\n{answer.strip()}\n"
    )
    return prompt_local(rubric, workspace=workspace, model=model)


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cursor SDK judge for a running Eurika workspace")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--model", default=DEFAULT_CURSOR_MODEL)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("models")
    pr = sub.add_parser("prompt")
    pr.add_argument("message")
    args = parser.parse_args(argv)
    root = args.workspace
    if args.cmd == "status":
        json.dump(cursor_key_status(root), sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    if args.cmd == "models":
        try:
            ids = list_models(root)
        except Exception as exc:
            json.dump({"ok": False, "error": str(exc)}, sys.stdout, ensure_ascii=False)
            sys.stdout.write("\n")
            return 1
        json.dump({"ok": True, "models": ids}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    result = prompt_local(args.message, workspace=root, model=args.model)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
