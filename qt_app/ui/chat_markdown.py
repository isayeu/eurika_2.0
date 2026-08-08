"""Lightweight markdown → HTML for the Qt chat transcript.

Not full CommonMark: fenced code frames, inline code, bold, simple lists,
paragraphs. Fenced blocks register payloads for Copy / Run link actions.
"""

from __future__ import annotations

import html
import re
import uuid
from typing import MutableMapping

CHAT_LINK_SCHEME = "eurika-chat"
SHELL_LANGS = frozenset({"bash", "sh", "shell", "console", "zsh", "terminal", "fish"})
# Protocol / non-runnable fences from the tool-loop.
NO_RUN_LANGS = frozenset({"eurika-cmds", "eurika-cmd", "diff", "patch"})
_SHELL_STARTERS = frozenset(
    {
        "ls",
        "pwd",
        "cd",
        "cat",
        "head",
        "tail",
        "git",
        "eurika",
        "python",
        "python3",
        "pip",
        "pip3",
        "pytest",
        "npm",
        "node",
        "cargo",
        "make",
        "curl",
        "wget",
        "echo",
        "rg",
        "grep",
        "find",
        "which",
        "uname",
        "df",
        "du",
        "ps",
        "top",
        "htop",
        "systemctl",
        "journalctl",
        "docker",
        "ssh",
        "./scripts",
        "bash",
        "sh",
    }
)

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_LIST_ITEM_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


def new_block_id() -> str:
    return uuid.uuid4().hex[:12]


def parse_chat_action_url(url: str) -> tuple[str, str] | None:
    """Return ``(action, block_id)`` for ``eurika-chat://copy/<id>`` etc."""
    raw = (url or "").strip()
    if not raw:
        return None
    # QUrl may give eurika-chat://copy/abc or eurika-chat:copy/abc
    prefix = f"{CHAT_LINK_SCHEME}://"
    if raw.startswith(prefix):
        rest = raw[len(prefix) :]
    elif raw.startswith(f"{CHAT_LINK_SCHEME}:"):
        rest = raw[len(CHAT_LINK_SCHEME) + 1 :].lstrip("/")
    else:
        return None
    parts = [p for p in rest.split("/") if p]
    if len(parts) < 2:
        return None
    action, block_id = parts[0].lower(), parts[1]
    if action not in ("copy", "run") or not block_id:
        return None
    return action, block_id


def looks_like_shell(code: str, lang: str) -> bool:
    """Whether a fenced block should offer Run."""
    lang_l = (lang or "").strip().lower()
    if lang_l in NO_RUN_LANGS:
        return False
    if lang_l in SHELL_LANGS:
        return True
    if lang_l:
        return False
    lines = [ln.strip() for ln in (code or "").splitlines() if ln.strip()]
    if not lines:
        return False
    first = lines[0]
    if first.startswith("$"):
        return True
    token = first.split(None, 1)[0]
    if token.startswith("./"):
        return True
    return token in _SHELL_STARTERS


def shell_command_from_block(code: str) -> str:
    """Strip leading ``$ `` prompts from a shell fence for execution."""
    out: list[str] = []
    for line in (code or "").splitlines():
        s = line.strip()
        if s.startswith("$"):
            s = s[1:].lstrip()
        out.append(s if line.strip().startswith("$") else line.rstrip())
    # Prefer non-empty lines; join multi-line scripts with newlines.
    body = "\n".join(out).strip()
    return body


def _chip(href: str, label: str) -> str:
    return (
        f'<a href="{html.escape(href, quote=True)}" '
        f'style="color:#93c5fd; text-decoration:none; '
        f'background-color:#334155; padding:1px 8px; '
        f'font-family:sans-serif; font-size:11px;">{html.escape(label)}</a>'
    )


def _render_fence(
    code: str,
    lang: str,
    payloads: MutableMapping[str, str],
) -> str:
    block_id = new_block_id()
    payloads[block_id] = code
    lang_l = (lang or "").strip().lower()
    label = html.escape(lang_l or "code")
    actions = [_chip(f"{CHAT_LINK_SCHEME}://copy/{block_id}", "Copy")]
    if looks_like_shell(code, lang_l):
        actions.append(_chip(f"{CHAT_LINK_SCHEME}://run/{block_id}", "Run"))
    actions_html = "&nbsp;&nbsp;".join(actions)
    body = html.escape(code)
    # Qt rich text: <pre> keeps newlines better than CSS white-space.
    return (
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="background-color:#0f172a; margin:6px 0; '
        'border:1px solid #334155;">'
        "<tr><td "
        'style="background-color:#1e293b; color:#94a3b8; '
        'font-family:sans-serif; font-size:11px; padding:4px 8px;">'
        f"{label}&nbsp;&nbsp;{actions_html}"
        "</td></tr>"
        "<tr><td style=\"padding:8px;\">"
        '<pre style="margin:0; font-family:monospace; font-size:12px; '
        f'color:#e2e8f0;">{body}</pre>'
        "</td></tr></table>"
    )


