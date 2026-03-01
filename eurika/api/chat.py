"""Chat endpoint for UI (ROADMAP 3.5.11.A, 3.5.11.B, 3.5.11.C). Eurika layer → Ollama; logs to .eurika/chat_history/; RAG; intent→action (save, refactor)."""
from __future__ import annotations
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from eurika.api.task_executor import build_task_spec, execute_spec, has_capability, is_pending_plan_valid, make_pending_plan

DEFAULT_SAVE_TARGET = "app.py"

def _load_user_context(root: Path) -> Dict[str, str]:
    """Load user context (name, etc.) from .eurika/chat_history/user_context.json."""
    path = root / '.eurika' / 'chat_history' / 'user_context.json'
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return {k: str(v) for k, v in data.items() if isinstance(v, (str, int, float))}
    except Exception:
        pass
    return {}

def _save_user_context(root: Path, data: Dict[str, str]) -> None:
    """Save user context to .eurika/chat_history/user_context.json."""
    path = root / '.eurika' / 'chat_history' / 'user_context.json'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass

def _build_chat_context(root: Path, scope: Optional[Dict[str, Any]] = None) -> str:
    """Build context snippet from summary + recent_events + user context for chat prompt.

    ROADMAP 3.6.5, R5 2.3: when scope has modules/smells from @-mentions, enrich context
    with scoped module details and filtered risks. Prioritize answers regarding the scope.
    """
    from eurika.api import get_graph, get_recent_events, get_summary
    lines: List[str] = []
    if scope:
        scope_parts: List[str] = []
        if scope.get('modules'):
            scope_parts.append(f"Focus module(s): {', '.join(scope['modules'])}")
        if scope.get('smells'):
            scope_parts.append(f"Focus smell(s): {', '.join(scope['smells'])}")
        if scope_parts:
            lines.append('[Scope: ' + '; '.join(scope_parts) + ']. Prioritize answers regarding the focused scope when relevant.')
        # R5 2.3: add scoped module details (fan-in, fan-out) from graph
        if scope.get('modules'):
            try:
                graph_data = get_graph(root)
                if graph_data and not graph_data.get('error'):
                    nodes = graph_data.get('nodes') or []
                    scope_mods = scope['modules']
                    details: List[str] = []
                    for node in nodes:
                        nid = node.get('id', '')
                        if any(m in nid or nid.endswith(m) for m in scope_mods):
                            fi = node.get('fan_in', 0)
                            fo = node.get('fan_out', 0)
                            details.append(f"{nid} (fan-in={fi}, fan-out={fo})")
                    if details:
                        lines.append('Scoped module details: ' + '; '.join(details[:5]))
            except Exception:
                pass
    try:
        uc = _load_user_context(root)
        if uc:
            parts = [f'{k}={v}' for k, v in uc.items()]
            lines.append(f"[User: {'; '.join(parts)}]")
    except Exception:
        pass
    try:
        summary = get_summary(root)
        if summary and (not summary.get('error')):
            sys_info = summary.get('system') or {}
            modules = sys_info.get('modules', '?')
            deps = sys_info.get('dependencies', '?')
            cycles = sys_info.get('cycles', '?')
            lines.append(f'Project: {modules} modules, {deps} deps, {cycles} cycles.')
            risks = summary.get('risks') or []
            if risks:
                scope_modules = set(scope.get('modules') or []) if scope else set()
                scope_smells = set((s or '').lower() for s in (scope.get('smells') or [])) if scope else set()
                filtered = risks
                if scope_modules:
                    filtered = [r for r in filtered if any(m in str(r) for m in scope_modules)]
                if scope_smells:
                    filtered = [r for r in filtered if any(s in str(r).lower() for s in scope_smells)]
                risks_to_show = filtered[:5] if filtered else (risks[:3] if not (scope_modules or scope_smells) else filtered[:5])
                if risks_to_show:
                    lines.append(f"Risks: {'; '.join((str(r) for r in risks_to_show))}.")
    except Exception:
        pass
    try:
        events = get_recent_events(root, limit=3, types=('patch', 'learn'))
        if events:
            event_parts: List[str] = []
            for e in events[:3]:
                if e.type == 'patch':
                    out = getattr(e, 'output', None) or {}
                    if isinstance(out, dict):
                        modified = out.get('modified', [])
                        event_parts.append(f'patch: {len(modified)} files')
                elif e.type == 'learn':
                    event_parts.append('learn')
            if event_parts:
                lines.append('Recent: ' + '; '.join(event_parts))
    except Exception:
        pass
    return ' '.join(lines) if lines else 'No project context (run eurika scan .)'

def _run_eurika_fix(project_root: Path, dry_run: bool=False, timeout: int=180) -> str:
    """Run eurika fix . in project; return stdout+stderr. ROADMAP 3.5.11.C."""
    try:
        cmd = ['eurika', 'fix', '.', '--quiet']
        if dry_run:
            cmd.append('--dry-run')
        r = subprocess.run([sys.executable, '-m', 'eurika_cli', 'fix', str(project_root), '--quiet'] + (['--dry-run'] if dry_run else []), cwd=str(project_root), capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or '') + (r.stderr or '')
        suffix = f' (exit {r.returncode})' if r.returncode != 0 else ''
        return (out or '(no output)').strip() + suffix
    except subprocess.TimeoutExpired:
        return 'eurika fix: timeout'
    except Exception as e:
        return f'eurika fix: {e}'

def _is_apply_confirmation(message: str) -> bool:
    """Detect explicit confirmation to execute a pending action."""
    msg = (message or '').strip().lower()
    if not msg:
        return False
    markers = ('применяй', 'выполняй', 'это подтверждение', 'apply', 'go ahead', 'execute')
    return any((m in msg for m in markers))

