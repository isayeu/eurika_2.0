"""Parse model chat responses into final text or structured tool calls."""

from __future__ import annotations

import json
import re
from typing import Any

from .contracts import TOOL_CONTRACTS


def split_model_notice(raw: str) -> tuple[str, str]:
    value = raw or ""
    match = re.search(r"\n+\s*—\s*\n(Лимит[\s\S]+)\Z", value)
    if not match:
        return value, ""
    return value[: match.start()].rstrip(), match.group(1).strip()


def loads_json_value(value: str) -> Any:
    try:
        loaded = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        start_obj = (value or "").find("{")
        start_arr = (value or "").find("[")
        starts = [item for item in (start_obj, start_arr) if item >= 0]
        if not starts:
            return None
        try:
            loaded, _end = json.JSONDecoder().raw_decode(value, min(starts))
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    return loaded if isinstance(loaded, (dict, list)) else None


def loads_json_object(value: str) -> dict[str, Any] | None:
    loaded = loads_json_value(value)
    return loaded if isinstance(loaded, dict) else None


def coerce_tool_call(obj: Any) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    raw_fn = obj.get("function")
    fn: dict[str, Any] = raw_fn if isinstance(raw_fn, dict) else {}
    name = obj.get("tool") or obj.get("name") or fn.get("name")
    arguments = obj.get("arguments")
    if arguments is None:
        arguments = obj.get("args") or obj.get("parameters") or fn.get("arguments") or fn.get("parameters")
    if not isinstance(name, str) or name not in TOOL_CONTRACTS:
        return None
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return None
    arguments = dict(arguments)
    for key in ("path", "oldText", "newText", "content"):
        value = obj.get(key)
        if key not in arguments and isinstance(value, str) and value:
            arguments[key] = value
    call: dict[str, Any] = {"tool": name, "arguments": arguments}
    call_id = obj.get("callId") or obj.get("id")
    if call_id:
        call["callId"] = str(call_id)
    return call


def extract_tool_calls(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        if parsed.get("type") == "final":
            return []
        raw = parsed.get("toolCalls") or parsed.get("tool_calls") or parsed.get("tools")
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = [raw]
        else:
            one = coerce_tool_call(parsed)
            return [one] if one else []
    else:
        return []
    calls: list[dict[str, Any]] = []
    for item in items:
        call = coerce_tool_call(item)
        if call:
            calls.append(call)
    return calls


def unwrap_json_payload(value: str) -> str:
    text = (value or "").strip()
    # Take the whole fence body. A non-greedy `{ ... }` cut stops at the first
    # nested object (search arguments) and then the tool-call is treated as final text.
    fenced = re.match(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    opened = re.match(r"```(?:json)?\s*", text, flags=re.IGNORECASE)
    if opened:
        text = text[opened.end() :]
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def parse_model_response(raw: str) -> dict[str, Any]:
    body, _notice = split_model_notice(raw or "")
    value = unwrap_json_payload(body)
    parsed = loads_json_value(value)
    if parsed is None and value != body.strip():
        parsed = loads_json_value(body)
    if parsed is None:
        return {"type": "final", "text": body.strip() or (raw or "")}
    calls = extract_tool_calls(parsed)
    if calls:
        return {"type": "tool_calls", "toolCalls": calls}
    if isinstance(parsed, dict):
        if parsed.get("type") == "final":
            return parsed
        text = parsed.get("text")
        if isinstance(text, str) and text.strip():
            return {"type": "final", "text": text.strip()}
    return {"type": "final", "text": body.strip() or (raw or "")}
