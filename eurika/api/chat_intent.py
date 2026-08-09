"""Intent detection for Chat (ROADMAP 3.5.11.C, 3.6.5).

Includes:
- legacy detect_intent(...) for direct command-like actions;
- interpret_task(...) with confidence + clarification hints;
- parse_mentions(...) for @module, @smell, @risk scoped context (ROADMAP 3.6.5).

Языковой приоритет: русский. Паттерны и сообщения — русский первым, английский вторично.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Tuple

from .chat_intent_detectors import (
    detect_create,
    detect_delete,
    detect_remember_recall,
    detect_refactor,
    detect_run,
    detect_save,
)

MAX_STRUCTURED_PATCH_OPS = 20

KNOWN_SMELL_TYPES = frozenset(
    ("god_module", "hub", "bottleneck", "cyclic_dependency", "cyclic", "long_function", "deep_nesting")
)


def parse_mentions(message: str) -> Dict[str, Any]:
    """Extract @-mentions for scoped context (ROADMAP 3.6.5).

    Returns dict with:
      - modules: list of module/file paths (e.g. @patch_engine.py, @cli/core_handlers.py)
      - smells: list of smell types (e.g. @god_module, @bottleneck)
      - scope_note: human-readable scope for context

    Examples (from eurika scan/doctor):
      "рефактори @patch_engine.py" -> modules=[patch_engine.py], target for refactor
      "рефактори @code_awareness.py с учётом @god_module" -> modules + smells
      "проверь @cli/core_handlers.py" -> scope on long_function candidate
    """
    msg = str(message or "")
    modules: List[str] = []
    smells: List[str] = []
    seen_mod: set[str] = set()
    seen_smell: set[str] = set()
    # @identifier — identifier can be path (contains / or .py) or smell type
    for m in re.finditer(r"@([a-zA-Z0-9_./\-]+)", msg):
        raw = m.group(1).strip()
        if not raw:
            continue
        norm = raw.replace("\\", "/")
        if norm in KNOWN_SMELL_TYPES or norm == "cyclic":
            s = "cyclic_dependency" if norm == "cyclic" else norm
            if s not in seen_smell:
                smells.append(s)
                seen_smell.add(s)
        elif "/" in norm or norm.endswith(".py") or (len(norm) > 2 and "." in norm):
            if norm not in seen_mod and re.match(r"^[a-zA-Z0-9_./\-]+$", norm):
                modules.append(norm)
                seen_mod.add(norm)
    parts: List[str] = []
    if modules:
        parts.append(f"@{' '.join(modules)}")
    if smells:
        parts.append(f"smells:{','.join(smells)}")
    scope_note = (" [Scope: " + "; ".join(parts) + "]" if parts else "")
    return {"modules": modules, "smells": smells, "scope_note": scope_note}


MAX_STRUCTURED_PATCH_TEXT = 20_000


@dataclass(slots=True)
class TaskInterpretation:
    """Structured interpretation of user request for chat orchestration."""

    intent: Optional[str]
    target: Optional[str] = None
    confidence: float = 0.0
    goal: str = ""
    constraints: str = ""
    actions: List[str] = field(default_factory=list)
    risk_level: str = "medium"
    requires_confirmation: bool = True
    needs_clarification: bool = False
    clarifying_question: Optional[str] = None
    entities: Dict[str, str] = field(default_factory=dict)
    plan_steps: List[str] = field(default_factory=list)


def detect_intent(message: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect intent and extract target from user message.

    Returns (intent, target). intent: "save" | "refactor" | "delete" | "create" | "remember" | "recall" | "run_tests" | "run_lint" | "run_command" | None.
    target: file path for save/delete/create; "name:Value" for remember; "name" for recall.
    """
    msg_raw = (message or '').strip()
    msg = msg_raw.lower()
    if not msg:
        return (None, None)
    result = detect_remember_recall(msg_raw, msg)
    if result:
        return result
    result = detect_create(msg)
    if result:
        return result
    result = detect_delete(msg)
    if result:
        return result
    result = detect_save(msg_raw, msg)
    if result:
        return result
    result = detect_refactor(msg_raw, msg)
    if result:
        return result
    result = detect_run(msg_raw, msg)
    if result:
        return result
    return (None, None)


