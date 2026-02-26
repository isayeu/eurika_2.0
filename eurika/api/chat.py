"""Chat endpoint for UI (ROADMAP 3.5.11.A, 3.5.11.B, 3.5.11.C). Eurika layer → Ollama; logs to .eurika/chat_history/; RAG; intent→action (save, refactor)."""
from __future__ import annotations
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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

def _extracted_block_64():
    out = getattr(e, 'output', None) or {}
    if not isinstance(out, dict):
        out = {}
    modified = out.get('modified', [])
    parts.append(f'patch: {len(modified)} files')

def _extracted_block_64():
    parts = []
    for e in events[:3]:
        if e.type == 'patch':
            _extracted_block_64()
        elif e.type == 'learn':
            parts.append('learn')
    if parts:
        lines.append('Recent: ' + '; '.join(parts))

def _build_chat_context(root: Path) -> str:
    """Build context snippet from summary + recent_events + user context for chat prompt."""
    from eurika.api import get_recent_events, get_summary
    lines: List[str] = []
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
                lines.append(f"Risks: {'; '.join((str(r) for r in risks[:3]))}.")
    except Exception:
        pass
    try:
        events = get_recent_events(root, limit=3, types=('patch', 'learn'))
        if events:
            _extracted_block_64()
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

def _build_chat_prompt(message: str, context: str, history: Optional[List[Dict[str, str]]]=None, rag_examples: Optional[str]=None, save_target: Optional[str]=None) -> str:
    """Build system + user prompt for chat. history: list of {role, content} from session.
    ROADMAP 3.5.11.B: rag_examples from retrieve_similar_chats."""
    if save_target:
        system = 'You are Eurika. The user asked you to write code and save it to a file. Generate ONLY the code. No questions, no apologies, no clarification requests. Output must contain a ```python code block.'
    else:
        system = 'You are Eurika, an architecture-aware coding assistant. You have context about the current project. Answer concisely and helpfully. When asked to write code, prefer Python; when asked about architecture, use the context.'
    context_block = f'\n\n[Project context]: {context}\n\n' if context else '\n\n'
    if rag_examples:
        context_block += rag_examples
    if save_target:
        context_block += f'\n[CRITICAL] User requested code to be saved to {save_target}. Reply ONLY with the code in a ```python block. Do NOT ask questions, do NOT apologize, do NOT request clarification. Generate the code immediately. Example format:\n```python\ndef foo(): ...\n```\n\n'
    user_content = message
    if history:
        hist_str = '\n'.join((f"{h.get('role', 'user')}: {h.get('content', '')}" for h in history[-4:]))
        user_content = f'[Previous messages]\n{hist_str}\n\nUser: {message}'
    return f'{system}{context_block}\nUser: {user_content}'

def _safe_write_file(root: Path, relative_path: str, content: str) -> tuple[bool, str]:
    """Write content to root/relative_path. Prevent path traversal. Return (ok, msg)."""
    if '..' in relative_path or relative_path.startswith('/'):
        return (False, 'invalid path')
    path = (root / relative_path).resolve()
    try:
        if not str(path).startswith(str(root.resolve())):
            return (False, 'path outside project')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return (True, str(path.relative_to(root)))
    except Exception as e:
        return (False, str(e))

def _safe_delete_file(root: Path, relative_path: str) -> tuple[bool, str]:
    """Delete file at root/relative_path. Prevent path traversal. Return (ok, msg)."""
    if '..' in relative_path or relative_path.startswith('/'):
        return (False, 'invalid path')
    path = (root / relative_path).resolve()
    try:
        if not str(path).startswith(str(root.resolve())):
            return (False, 'path outside project')
        if not path.is_file():
            return (False, 'not a file or does not exist')
        rel = str(path.relative_to(root))
        path.unlink()
        return (True, rel)
    except Exception as e:
        return (False, str(e))

def _safe_create_empty_file(root: Path, relative_path: str) -> tuple[bool, str]:
    """Create empty file at root/relative_path. Prevent path traversal. Return (ok, msg)."""
    if '..' in relative_path or relative_path.startswith('/'):
        return (False, 'invalid path')
    path = (root / relative_path).resolve()
    try:
        if not str(path).startswith(str(root.resolve())):
            return (False, 'path outside project')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')
        return (True, str(path.relative_to(root)))
    except Exception as e:
        return (False, str(e))

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
    intent, target = (None, None)
    try:
        from eurika.api.chat_intent import detect_intent
        intent, target = detect_intent(msg)
    except Exception:
        pass
    if intent == 'refactor':
        dry = 'dry-run' in msg.lower() or 'dry run' in msg.lower() or 'без применения' in msg.lower()
        output = _run_eurika_fix(root, dry_run=dry)
        text = f'Запустил `eurika fix .`' + (' (dry-run)' if dry else '') + f':\n\n{output}'
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
    context = _build_chat_context(root)
    rag_examples = None
    try:
        from eurika.api.chat_rag import retrieve_similar_chats, format_rag_examples
        examples = retrieve_similar_chats(root, msg, top_k=3)
        if examples:
            rag_examples = format_rag_examples(examples)
    except Exception:
        pass
    save_target = target if intent == 'save' else None
    prompt = _build_chat_prompt(msg, context, history, rag_examples=rag_examples, save_target=save_target)
    from eurika.reasoning.architect import call_llm_with_prompt
    text, err = call_llm_with_prompt(prompt, max_tokens=1024)
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
                    text = text.rstrip() + f'\n\n[Сохранено в {res} ({full})]'
        except Exception:
            pass
    _append_chat_history_safe(root, 'user', msg, context)
    _append_chat_history_safe(root, 'assistant', text or '', None)
    return {'text': text or '', 'error': None}