def _extract_confirmation_token(message: str) -> str:
    """Extract optional confirmation token from message."""
    msg = str(message or '')
    m = re.search('(?:token|токен)\\s*[:=]?\\s*([a-fA-F0-9]{8,32})', msg)
    if not m:
        return ''
    return str(m.group(1))

def _is_reject_confirmation(message: str) -> bool:
    """Detect explicit rejection/cancel for pending plan."""
    msg = (message or '').strip().lower()
    if not msg:
        return False
    markers = ('отклонить', 'отмена', 'cancel', 'reject')
    return any((m in msg for m in markers))

def _apply_add_empty_tab_after_chat(root: Path) -> tuple[bool, str]:
    """Apply deterministic edit: add `New Tab` after Chat in Qt UI."""
    target = root / 'qt_app' / 'ui' / 'main_window.py'
    if not target.exists():
        return (False, 'target file not found: qt_app/ui/main_window.py')
    try:
        src = target.read_text(encoding='utf-8')
    except OSError as e:
        return (False, f'failed to read target file: {e}')
    if 'self.tabs.addTab(tab, "New Tab")' in src:
        return (True, 'tab already exists (no changes required)')
    anchor = 'self.tabs.addTab(tab, "Chat")'
    pos = src.find(anchor)
    if pos < 0:
        return (False, 'anchor not found: self.tabs.addTab(tab, "Chat")')
    line_end = src.find('\n', pos)
    if line_end < 0:
        line_end = len(src)
    insert = '\n        self.tabs.addTab(tab, "New Tab")'
    updated = src[:line_end] + insert + src[line_end:]
    try:
        target.write_text(updated, encoding='utf-8')
    except OSError as e:
        return (False, f'failed to write target file: {e}')
    return (True, 'added empty tab `New Tab` after `Chat`')

def _run_qt_smoke_test(project_root: Path, timeout: int=120) -> str:
    """Run minimal Qt smoke test after UI edit."""
    try:
        r = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/test_qt_smoke.py'], cwd=str(project_root), capture_output=True, text=True, timeout=timeout)
        out = ((r.stdout or '') + (r.stderr or '')).strip()
        if r.returncode == 0:
            return f"qt smoke: OK\n{out or '(no output)'}"
        return f"qt smoke: FAIL (exit {r.returncode})\n{out or '(no output)'}"
    except subprocess.TimeoutExpired:
        return 'qt smoke: timeout'
    except Exception as e:
        return f'qt smoke: {e}'

def _knowledge_topics_for_chat(intent: str, scope: Optional[Dict[str, Any]]) -> List[str]:
    """Topics for Knowledge from intent and scope (ROADMAP 3.6.6)."""
    from eurika.knowledge import SMELL_TO_KNOWLEDGE_TOPICS
    topics: List[str] = ["python"]
    if intent in ("refactor", "save", "code_edit_patch", "create"):
        if "architecture_refactor" not in topics:
            topics.append("architecture_refactor")
    if scope and scope.get("smells"):
        for s in scope["smells"]:
            smell = (s or "").strip().lower()
            for t in SMELL_TO_KNOWLEDGE_TOPICS.get(smell, []):
                if t not in topics:
                    topics.append(t)
    return topics


def _fetch_knowledge_for_chat(root: Path, topics: List[str], max_chars: int = 800) -> str:
    """Fetch knowledge snippets from Local + OSSPattern + cached PEP/docs (ROADMAP 3.6.6). rate_limit=0 = cache only."""
    import os
    from eurika.knowledge import CompositeKnowledgeProvider, LocalKnowledgeProvider, OfficialDocsProvider, OSSPatternProvider, PEPProvider, ReleaseNotesProvider, StructuredKnowledge

    cache_dir = root / ".eurika" / "knowledge_cache"
    ttl = float(os.environ.get("EURIKA_KNOWLEDGE_TTL", "86400"))
    oss_path = root / ".eurika" / "pattern_library.json"
    provider = CompositeKnowledgeProvider([
        LocalKnowledgeProvider(root / "eurika_knowledge.json"),
        OSSPatternProvider(oss_path),
        PEPProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=False, rate_limit_seconds=0),
        OfficialDocsProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=False, rate_limit_seconds=0),
        ReleaseNotesProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=False, rate_limit_seconds=0),
    ])
    all_fragments: List[Dict[str, Any]] = []
    for t in topics[:5]:
        if not t:
            continue
        kn = provider.query(t.strip())
        if isinstance(kn, StructuredKnowledge) and (not kn.is_empty()):
            for f in kn.fragments:
                if isinstance(f, dict):
                    all_fragments.append(f)
    if not all_fragments:
        return ""
    lines: List[str] = []
    for i, f in enumerate(all_fragments[:10], 1):
        title = f.get("title") or f.get("name") or f"Fragment {i}"
        content = f.get("content") or f.get("text") or str(f)
        lines.append(f"- {title}: {content[:400]}".rstrip() + ("..." if len(str(content)) > 400 else ""))
    snip = "\n".join(lines)
    return snip[:max_chars] + ("..." if len(snip) > max_chars else "")


