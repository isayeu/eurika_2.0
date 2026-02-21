"""Intent detection for Chat (ROADMAP 3.5.11.C). save_code, refactor, delete, create, remember, recall."""
from __future__ import annotations
import re
from typing import Optional, Tuple

def detect_intent(message: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect intent and extract target from user message.

    Returns (intent, target). intent: "save" | "refactor" | "delete" | "create" | "remember" | "recall" | None.
    target: file path for save/delete/create; "name:Value" for remember; "name" for recall.
    """
    msg_raw = (message or '').strip()
    msg = msg_raw.lower()
    if not msg:
        return (None, None)
    # remember: "меня зовут X", "запомни что меня зовут X", "my name is X"
    remember_name = re.search(
        r'(?:меня\s+зовут|my\s+name\s+is|запомни[,:\s]*(?:что\s+)?меня\s+зовут)\s+([^,\.]+)',
        msg_raw, re.IGNORECASE
    )
    if remember_name:
        name = remember_name.group(1).strip()
        if name and len(name) < 100 and not name.startswith(('http', '/')):
            return ('remember', f'name:{name}')
    # recall: "как меня зовут", "what's my name", "what is my name"
    if re.search(r"как\s+меня\s+зовут|what'?s?\s+my\s+name|how\s+do\s+you\s+call\s+me\b", msg, re.IGNORECASE):
        return ('recall', 'name')
    # create: "создай пустой файл X", "create empty file X"
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
    if any((w in msg for w in ('создай файл', 'создай пустой', 'create file', 'create empty'))):
        m = re.search(r'([a-zA-Z0-9_/.\\-]+\.[a-zA-Z0-9]+)\s*$', msg)
        if m:
            return ('create', m.group(1).strip())
    # delete: "удали X", "delete X", "remove X"
    delete_patterns = [
        r'(?:удали|удалить|delete|remove)\s+([a-zA-Z0-9_/.\\-]+\.[a-zA-Z0-9]+)',
        r'(?:удали|удалить|delete|remove)\s+([a-zA-Z0-9_/.\\-]+)',
    ]
    for pat in delete_patterns:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            target = m.group(1).strip()
            if re.match(r'^[a-zA-Z0-9_./\-]+$', target):
                return ('delete', target)
    if any((w in msg for w in ('удали', 'удалить', 'delete', 'remove'))):
        m = re.search(r'(?:удали|удалить|delete|remove)\s+([a-zA-Z0-9_/.\\-]+(?:\.\w+)?)\s*$', msg, re.IGNORECASE)
        if m:
            return ('delete', m.group(1).strip())
    # save with directory: "сохрани в tests/ foo.py", "save to tests/ bar.py", "сохрани в tests/ файл test_utils.py"
    save_dir_file = re.search(
        r'(?:сохрани|запиши|save|write)\s+(?:код\s+)?(?:в|to)\s+([a-zA-Z0-9_/.\\-]+/)\s+(?:\w+\s+)*([a-zA-Z0-9_/.\\-]+\.[a-zA-Z0-9]+)',
        msg_raw, re.IGNORECASE
    )
    if save_dir_file:
        dir_part, file_part = save_dir_file.group(1).strip(), save_dir_file.group(2).strip()
        if re.match(r'^[a-zA-Z0-9_./\-]+$', dir_part + file_part):
            target = (dir_part.rstrip('/') + '/' + file_part).replace('//', '/')
            return ('save', target)
    # save with "в каталог X файл Y"
    save_dir_as = re.search(
        r'(?:сохрани|запиши|save)\s+(?:в\s+)?каталог\s+([a-zA-Z0-9_/.\\-]+)\s+(?:файл\s+)?([a-zA-Z0-9_/.\\-]+\.[a-zA-Z0-9]+)',
        msg_raw, re.IGNORECASE
    )
    if save_dir_as:
        dir_part, file_part = save_dir_as.group(1).strip(), save_dir_as.group(2).strip()
        if re.match(r'^[a-zA-Z0-9_./\-]+$', dir_part + file_part):
            return ('save', f'{dir_part.rstrip("/")}/{file_part}')
    save_patterns = ['(?:сохрани|запиши|save|write)\\s+(?:код\\s+)?(?:в|to)\\s+([^\\s,\\.]+\\.\\w+)', '(?:сохрани|запиши)\\s+в\\s+([a-zA-Z0-9_/.\\-]+)', '(?:в|to)\\s+([a-zA-Z0-9_/.\\-]+\\.py)\\b']
    for pat in save_patterns:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            target = m.group(1).strip()
            if '.py' in target or '/' in target or re.match('^[a-zA-Z0-9_./\\-]+$', target):
                return ('save', target)
    if any((w in msg for w in ('сохрани', 'запиши в', 'save to', 'write to'))):
        m = re.search('(?:в|to)\\s+([a-zA-Z0-9_/.\\-]+(?:\\.[a-zA-Z0-9]+)?)\\s*$', msg)
        if m:
            return ('save', m.group(1).strip())
    refactor_patterns = ['(?:рефактори|рефактор|refactor|исправь|пофикси)\\s+([a-zA-Z0-9_/.\\-]+)', 'refactor\\s+([a-zA-Z0-9_/.\\-]+\\.py)']
    for pat in refactor_patterns:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            target = m.group(1).strip()
            return ('refactor', target)
    if any((w in msg for w in ('рефактори', 'рефактор', 'refactor', 'исправь архитектуру'))):
        return ('refactor', '.')
    return (None, None)

def extract_code_block(text: str) -> Optional[str]:
    """Extract first ```python ... ``` or ``` ... ``` block from LLM response."""
    if not text:
        return None
    m = re.search('```(?:python)?\\s*\\n(.*?)```', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


# TODO (eurika): refactor long_function 'detect_intent' — consider extracting helper