def _extract_create_content(message: str) -> tuple[str, str] | None:
    """Extract an explicit file body from a create-file request."""
    text = str(message or "")
    intent, target = detect_intent(text)
    if intent != "create" or not target:
        return None
    marker = re.search(
        r"(?:со\s+следующим\s+содержимым|с\s+содержимым|"
        r"with\s+(?:the\s+)?following\s+content|with\s+content)",
        text,
        re.IGNORECASE,
    )
    if marker is None:
        return None
    remainder = text[marker.end() :]
    fenced = re.search(r"```(?:[a-zA-Z0-9_+-]+)?[ \t]*\r?\n(.*?)```", remainder, re.DOTALL)
    if fenced is not None:
        content = fenced.group(1).strip("\r\n")
    else:
        body_start = re.search(r":\s*\r?\n", remainder)
        if body_start is None:
            return None
        content = remainder[body_start.end() :].strip("\r\n")
    if not content:
        return None
    return target, content + "\n"


def interpret_task(message: str, history: Optional[List[Dict[str, str]]] = None) -> TaskInterpretation:
    """Interpret user request with confidence and clarification hints."""
    msg_raw = (message or "").strip()
    msg = msg_raw.lower()
    if not msg:
        return TaskInterpretation(intent=None, confidence=0.0)
    sectioned = _extract_goal_constraints_actions(msg_raw)
    structured_patch = _parse_structured_patch_request(msg_raw)
    if structured_patch is not None:
        target, old_text, new_text, verify_target, operations_json, dry_run = structured_patch
        entities = {"old_text": old_text, "new_text": new_text}
        if verify_target:
            entities["verify_target"] = verify_target
        if operations_json:
            entities["operations_json"] = operations_json
            step_title = f"apply {len(json.loads(operations_json))} structured patch operations"
        else:
            step_title = f"apply structured patch in `{target}`"
        if dry_run:
            entities["dry_run"] = "1"
            step_title = "preview structured patch (dry-run)"
        return TaskInterpretation(
            intent="code_edit_patch",
            target=target,
            confidence=0.97,
            goal=sectioned.get("goal", ""),
            constraints=sectioned.get("constraints", ""),
            actions=sectioned.get("actions_lines", []),
            risk_level="high",
            requires_confirmation=True,
            entities=entities,
            plan_steps=[
                step_title,
                ("run verify tests (optional preview)" if dry_run else "run verify tests"),
                ("report changes without write" if dry_run else "rollback if verify fails"),
            ],
        )
    patch_instr = _parse_code_edit_patch_instruction(msg_raw)
    if patch_instr is not None:
        target, old_text, new_text = patch_instr
        return TaskInterpretation(
            intent="code_edit_patch",
            target=target,
            confidence=0.9,
            goal=sectioned.get("goal", ""),
            constraints=sectioned.get("constraints", ""),
            actions=sectioned.get("actions_lines", []),
            risk_level="high",
            requires_confirmation=True,
            entities={"old_text": old_text, "new_text": new_text},
            plan_steps=[
                f"apply patch in `{target}`",
                "run verify tests",
                "rollback if verify fails",
            ],
        )

    create_with_content = _extract_create_content(msg_raw)
    if create_with_content is not None:
        target, content = create_with_content
        return TaskInterpretation(
            intent="create",
            target=target,
            confidence=0.98,
            goal=sectioned.get("goal", ""),
            constraints=sectioned.get("constraints", ""),
            actions=sectioned.get("actions_lines", []),
            risk_level="medium",
            requires_confirmation=True,
            entities={"content": content},
            plan_steps=[
                f"validate path `{target}`",
                f"create `{target}` with provided content",
                "show diff and wait for Apply",
            ],
        )

    has_tabs_ru = re.search(r"\bвклад\w*\b", msg) is not None
    # Task-like request: remove tab in Qt UI.
    if has_tabs_ru and any(token in msg for token in ("удал", "remove", "delete")) and (
        "chat" in msg or "ui" in msg or "интерфейс" in msg or "new tab" in msg
    ):
        target = "qt_app/ui/main_window.py"
        return TaskInterpretation(
            intent="ui_remove_tab",
            target=target,
            confidence=0.9,
            goal=sectioned.get("goal", ""),
            constraints=sectioned.get("constraints", ""),
            actions=sectioned.get("actions_lines", []),
            risk_level="high",
            requires_confirmation=True,
            entities={"tab_name": "New Tab"},
            plan_steps=[
                "update Qt tab builder",
                "remove tab `New Tab`",
                "verify UI smoke",
            ],
        )
    # Task-like request: add empty tab in Qt UI.
    add_tab_markers = ("chat", "ui", "интерфейс", "terminal", "терминал", "эмулятор")
    if has_tabs_ru and any(token in msg for token in ("добав", "созда", "add", "create")) and (
        any(m in msg for m in add_tab_markers)
    ):
        target = "qt_app/ui/main_window.py"
        tab_name = "New Tab"
        if "terminal" in msg or "терминал" in msg:
            tab_name = "Terminal"
        return TaskInterpretation(
            intent="ui_add_empty_tab",
            target=target,
            confidence=0.86,
            goal=sectioned.get("goal", ""),
            constraints=sectioned.get("constraints", ""),
            actions=sectioned.get("actions_lines", []),
            risk_level="high",
            requires_confirmation=True,
            entities={"position": "after Chat", "tab_name": tab_name},
            plan_steps=[
                "update Qt tab builder",
                f"insert tab `{tab_name}` after Chat",
                "verify UI smoke",
            ],
        )
    # Grounded factual query: actual Qt UI tabs.
    if (has_tabs_ru and ("ui" in msg or "интерфейс" in msg)) or ("tabs" in msg and "ui" in msg):
        return TaskInterpretation(
            intent="ui_tabs",
            confidence=0.98,
            goal=sectioned.get("goal", ""),
            constraints=sectioned.get("constraints", ""),
            actions=sectioned.get("actions_lines", []),
            risk_level="low",
            requires_confirmation=False,
            plan_steps=["read factual Qt tabs", "return exact tab list"],
        )

    mentions = parse_mentions(msg_raw)
    intent, target = detect_intent(msg_raw)  # type: ignore[assignment]
    if intent:
        if intent == "refactor" and (not target or target == ".") and mentions.get("modules"):
            target = mentions["modules"][0]
        intent_entities = {}
        if mentions.get("modules"):
            intent_entities["scope_modules"] = ",".join(mentions["modules"])
        if mentions.get("smells"):
            intent_entities["scope_smells"] = ",".join(mentions["smells"])
        confidence = 0.9 if target else 0.78
        return TaskInterpretation(
            intent=intent,
            target=target,
            confidence=confidence,
            goal=sectioned.get("goal", ""),
            constraints=sectioned.get("constraints", ""),
            actions=sectioned.get("actions_lines", []),
            risk_level=_risk_for_intent(intent),
            requires_confirmation=_risk_for_intent(intent) != "low",
            entities=intent_entities,
            plan_steps=_plan_for_intent(intent, target),
        )

    # Ambiguous imperative-like requests should ask clarification instead of hallucinating.
    # Русский приоритет: маркеры на русском первыми.
    imperative_markers = (
        "сделай",
        "почини",
        "исправь",
        "добавь",
        "перепиши",
        "реализуй",
        "улучши",
        "оптимизируй",
        "optimize",
        "fix it",
        "do it",
    )
    if any(marker in msg for marker in imperative_markers):
        return TaskInterpretation(
            intent="ambiguous_request",
            confidence=0.35,
            goal=sectioned.get("goal", ""),
            constraints=sectioned.get("constraints", ""),
            actions=sectioned.get("actions_lines", []),
            needs_clarification=True,
            clarifying_question=(
                "Уточни, пожалуйста, цель и границы задачи: "
                "что именно изменить, в каком файле/модуле и какой ожидаемый результат?"
            ),
            plan_steps=["collect missing constraints", "confirm target module/file", "execute once clarified"],
        )

    # Optional small context bump when user asks to continue previous task.
    if history and any(token in msg for token in ("продолжай", "continue", "как выше")):
        # Try to recover actionable intent from recent user message.
        for item in reversed(history[-8:]):
            if str(item.get("role", "")).lower() != "user":
                continue
            prev = str(item.get("content", "")).strip()
            if not prev or prev.lower() == msg:
                continue
            prev_intent, prev_target = detect_intent(prev)
            if prev_intent:
                return TaskInterpretation(
                    intent=prev_intent,
                    target=prev_target,
                    confidence=0.72,
                    goal=sectioned.get("goal", ""),
                    constraints=sectioned.get("constraints", ""),
                    actions=sectioned.get("actions_lines", []),
                    risk_level=_risk_for_intent(prev_intent),
                    requires_confirmation=_risk_for_intent(prev_intent) != "low",
                    entities={"source": "history"},
                    plan_steps=_plan_for_intent(prev_intent, prev_target),
                )
        return TaskInterpretation(intent="continue_context", confidence=0.45)

    return TaskInterpretation(intent=None, confidence=0.2)


