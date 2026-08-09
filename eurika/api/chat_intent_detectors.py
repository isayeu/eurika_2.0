"""Intent detectors for chat (extracted from chat_intent)."""

from __future__ import annotations

import re
from typing import Optional, Tuple


def detect_remember_recall(msg_raw: str, msg: str) -> Optional[Tuple[str, str]]:
    """Detect remember/recall intents (name memory)."""
    remember_name = re.search(
        r'(?:меня\s+зовут|my\s+name\s+is|запомни[,:\s]*(?:что\s+)?меня\s+зовут)\s+([^,\.]+)',
        msg_raw, re.IGNORECASE
    )
    if remember_name:
        name = remember_name.group(1).strip()
        if name and len(name) < 100 and not name.startswith(('http', '/')):
            return ('remember', f'name:{name}')
    if re.search(r"как\s+меня\s+зовут|what'?s?\s+my\s+name|how\s+do\s+you\s+call\s+me\b", msg, re.IGNORECASE):
        return ('recall', 'name')
    return None


def detect_create(msg: str) -> Optional[Tuple[str, str]]:
    """Detect create (empty file) intent."""
    create_patterns = [
        r'(?:создай|create)\s+(?:пустой\s+)?(?:файл\s+)?([a-zA-Z0-9_/.\\-]+\.[a-zA-Z0-9]+)',
        r'(?:создай|create)\s+(?:файл\s+)?([a-zA-Z0-9_/.\\-]+\.[a-zA-Z0-9]+)',
        r'(?:empty\s+)?file\s+([a-zA-Z0-9_/.\\-]+\.[a-zA-Z0-9]+)',
    ]
    for pat in create_patterns:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            target = m.group(1).strip()
            if re.match(r'^[a-zA-Z0-9_./\-]+$', target):
                return ('create', target)
    if any((w in msg for w in ('создай файл', 'создай пустой', 'создай новый', 'create file', 'create empty'))):
        m = re.search(r'([a-zA-Z0-9_/.\\-]+\.[a-zA-Z0-9]+)\s*$', msg)
        if m:
            return ('create', m.group(1).strip())
    return None


def detect_delete(msg: str) -> Optional[Tuple[str, str]]:
    """Detect delete/remove file intent."""
    delete_patterns = [
        r'(?:удали|удалить|delete|remove)\s+(?:файл\s+)?([a-zA-Z0-9_/.\\-]+\.[a-zA-Z0-9]+)',
        r'(?:удали|удалить|delete|remove)\s+(?:файл\s+)?([a-zA-Z0-9_/.\\-]+)',
    ]
    for pat in delete_patterns:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            target = m.group(1).strip()
            if re.match(r'^[a-zA-Z0-9_./\-]+$', target):
                return ('delete', target)
    if any((w in msg for w in ('удали', 'удалить', 'delete', 'remove'))):
        m = re.search(r'(?:удали|удалить|delete|remove)\s+(?:файл\s+)?([a-zA-Z0-9_/.\\-]+(?:\.\w+)?)\s*$', msg, re.IGNORECASE)
        if m:
            return ('delete', m.group(1).strip())
    return None


def detect_save(msg_raw: str, msg: str) -> Optional[Tuple[str, str]]:
    """Detect save/write file intent."""
    save_dir_file = re.search(
        r'(?:сохрани|запиши|save|write)\s+(?:код\s+)?(?:в|to)\s+([a-zA-Z0-9_/.\\-]+/)\s+(?:\w+\s+)*([a-zA-Z0-9_/.\\-]+\.[a-zA-Z0-9]+)',
        msg_raw, re.IGNORECASE
    )
    if save_dir_file:
        dir_part, file_part = save_dir_file.group(1).strip(), save_dir_file.group(2).strip()
        if re.match(r'^[a-zA-Z0-9_./\-]+$', dir_part + file_part):
            target = (dir_part.rstrip('/') + '/' + file_part).replace('//', '/')
            return ('save', target)
    save_dir_as = re.search(
        r'(?:сохрани|запиши|save)\s+(?:в\s+)?каталог\s+([a-zA-Z0-9_/.\\-]+)\s+(?:файл\s+)?([a-zA-Z0-9_/.\\-]+\.[a-zA-Z0-9]+)',
        msg_raw, re.IGNORECASE
    )
    if save_dir_as:
        dir_part, file_part = save_dir_as.group(1).strip(), save_dir_as.group(2).strip()
        if re.match(r'^[a-zA-Z0-9_./\-]+$', dir_part + file_part):
            return ('save', f'{dir_part.rstrip("/")}/{file_part}')
    save_patterns = [
        r'(?:сохрани|запиши|напиши|save|write)\s+(?:код\s+)?(?:в|to)\s+([^\s,\.]+\.\w+)',
        r'(?:сохрани|запиши|напиши)\s+в\s+([a-zA-Z0-9_/.\-]+)',
        r'(?:в|to)\s+([a-zA-Z0-9_/.\-]+\.py)\b',
    ]
    for pat in save_patterns:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            target = m.group(1).strip()
            if '.py' in target or '/' in target or re.match(r'^[a-zA-Z0-9_./\-]+$', target):
                return ('save', target)
    if any((w in msg for w in ('сохрани', 'запиши в', 'напиши в', 'save to', 'write to'))):
        m = re.search(r'(?:в|to)\s+([a-zA-Z0-9_/.\-]+(?:\.[a-zA-Z0-9]+)?)\s*$', msg)
        if m:
            return ('save', m.group(1).strip())
    return None


def detect_refactor(msg_raw: str, msg: str) -> Optional[Tuple[str, str]]:
    """Detect refactor intent."""
    refactor_patterns = [
        r'(?:рефактори|рефактор|исправь|пофикси|улучши|refactor)\s+([a-zA-Z0-9_/.\-]+)',
        r'refactor\s+([a-zA-Z0-9_/.\-]+\.py)',
    ]
    for pat in refactor_patterns:
        m = re.search(pat, msg_raw, re.IGNORECASE)
        if m:
            return ('refactor', m.group(1).strip())
    if any((w in msg for w in ('рефактори', 'рефактор', 'исправь архитектуру', 'пофикси архитектуру', 'refactor'))):
        return ('refactor', '.')
    return None


def detect_run(msg_raw: str, msg: str) -> Optional[Tuple[str, str]]:
    """Detect run_tests, run_lint, run_command intents."""
    test_run = re.search(
        r"(?:запусти|прогони|проверь|run)\s+(?:тест(?:ы)?|tests?)\s*([a-zA-Z0-9_./\\:-]+)?",
        msg_raw, re.IGNORECASE,
    )
    if test_run:
        return ("run_tests", (test_run.group(1) or "").strip())
    if re.search(r"\bpytest\b", msg, re.IGNORECASE):
        m = re.search(r"pytest\s+([a-zA-Z0-9_./\\:-]+)", msg_raw, re.IGNORECASE)
        return ("run_tests", (m.group(1).strip() if m else ""))
    if re.search(r"(?:запусти|run)\s+(?:линтер|lint)\b", msg, re.IGNORECASE):
        return ("run_lint", "")
    cmd_run = re.search(r"(?:запусти|выполни|run|execute)\s+(?:команд[ау]\s+)?(.+)$", msg_raw, re.IGNORECASE)
    if cmd_run:
        cmd = cmd_run.group(1).strip()
        if cmd:
            return ("run_command", cmd)
    return None