def _load_chat_feedback_for_prompt(root: Path, max_chars: int = 1200) -> str:
    """Load few-shot examples from .eurika/chat_feedback.json for prompt injection (ROADMAP 3.6.8 Phase 4)."""
    path = root / '.eurika' / 'chat_feedback.json'
    if not path.exists():
        return ''
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        entries = list(data.get('entries') or [])
        if not entries:
            return ''
        neg = [e for e in entries if not e.get('helpful', True) and (e.get('clarification') or '').strip()]
        pos = [e for e in entries if e.get('helpful', True)]
        ordered = neg[-5:] + pos[-5:]
        ordered = ordered[-10:]
        lines: List[str] = []
        for e in ordered:
            user_msg = (e.get('user_message') or '')[:150].strip()
            asst_msg = (e.get('assistant_message') or '')[:120].strip()
            helpful = e.get('helpful', True)
            clarification = (e.get('clarification') or '').strip()[:200]
            if not user_msg:
                continue
            if helpful:
                snip = asst_msg[:80] + ('...' if len(asst_msg) > 80 else '')
                lines.append(f"- User: {user_msg} → correct: {snip}")
            elif clarification:
                lines.append(f"- User: {user_msg} → was wrong; user meant: {clarification}")
            if len('\n'.join(lines)) >= max_chars:
                break
        if not lines:
            return ''
        return '\n[Few-shot from past feedback]\n' + '\n'.join(lines[:8]) + '\n'
    except Exception:
        return ''


INTENT_INTERPRETATION_RULES = """[Intent interpretation (ROADMAP 3.6.8 Phase 2)]
- Commit / коммит / save to git / закоммитить → User should say «собери коммит»: shows git status+diff, then «применяй» to commit.
- Ritual / ритуал / полный цикл / scan doctor fix → eurika scan . → eurika doctor . → eurika report-snapshot . → eurika fix .
- Report / отчёт / doctor report → «покажи отчёт» shows eurika doctor report.
- Refactor / рефакторинг → «рефактори» + path, or eurika fix .
- List files / структура → «выполни ls» or «покажи структуру проекта».
- When user intent matches above, direct them to the exact phrase or explain the command chain."""


def _build_chat_prompt(message: str, context: str, history: Optional[List[Dict[str, str]]]=None, rag_examples: Optional[str]=None, save_target: Optional[str]=None, knowledge_snippet: Optional[str]=None, feedback_snippet: Optional[str]=None) -> str:
    """Build system + user prompt for chat. history: list of {role, content} from session.
    ROADMAP 3.5.11.B: rag_examples. ROADMAP 3.6.6: knowledge_snippet. ROADMAP 3.6.8 Phase 2: intent rules. Phase 4: feedback_snippet few-shot."""
    if save_target:
        system = 'You are Eurika. Never identify yourself as a base model/vendor name (Qwen, Llama, Ollama, OpenAI model, etc). If asked who you are, answer that you are Eurika. The user asked you to write code and save it to a file. Generate ONLY the code. No questions, no apologies, no clarification requests. Output must contain a ```python code block.'
    else:
        system = 'You are Eurika, an architecture-aware coding assistant. Never identify yourself as a base model/vendor name (Qwen, Llama, Ollama, OpenAI model, etc). If asked who you are, answer that you are Eurika. You have context about the current project. Answer concisely and helpfully. When asked to write code, prefer Python; when asked about architecture, use the context.'
    context_block = f'\n\n[Project context]: {context}\n\n' if context else '\n\n'
    context_block += f'\n{INTENT_INTERPRETATION_RULES}\n\n'
    if feedback_snippet:
        context_block += feedback_snippet
    if rag_examples:
        context_block += rag_examples
    if knowledge_snippet:
        context_block += f'\n[Reference (from documentation)]:\n{knowledge_snippet}\n\n'
    if save_target:
        context_block += f'\n[CRITICAL] User requested code to be saved to {save_target}. Reply ONLY with the code in a ```python block. Do NOT ask questions, do NOT apologize, do NOT request clarification. Generate the code immediately. Example format:\n```python\ndef foo(): ...\n```\n\n'
    user_content = message
    if history:
        hist_str = '\n'.join((f"{h.get('role', 'user')}: {h.get('content', '')}" for h in history[-4:]))
        user_content = f'[Previous messages]\n{hist_str}\n\nUser: {message}'
    return f'{system}{context_block}\nUser: {user_content}'

def _safe_write_file(root: Path, relative_path: str, content: str) -> tuple[bool, str]:
    """Write content to root/relative_path. Prevent path traversal. Return (ok, msg)."""
    if not relative_path or relative_path.startswith('/'):
        return (False, 'invalid path')
    path = (root / relative_path).resolve()
    try:
        allowed_base = root.resolve().parent
        if not path.is_relative_to(allowed_base):
            return (False, 'path outside project')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        try:
            return (True, str(path.relative_to(root)))
        except ValueError:
            return (True, str(path))
    except Exception as e:
        return (False, str(e))

def _safe_delete_file(root: Path, relative_path: str) -> tuple[bool, str]:
    """Delete file at root/relative_path. Prevent path traversal. Return (ok, msg)."""
    if not relative_path or relative_path.startswith('/'):
        return (False, 'invalid path')
    path = (root / relative_path).resolve()
    try:
        allowed_base = root.resolve().parent
        if not path.is_relative_to(allowed_base):
            return (False, 'path outside project')
        if not path.is_file():
            return (False, 'not a file or does not exist')
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)
        path.unlink()
        return (True, rel)
    except Exception as e:
        return (False, str(e))

def _safe_create_empty_file(root: Path, relative_path: str) -> tuple[bool, str]:
    """Create empty file at root/relative_path. Prevent path traversal. Return (ok, msg)."""
    if not relative_path or relative_path.startswith('/'):
        return (False, 'invalid path')
    path = (root / relative_path).resolve()
    try:
        allowed_base = root.resolve().parent
        if not path.is_relative_to(allowed_base):
            return (False, 'path outside project')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')
        try:
            return (True, str(path.relative_to(root)))
        except ValueError:
            return (True, str(path))
    except Exception as e:
        return (False, str(e))

def _load_dialog_state(root: Path) -> Dict[str, Any]:
    """Load lightweight dialog state for clarification/goal continuity."""
    path = root / '.eurika' / 'chat_history' / 'dialog_state.json'
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                return raw
    except Exception:
        pass
    return {}