def _plan_for_intent(intent: str, target: Optional[str]) -> List[str]:
    """Minimal deterministic step plan for recognized intents."""
    tgt = target or "."
    if intent == "save":
        return [f"generate code for target `{tgt}`", "extract code block", f"write `{tgt}` safely"]
    if intent == "create":
        return [f"validate path `{tgt}`", f"create empty file `{tgt}`", "report result"]
    if intent == "delete":
        return [f"validate path `{tgt}`", f"delete `{tgt}` safely", "report result"]
    if intent == "refactor":
        return ["run eurika fix flow", "collect verify output", "report success/fail summary"]
    if intent == "run_tests":
        return [f"run pytest for `{tgt or 'tests'}`", "collect exit code", "return verification output"]
    if intent == "run_lint":
        return ["run linter", "collect diagnostics", "return lint summary"]
    if intent == "run_command":
        return [f"validate command `{tgt}`", "execute command in project root", "return structured output"]
    if intent in {"remember", "recall"}:
        return ["read/update user context", "persist to chat memory", "return deterministic response"]
    return ["analyze request", "choose safe action", "return result"]


def _risk_for_intent(intent: str) -> str:
    if intent in {"ui_tabs", "project_ls", "project_tree", "recall", "run_tests", "run_lint"}:
        return "low"
    if intent in {"remember", "create"}:
        return "medium"
    return "high"