def _render_inline(text: str) -> str:
    """Escape text, then restore bold and inline code spans."""
    if not text:
        return ""
    placeholders: dict[str, str] = {}

    def _hold(html_frag: str) -> str:
        key = f"@@EURIKAHTML{len(placeholders)}@@"
        placeholders[key] = html_frag
        return key

    def _code_sub(m: re.Match[str]) -> str:
        inner = html.escape(m.group(1))
        return _hold(
            f'<code style="background-color:#1e293b; color:#fde68a; '
            f'font-family:monospace; padding:1px 4px;">{inner}</code>'
        )

    # Protect inline code before bold / escape.
    protected = _INLINE_CODE_RE.sub(_code_sub, text)
    pieces: list[str] = []
    pos = 0
    for m in _BOLD_RE.finditer(protected):
        pieces.append(html.escape(protected[pos : m.start()]).replace("\n", "<br>"))
        # Bold body may still contain @@EURIKAHTML…@@ placeholders — keep as-is.
        bold_inner = m.group(1)
        if "@@EURIKAHTML" in bold_inner:
            pieces.append(f"<b>{bold_inner}</b>")
        else:
            pieces.append(f"<b>{html.escape(bold_inner)}</b>")
        pos = m.end()
    pieces.append(html.escape(protected[pos:]).replace("\n", "<br>"))
    out = "".join(pieces)
    # Placeholders survive html.escape (letters/@ only).
    for key, frag in placeholders.items():
        out = out.replace(key, frag)
    return out


def _render_text_block(text: str) -> str:
    """Paragraphs + simple list items."""
    if not text.strip():
        return ""
    lines = text.split("\n")
    parts: list[str] = []
    list_buf: list[str] = []
    list_ordered: bool | None = None

    def flush_list() -> None:
        nonlocal list_buf, list_ordered
        if not list_buf:
            return
        tag = "ol" if list_ordered else "ul"
        items = "".join(f"<li>{_render_inline(item)}</li>" for item in list_buf)
        parts.append(f"<{tag}>{items}</{tag}>")
        list_buf = []
        list_ordered = None

    para: list[str] = []

    def flush_para() -> None:
        nonlocal para
        if not para:
            return
        body = _render_inline("\n".join(para))
        parts.append(f"<p style=\"margin:4px 0;\">{body}</p>")
        para = []

    for line in lines:
        m = _LIST_ITEM_RE.match(line)
        if m:
            flush_para()
            marker = m.group(2)
            ordered = marker[:1].isdigit()
            if list_buf and list_ordered is not None and list_ordered != ordered:
                flush_list()
            list_ordered = ordered
            list_buf.append(m.group(3))
            continue
        if not line.strip():
            flush_list()
            flush_para()
            continue
        flush_list()
        para.append(line)
    flush_list()
    flush_para()
    return "".join(parts)


def split_fenced_segments(text: str) -> list[tuple[str, str, str]]:
    """Split into ``('text', '', body)`` / ``('fence', lang, code)`` segments."""
    lines = (text or "").split("\n")
    segments: list[tuple[str, str, str]] = []
    buf: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            segments.append(("text", "", "\n".join(buf)))
            buf = []
            lang = line[3:].strip()
            i += 1
            code_lines: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines) and lines[i].startswith("```"):
                i += 1
            segments.append(("fence", lang, "\n".join(code_lines)))
            continue
        buf.append(line)
        i += 1
    if buf:
        segments.append(("text", "", "\n".join(buf)))
    return segments


def render_chat_markdown(
    text: str,
    *,
    payloads: MutableMapping[str, str] | None = None,
) -> str:
    """Convert light markdown to Qt-rich HTML. Mutates ``payloads`` for fences."""
    store: MutableMapping[str, str] = payloads if payloads is not None else {}
    chunks: list[str] = []
    for kind, lang, body in split_fenced_segments(text or ""):
        if kind == "fence":
            chunks.append(_render_fence(body, lang, store))
        else:
            chunks.append(_render_text_block(body))
    return "".join(chunks) or _render_inline(text or "")


def format_chat_line_html(
    role: str,
    text: str,
    *,
    is_error: bool = False,
    payloads: MutableMapping[str, str] | None = None,
) -> str:
    """Role label + rendered body for ``QTextBrowser.append``."""
    body = render_chat_markdown(text, payloads=payloads)
    if role == "user":
        label = '<b><span style="color:#1e40af">You</span></b>'
    elif is_error:
        label = '<b><span style="color:#b91c1c">Eurika</span></b>'
    else:
        label = '<b><span style="color:#15803d">Eurika</span></b>'
    return f'{label}:<div style="margin:2px 0 10px 0;">{body}</div>'