def _save_dialog_state(root: Path, state: Dict[str, Any]) -> None:
    """Persist lightweight dialog state (best effort)."""
    path = root / '.eurika' / 'chat_history' / 'dialog_state.json'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass

def _format_execution_report(report: Dict[str, Any]) -> str:
    """Render structured execution report text for chat output."""
    ok = bool(report.get('ok'))
    summary = str(report.get('summary') or ('done' if ok else 'failed'))
    applied = list(report.get('applied_steps') or [])
    skipped = list(report.get('skipped_steps') or [])
    changed = list(report.get('artifacts_changed') or [])
    verification = report.get('verification') or {}
    error = report.get('error')
    lines = [('Готово' if ok else 'Не удалось') + f': {summary}.']
    if applied:
        lines.append('Applied steps: ' + ', '.join((str(x) for x in applied)))
    if skipped:
        lines.append('Skipped steps: ' + ', '.join((str(x) for x in skipped)))
    if changed:
        lines.append('Changed: ' + ', '.join((str(x) for x in changed)))
    if isinstance(verification, dict) and verification:
        lines.append('Verification: ' + ('OK' if verification.get('ok') else 'FAIL'))
        out = str(verification.get('output') or '').strip()
        if out:
            lines.append(out[:1200])
    if error:
        lines.append(f'Error: {error}')
    return '\n'.join(lines)

def _store_last_execution(state: Dict[str, Any], report: Dict[str, Any]) -> None:
    """Store compact last execution block in dialog state."""
    state['last_execution'] = {'ok': bool(report.get('ok')), 'summary': str(report.get('summary') or ''), 'verification_ok': bool((report.get('verification') or {}).get('ok')), 'artifacts_changed': list(report.get('artifacts_changed') or [])}

def _is_identity_question(message: str) -> bool:
    """Detect direct "who are you?" questions for deterministic persona answer."""
    msg = (message or '').strip().lower()
    if not msg:
        return False
    patterns = ('^ты\\s+кто\\??$', '^кто\\s+ты\\??$', '^who\\s+are\\s+you\\??$', '^what\\s+are\\s+you\\??$')
    return any((re.match(p, msg) for p in patterns))

def _is_ls_request(message: str) -> bool:
    """Detect explicit request to run ls/list in project root."""
    msg = (message or '').strip().lower()
    if not msg:
        return False
    return any((k in msg for k in (' ls ', 'команду ls', 'выполни ls', 'run ls', 'execute ls', 'list root', 'list files'))) or msg == 'ls'

def _is_show_report_request(message: str) -> bool:
    """Detect request to show scan/doctor report (ROADMAP: chat fast-path without LLM)."""
    msg = (message or "").strip().lower()
    if not msg:
        return False
    keywords = (
        "покажи отчет", "покажи отчёт", "сформируй отчет", "сформируй отчёт",
        "посмотри результат", "покажи результат", "report", "отчет", "отчёт",
        "doctor report", "scan report", "результат scan", "результат doctor",
    )
    return any(k in msg for k in keywords)


def _format_doctor_report_for_chat(root: Path) -> str:
    """Format eurika_doctor_report.json for chat display. No LLM, instant response."""
    doctor_path = root / "eurika_doctor_report.json"
    fix_path = root / "eurika_fix_report.json"
    if not doctor_path.exists() and not fix_path.exists():
        return "Отчёт не найден. Сначала выполни `eurika scan .` и `eurika doctor .`."
    try:
        from report.report_snapshot import format_report_snapshot
        return format_report_snapshot(root)
    except Exception:
        pass
    if doctor_path.exists():
        try:
            doc = json.loads(doctor_path.read_text(encoding="utf-8"))
            lines: List[str] = ["## Отчёт Doctor (eurika_doctor_report.json)\n"]
            summary = doc.get("summary", {}) or {}
            sys_info = summary.get("system", {}) or {}
            lines.append(f"- **Модули:** {sys_info.get('modules', '?')}")
            lines.append(f"- **Зависимости:** {sys_info.get('dependencies', '?')}")
            lines.append(f"- **Циклы:** {sys_info.get('cycles', 0)}")
            risks = summary.get("risks", [])[:8]
            if risks:
                lines.append("- **Риски:**")
                for r in risks:
                    lines.append(f"  - {r}")
            arch = (doc.get("architect") or "").strip()
            if arch:
                lines.append(f"\n**Architect:** {arch[:800]}" + ("..." if len(arch) > 800 else ""))
            ops = doc.get("operational_metrics") or {}
            if ops:
                lines.append(f"\n**Метрики:** apply_rate={ops.get('apply_rate')}, rollback_rate={ops.get('rollback_rate')}")
            return "\n".join(lines)
        except Exception:
            return "Не удалось прочитать eurika_doctor_report.json."
    if fix_path.exists():
        try:
            fix = json.loads(fix_path.read_text(encoding="utf-8"))
            lines = ["## Отчёт Fix (eurika_fix_report.json)\n"]
            mod = fix.get("modified", [])
            sk = fix.get("skipped", [])
            lines.append(f"- **Modified:** {len(mod)}")
            lines.append(f"- **Skipped:** {len(sk)}")
            v = fix.get("verify", {}) or {}
            lines.append(f"- **Verify:** {v.get('success', 'N/A')}")
            return "\n".join(lines)
        except Exception:
            return "Не удалось прочитать eurika_fix_report.json."
    return "Отчёт не найден."


def _is_git_commit_request(message: str) -> bool:
    """Detect request for git status/diff/commit (ROADMAP 3.6.8 Phase 1)."""
    msg = (message or '').strip().lower()
    if not msg:
        return False
    keywords = (
        'собери коммит', 'сделай коммит', 'создай коммит', 'закоммить', 'закоммит',
        'собери commit', 'сделай commit', 'commit changes', 'commit the changes',
        'git status', 'git diff', 'покажи status', 'покажи diff',
    )
    if any(k in msg for k in keywords):
        return True
    if re.match(r'^\s*commit\s*$', msg) or re.match(r'^\s*коммит\s*$', msg):
        return True
    return False