def _parse_code_edit_patch_instruction(message: str) -> tuple[str, str, str] | None:
    """Parse direct replacement instruction: replace old with new in file."""
    text = str(message or "").strip()
    if not text:
        return None
    patterns = [
        r"(?:замени|replace)\s+в\s+файле\s+([a-zA-Z0-9_./\\-]+)\s+['\"](.+?)['\"]\s+на\s+['\"](.+?)['\"]",
        r"(?:в\s+файле)\s+([a-zA-Z0-9_./\\-]+)\s+(?:замени|replace)\s+['\"](.+?)['\"]\s+(?:на|with)\s+['\"](.+?)['\"]",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        target = m.group(1).strip()
        old_text = m.group(2)
        new_text = m.group(3)
        if target and old_text:
            return target, old_text, new_text
    return None


def _parse_structured_patch_request(message: str) -> tuple[str, str, str, str, str, bool] | None:
    """Parse structured patch payload from plain JSON or fenced ```json block.

    Expected shape:
      Single:
        {
          "intent": "code_edit_patch",
          "target": "path/to/file.py",
          "old_text": "...",
          "new_text": "...",
          "verify_target": "tests/test_x.py"   # optional
        }

      Batch:
        {
          "schema_version": 1,
          "intent": "code_edit_patch",
          "operations": [
            {"target": "a.py", "old_text": "...", "new_text": "..."},
            {"target": "b.py", "old_text": "...", "new_text": "..."}
          ],
          "verify_target": "tests/test_x.py",  # optional
          "dry_run": true                       # optional
        }
    """
    text = str(message or "").strip()
    if not text:
        return None

    candidates: List[str] = []
    candidates.append(text)
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())

    for raw in candidates:
        if not raw.startswith("{"):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        schema_version = payload.get("schema_version")
        if schema_version is not None and str(schema_version).strip() not in {"1", "v1"}:
            continue
        intent = str(payload.get("intent") or "").strip().lower()
        if intent not in {"code_edit_patch", "patch", "replace_text"}:
            continue
        verify_target = str(payload.get("verify_target") or "").strip()
        dry_run = bool(payload.get("dry_run"))
        operations = payload.get("operations")
        if isinstance(operations, list) and operations:
            if len(operations) > MAX_STRUCTURED_PATCH_OPS:
                continue
            normalized_ops: List[Dict[str, Any]] = []
            first_target = ""
            first_old = ""
            first_new = ""
            for item in operations:
                if not isinstance(item, dict):
                    normalized_ops = []
                    break
                target = str(item.get("target") or "").strip()
                old_text = str(item.get("old_text") or "")
                new_text = str(item.get("new_text") or "")
                item_verify = str(item.get("verify_target") or "").strip()
                if not target or not old_text:
                    normalized_ops = []
                    break
                if len(old_text) > MAX_STRUCTURED_PATCH_TEXT or len(new_text) > MAX_STRUCTURED_PATCH_TEXT:
                    normalized_ops = []
                    break
                if not first_target:
                    first_target, first_old, first_new = target, old_text, new_text
                op: Dict[str, Any] = {"target": target, "old_text": old_text, "new_text": new_text}
                if item_verify:
                    op["verify_target"] = item_verify
                normalized_ops.append(op)
            if normalized_ops:
                return (
                    first_target,
                    first_old,
                    first_new,
                    verify_target,
                    json.dumps(normalized_ops, ensure_ascii=False),
                    dry_run,
                )
            continue
        target = str(payload.get("target") or "").strip()
        old_text = str(payload.get("old_text") or "")
        new_text = str(payload.get("new_text") or "")
        if not target or not old_text:
            continue
        if len(old_text) > MAX_STRUCTURED_PATCH_TEXT or len(new_text) > MAX_STRUCTURED_PATCH_TEXT:
            continue
        return target, old_text, new_text, verify_target, "", dry_run
    return None