def _extract_commit_message_from_request(message: str) -> Optional[str]:
    """Extract explicit commit message from user message, if present."""
    msg_raw = (message or '').strip()
    patterns = [
        r'(?:в\s+сообщении\s+напиши|напиши\s+в\s+сообщении|сообщение\s+напиши)\s*[:=]\s*["\']?([^"\'\n]+)',
        r'(?:с\s+сообщением|with\s+message|message\s*[:=])\s*["\']?([^"\'\n]+)["\']?',
    ]
    for pat in patterns:
        m = re.search(pat, msg_raw, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _infer_commit_message_via_llm(user_message: str, status_out: str, diff_snippet: str) -> Optional[str]:
    """Infer commit message from user intent via LLM (ROADMAP 3.6.8). Fallback-safe."""
    if not user_message or not user_message.strip():
        return None
    prompt = f"""User wants to commit. Their message: "{user_message.strip()[:500]}"
Changed files (git status): {status_out[:600]}
Diff snippet: {diff_snippet[:800]}

Reply with ONLY the commit message (1-2 lines), no quotes, no explanation. Convey what the user asked for."""
    try:
        from eurika.reasoning.architect import call_llm_with_prompt
        raw, err = call_llm_with_prompt(prompt, max_tokens=80)
        if err or not raw:
            return None
        line = raw.strip().split('\n')[0].strip()
        line = line.strip('"\'`')
        if len(line) > 200:
            line = line[:200].rsplit(' ', 1)[0]
        return line if line else None
    except Exception:
        return None


def _propose_commit_message_from_status(status_out: str) -> str:
    """Derive a simple commit message from git status output."""
    lines = [l.strip() for l in (status_out or '').splitlines() if l.strip()]
    if not lines:
        return 'Update project'
    files = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 2:
            files.append(parts[-1])
    if not files:
        return 'Update project'
    if len(files) == 1:
        name = Path(files[0]).name
        return f'Update {name}'
    return f'Update {len(files)} files'


def _is_tree_request(message: str) -> bool:
    """Detect request for actual directory structure."""
    msg = (message or '').strip().lower()
    if not msg:
        return False
    if any((marker in msg for marker in ('цель:', 'границы:', 'задачи:', 'задача:'))):
        return False
    explicit = ('покажи структ', 'покажи дерево', 'какая структура', 'структуру проекта', 'фактическую структуру', 'tree', 'project structure', 'folder structure')
    if any((k in msg for k in explicit)):
        return True
    has_structure_word = re.search('\\bструктур\\w*\\b', msg) is not None
    has_question_marker = any((k in msg for k in ('?', 'какая', 'покажи', 'фактическ', 'полную')))
    return has_structure_word and has_question_marker

def _format_root_ls(root: Path, limit: int=120) -> str:
    """Render `ls`-like listing for project root."""
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as e:
        return f'Не удалось прочитать корень проекта: {e}'
    shown = entries[:max(limit, 1)]
    lines = [f'{p.name}/' if p.is_dir() else p.name for p in shown]
    if len(entries) > len(shown):
        lines.append(f'... (+{len(entries) - len(shown)} entries)')
    return '\n'.join(lines) if lines else '(empty)'

def _format_project_tree(root: Path, max_depth: int=3, limit: int=500) -> str:
    """Render compact project tree from root with sane limits."""
    lines: list[str] = [f'{root.name}/']
    seen = 1
    skip = {'.git', '__pycache__', '.mypy_cache', '.pytest_cache'}

    def walk(path: Path, depth: int, prefix: str) -> None:
        nonlocal seen
        if depth >= max_depth or seen >= limit:
            return
        try:
            children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return
        filtered = [c for c in children if c.name not in skip]
        for idx, child in enumerate(filtered):
            if seen >= limit:
                return
            branch = '└── ' if idx == len(filtered) - 1 else '├── '
            label = f'{child.name}/' if child.is_dir() else child.name
            lines.append(f'{prefix}{branch}{label}')
            seen += 1
            if child.is_dir():
                ext = '    ' if idx == len(filtered) - 1 else '│   '
                walk(child, depth + 1, prefix + ext)
    walk(root, 0, '')
    if seen >= limit:
        lines.append('... (tree truncated)')
    return '\n'.join(lines)

def _grounded_ui_tabs_text() -> str:
    """Return factual tabs for current Qt shell UI."""
    tabs = ['Commands', 'Dashboard', 'Approvals', 'Models', 'Chat']
    return 'В текущем Qt UI есть вкладки: ' + ', '.join((f'`{name}`' for name in tabs)) + '.'

def _is_saved_file_path_request(message: str) -> bool:
    """Detect explicit request for full path of recently saved file."""
    msg = (message or '').strip().lower()
    if not msg:
        return False
    full_path_markers = ('полный путь', 'full path', 'absolute path')
    file_markers = ('файл', 'file', '.py')
    show_markers = ('покажи', 'show', 'дай', 'where')
    return any((m in msg for m in full_path_markers)) and (
        any((m in msg for m in file_markers)) or any((m in msg for m in show_markers))
    )

def _infer_default_save_target(message: str) -> str:
    """Fallback file path for save-intent when user did not provide target."""
    msg = (message or '').strip().lower()
    if any((token in msg for token in ('hello world', 'хелло ворлд', 'приложение'))):
        return DEFAULT_SAVE_TARGET
    return DEFAULT_SAVE_TARGET

def _enforce_eurika_persona(text: str) -> str:
    """Normalize accidental model self-identification to Eurika persona."""
    raw = (text or '').strip()
    if not raw:
        return raw
    first_line = raw.splitlines()[0].strip()
    first_line_l = first_line.lower()
    leaked_markers = ('я qwen', 'i am qwen', "i'm qwen", 'as qwen', 'я llama', 'i am llama', "i'm llama", 'ollama')
    if any((m in first_line_l for m in leaked_markers)):
        prefix = 'Я Eurika, архитектурный ассистент этого проекта.'
        remainder = raw[len(first_line):].lstrip()
        return prefix if not remainder else f'{prefix}\n{remainder}'
    return raw

def append_chat_history(project_root: Path, role: str, content: str, context_snapshot: Optional[str]=None) -> None:
    """Append one message to .eurika/chat_history/chat.jsonl (ROADMAP 3.5.11.A.3)."""
    root = Path(project_root).resolve()
    chat_dir = root / '.eurika' / 'chat_history'
    chat_dir.mkdir(parents=True, exist_ok=True)
    log_path = chat_dir / 'chat.jsonl'
    record = {'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'role': role, 'content': content[:10000], 'context_snapshot': context_snapshot[:500] if context_snapshot else None}
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

def _append_chat_history_safe(project_root: Path, role: str, content: str, context_snapshot: Optional[str]=None) -> None:
    """Best-effort history append: never break chat flow on write errors."""
    try:
        append_chat_history(project_root, role, content, context_snapshot)
    except Exception:
        pass


def save_chat_feedback(
    project_root: Path,
    user_message: str,
    assistant_message: str,
    helpful: bool,
    clarification: Optional[str] = None,
) -> None:
    """Append feedback to .eurika/chat_feedback.json (ROADMAP 3.6.8 Phase 3)."""
    root = Path(project_root).resolve()
    path = root / '.eurika' / 'chat_feedback.json'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        entries: List[Dict[str, Any]] = []
        if path.exists():
            raw = path.read_text(encoding='utf-8')
            data = json.loads(raw) if raw.strip() else {}
            entries = list(data.get('entries') or [])
        entry = {
            'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'user_message': (user_message or '')[:2000],
            'assistant_message': (assistant_message or '')[:2000],
            'helpful': helpful,
            'clarification': (clarification or '').strip()[:500] or None,
        }
        entries.append(entry)
        path.write_text(json.dumps({'entries': entries}, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


def chat_send(project_root: Path, message: str, history: Optional[List[Dict[str, str]]]=None) -> Dict[str, Any]:
    """
    Send user message through Eurika layer to LLM; return response.

    ROADMAP 3.5.11.A: enriches prompt with project context.
    ROADMAP 3.5.11.B: RAG from past exchanges.
    ROADMAP 3.5.11.C: intent refactor -> run eurika fix; intent save -> extract code, write file.
    """
    root = Path(project_root).resolve()
    msg = (message or '').strip()
    if not msg:
        return {'text': '', 'error': 'message is empty'}
    state = _load_dialog_state(root)
    if _is_identity_question(msg):
        text = 'Я Eurika — архитектурный coding-ассистент этого проекта. Могу помочь с анализом, рефакторингом и изменениями кода.'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if _is_ls_request(msg):
        report_obj = execute_spec(root, build_task_spec(intent='project_ls', message=msg))
        report = {'ok': report_obj.ok, 'summary': report_obj.summary, 'applied_steps': report_obj.applied_steps, 'skipped_steps': report_obj.skipped_steps, 'verification': report_obj.verification, 'artifacts_changed': report_obj.artifacts_changed, 'error': report_obj.error}
        _store_last_execution(state, report)
        _save_dialog_state(root, state)
        listing = _format_root_ls(root)
        text = f'Да. Выполнил `ls` в корне проекта `{root}`:\n\n```\n{listing}\n```'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if _is_tree_request(msg):
        report_obj = execute_spec(root, build_task_spec(intent='project_tree', message=msg))
        report = {'ok': report_obj.ok, 'summary': report_obj.summary, 'applied_steps': report_obj.applied_steps, 'skipped_steps': report_obj.skipped_steps, 'verification': report_obj.verification, 'artifacts_changed': report_obj.artifacts_changed, 'error': report_obj.error}
        _store_last_execution(state, report)
        _save_dialog_state(root, state)
        tree = _format_project_tree(root, max_depth=3, limit=500)
        text = f'Показываю фактическую структуру проекта `{root}`:\n\n```\n{tree}\n```'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if _is_saved_file_path_request(msg):
        last_saved_abs = str(state.get('last_saved_file_abs') or '').strip()
        if last_saved_abs:
            text = f'Полный путь к последнему сохранённому файлу:\n{last_saved_abs}'
        else:
            text = 'Пока не вижу сохранённого файла в текущей сессии. Сначала попроси: «напиши ... и сохрани».'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if _is_show_report_request(msg):
        text = _format_doctor_report_for_chat(root)
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if _is_git_commit_request(msg):
        from eurika.api.chat_tools import git_status, git_diff, git_commit as _git_commit_tool
        ok_status, status_out = git_status(root)
        ok_diff, diff_out = git_diff(root)
        if not ok_status and not status_out:
            status_out = 'Не git-репозиторий или git недоступен.'
        blocks = [f'**git status**\n```\n{status_out or "(пусто)"}\n```']
        if diff_out:
            blocks.append(f'**git diff**\n```\n{diff_out[:4000]}{"..." if len(diff_out) > 4000 else ""}\n```')
        if ok_status and status_out.strip():
            explicit = _extract_commit_message_from_request(msg)
            if explicit:
                proposed = explicit
            else:
                minimal = (msg.strip().lower() in ('собери коммит', 'сделай коммит', 'commit', 'коммит') or
                           len(msg.strip()) < 20)
                if not minimal:
                    inferred = _infer_commit_message_via_llm(msg, status_out, diff_out[:1500] if diff_out else '')
                    proposed = inferred if inferred else _propose_commit_message_from_status(status_out)
                else:
                    proposed = _propose_commit_message_from_status(status_out)
            state['pending_git_commit'] = {'message': proposed}
            _save_dialog_state(root, state)
            blocks.append(f'\nПредлагаю коммит с сообщением: «{proposed}». Напиши **применяй** для подтверждения.')
        else:
            blocks.append('\nНет изменений для коммита.')
        text = '\n\n'.join(blocks)
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if _is_reject_confirmation(msg):
        pending_plan = state.get('pending_plan') if isinstance(state, dict) else {}
        if isinstance(pending_plan, dict) and is_pending_plan_valid(pending_plan):
            state['pending_plan'] = {}
            _save_dialog_state(root, state)
            text = 'Отклонил pending-план. Ничего не применял.'
        else:
            text = 'Нет активного pending-плана для отклонения.'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    intent, target = (None, None)
    interpretation = None
    effective_msg = msg
    pending = state.get('pending_clarification') if isinstance(state, dict) else None
    if isinstance(pending, dict):
        original = str(pending.get('original') or '').strip()
        if original and msg.lower() not in {'отмена', 'cancel', 'стоп'}:
            effective_msg = f'{original}\nУточнение: {msg}'
    try:
        from eurika.api.chat_intent import interpret_task
        interpretation = interpret_task(effective_msg, history=history)
        intent = interpretation.intent
        target = interpretation.target
    except Exception:
        pass
    if _is_apply_confirmation(msg):
        pending_git = state.get('pending_git_commit') if isinstance(state, dict) else None
        if isinstance(pending_git, dict) and pending_git.get('message'):
            from eurika.api.chat_tools import git_commit as _git_commit_tool
            msg_commit = str(pending_git.get('message') or '').strip()
            state['pending_git_commit'] = {}
            _save_dialog_state(root, state)
            ok, out = _git_commit_tool(root, msg_commit)
            text = f"Коммит выполнен: {out}" if ok else f"Ошибка: {out}"
            _append_chat_history_safe(root, 'user', msg, None)
            _append_chat_history_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None if ok else out}
        pending_plan = state.get('pending_plan') if isinstance(state, dict) else {}
        if isinstance(pending_plan, dict) and is_pending_plan_valid(pending_plan):
            user_token = _extract_confirmation_token(msg)
            plan_token = str(pending_plan.get('token') or '')
            if user_token and user_token != plan_token:
                text = 'Не могу выполнить: token подтверждения не совпадает.'
                _append_chat_history_safe(root, 'user', msg, None)
                _append_chat_history_safe(root, 'assistant', text, None)
                return {'text': text, 'error': None}
            spec = build_task_spec(intent=str(pending_plan.get('intent') or ''), target=str(pending_plan.get('target') or ''), message=msg, plan_steps=list(pending_plan.get('steps') or []), entities=dict(pending_plan.get('entities') or {}))
        else:
            if isinstance(state, dict) and isinstance(pending_plan, dict) and pending_plan:
                state['pending_plan'] = {}
                _save_dialog_state(root, state)
            text = (
                'Не могу выполнить: нет активного плана на подтверждение. '
                'Сначала сформулируй задачу, затем подтвердить: `применяй`.'
            )
            _append_chat_history_safe(root, 'user', msg, None)
            _append_chat_history_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None}
        if spec is not None:
            report_obj = execute_spec(root, spec)
            report = {'ok': report_obj.ok, 'summary': report_obj.summary, 'applied_steps': report_obj.applied_steps, 'skipped_steps': report_obj.skipped_steps, 'verification': report_obj.verification, 'artifacts_changed': report_obj.artifacts_changed, 'error': report_obj.error}
            state['pending_plan'] = {}
            state['active_goal'] = {'intent': spec.intent, 'target': spec.target, 'source': 'executor'}
            _store_last_execution(state, report)
            _save_dialog_state(root, state)
            text = _format_execution_report(report)
            _append_chat_history_safe(root, 'user', msg, None)
            _append_chat_history_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None}
    if intent == 'ui_tabs':
        report_obj = execute_spec(root, build_task_spec(intent='ui_tabs', message=msg))
        report = {'ok': report_obj.ok, 'summary': report_obj.summary, 'applied_steps': report_obj.applied_steps, 'skipped_steps': report_obj.skipped_steps, 'verification': report_obj.verification, 'artifacts_changed': report_obj.artifacts_changed, 'error': report_obj.error}
        _store_last_execution(state, report)
        _save_dialog_state(root, state)
        text = _grounded_ui_tabs_text()
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if interpretation is not None and interpretation.needs_clarification:
        text = interpretation.clarifying_question or 'Уточни, пожалуйста, задачу: что изменить, где именно и какой ожидаемый результат?'
        state['pending_clarification'] = {'original': msg}
        _save_dialog_state(root, state)
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if isinstance(state.get('pending_clarification'), dict):
        state.pop('pending_clarification', None)
        _save_dialog_state(root, state)
    if intent:
        state['active_goal'] = {'intent': intent, 'target': target or '', 'source': 'interpreter', 'confidence': float(getattr(interpretation, 'confidence', 0.0) if interpretation else 0.0), 'risk_level': str(getattr(interpretation, 'risk_level', 'medium') if interpretation else 'medium'), 'plan_steps': list(getattr(interpretation, 'plan_steps', []) if interpretation else []), 'entities': dict(getattr(interpretation, 'entities', {}) if interpretation else {})}
        _save_dialog_state(root, state)
    if intent and has_capability(intent) and (intent != 'save'):
        spec = build_task_spec(intent=intent, target=target or '', message=msg, plan_steps=list(getattr(interpretation, 'plan_steps', []) if interpretation else []), entities=dict(getattr(interpretation, 'entities', {}) if interpretation else {}))
        if spec.requires_confirmation:
            pending = make_pending_plan(spec)
            state['pending_plan'] = pending
            _save_dialog_state(root, state)
            steps_text = '; '.join(spec.steps[:4]) if spec.steps else 'n/a'
            task_text = f'Понял задачу: `{intent}`'
            if intent == 'ui_add_empty_tab':
                task_text = 'Понял задачу: добавить пустую вкладку после `Chat` в Qt UI'
            elif intent == 'ui_remove_tab':
                task_text = 'Понял задачу: удалить вкладку `New Tab` из Qt UI'
            text = task_text + (f' (target `{spec.target}`).' if spec.target else '.') + f' Risk: `{spec.risk_level}`. ' + f'Plan: {steps_text}. ' + f"Подтверди выполнение: `применяй token:{pending.get('token')}` (или просто `применяй`)."
            _append_chat_history_safe(root, 'user', msg, None)
            _append_chat_history_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None}
        report_obj = execute_spec(root, spec)
        report = {'ok': report_obj.ok, 'summary': report_obj.summary, 'applied_steps': report_obj.applied_steps, 'skipped_steps': report_obj.skipped_steps, 'verification': report_obj.verification, 'artifacts_changed': report_obj.artifacts_changed, 'error': report_obj.error}
        _store_last_execution(state, report)
        _save_dialog_state(root, state)
        text = _format_execution_report(report)
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if intent == 'refactor':
        dry = 'dry-run' in msg.lower() or 'dry run' in msg.lower() or 'без применения' in msg.lower()
        output = _run_eurika_fix(root, dry_run=dry)
        text = 'Запустил `eurika fix .`' + (' (dry-run)' if dry else '') + f':\n\n{output}'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if intent == 'delete' and target:
        ok, res = _safe_delete_file(root, target)
        if ok:
            full = (root / res).resolve()
            text = f'Удалён файл {res} ({full})'
        else:
            text = f'Не удалось удалить: {res}'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if intent == 'create' and target:
        ok, res = _safe_create_empty_file(root, target)
        if ok:
            full = (root / res).resolve()
            text = f'Создан пустой файл {res} ({full})'
        else:
            text = f'Не удалось создать: {res}'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if intent == 'recall' and target == 'name':
        uc = _load_user_context(root)
        name = uc.get('name')
        if name:
            text = f'Тебя зовут {name}.'
        else:
            text = 'Я не знаю, как тебя зовут. Скажи «Меня зовут X» или «My name is X», и я запомню.'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if intent == 'remember' and target and (':' in target):
        key, _, val = target.partition(':')
        key, val = (key.strip().lower(), val.strip())
        if key and val:
            uc = _load_user_context(root)
            uc[key] = val
            try:
                _save_user_context(root, uc)
            except Exception:
                pass
            if key == 'name':
                text = f'Запомнил: тебя зовут {val}.'
            else:
                text = f'Запомнил: {key}={val}'
        else:
            text = 'Не удалось распознать, что запомнить.'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    scope = None
    if interpretation is not None and interpretation.entities:
        modules = (interpretation.entities.get('scope_modules') or '').split(',')
        smells = (interpretation.entities.get('scope_smells') or '').split(',')
        if modules or smells:
            scope = {'modules': [m.strip() for m in modules if m.strip()], 'smells': [s.strip() for s in smells if s.strip()]}
    if scope is None:
        try:
            from eurika.api.chat_intent import parse_mentions
            mentions = parse_mentions(msg)
            if mentions.get('modules') or mentions.get('smells'):
                scope = mentions
        except Exception:
            pass
    context = _build_chat_context(root, scope=scope)
    rag_examples = None
    try:
        from eurika.api.chat_rag import retrieve_similar_chats, format_rag_examples
        examples = retrieve_similar_chats(root, msg, top_k=3)
        if examples:
            rag_examples = format_rag_examples(examples)
    except Exception:
        pass
    knowledge_snippet = ""
    try:
        topics = _knowledge_topics_for_chat(intent or "", scope)
        if topics:
            knowledge_snippet = _fetch_knowledge_for_chat(root, topics)
    except Exception:
        pass
    save_target = target if intent == 'save' else None
    if intent == 'save' and not save_target:
        save_target = _infer_default_save_target(msg)
        target = save_target
    feedback_snippet = _load_chat_feedback_for_prompt(root)
    prompt = _build_chat_prompt(msg, context, history, rag_examples=rag_examples, save_target=save_target, knowledge_snippet=knowledge_snippet or None, feedback_snippet=feedback_snippet or None)
    from eurika.reasoning.architect import call_llm_with_prompt
    raw_text, err = call_llm_with_prompt(prompt, max_tokens=1024)
    text = raw_text or ""
    if err:
        _append_chat_history_safe(root, 'user', msg, context)
        _append_chat_history_safe(root, 'assistant', f'[Error] {err}', None)
        return {'text': '', 'error': err}
    if intent == 'save' and save_target:
        try:
            from eurika.api.chat_intent import extract_code_block
            code = extract_code_block(text)
            if code:
                ok, res = _safe_write_file(root, save_target, code)
                if ok:
                    full = (root / res).resolve()
                    state['last_saved_file_rel'] = res
                    state['last_saved_file_abs'] = str(full)
                    _save_dialog_state(root, state)
                    text = text.rstrip() + f'\n\n[Сохранено в {res} ({full})]'
        except Exception:
            pass
    text = _enforce_eurika_persona(text or '')
    _append_chat_history_safe(root, 'user', msg, context)
    _append_chat_history_safe(root, 'assistant', text or '', None)
    return {'text': text or '', 'error': None}