def _extract_goal_constraints_actions(message: str) -> Dict[str, Any]:
    """Parse optional multiline sections: goal/constraints/actions."""
    text = str(message or "")
    out: Dict[str, Any] = {"goal": "", "constraints": "", "actions": "", "actions_lines": []}
    patterns = {
        "goal": r"(?:^|\n)\s*(?:цель|goal)\s*:\s*(.+)",
        "constraints": r"(?:^|\n)\s*(?:границы|constraints?)\s*:\s*(.+)",
        "actions": r"(?:^|\n)\s*(?:задачи|действия|tasks?|actions?)\s*:\s*(.+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        value = m.group(1).strip()
        # Stop at next section marker if captured with DOTALL.
        value = re.split(
            r"\n\s*(?:цель|goal|границы|constraints?|задачи|действия|tasks?|actions?)\s*:",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        out[key] = value
    actions_lines: List[str] = []
    if out["actions"]:
        for line in str(out["actions"]).splitlines():
            item = line.strip(" -\t")
            if item:
                actions_lines.append(item)
    out["actions_lines"] = actions_lines
    return out

def extract_code_block(text: str) -> Optional[str]:
    """Extract first ```python ... ``` or ``` ... ``` block from LLM response."""
    if not text:
        return None
    m = re.search('```(?:python)?\\s*\\n(.*?)```', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


