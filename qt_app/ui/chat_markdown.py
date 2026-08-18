"""Lightweight markdown → HTML for the Qt chat transcript.

Not full CommonMark: fenced code frames, inline code, bold, simple lists,
paragraphs. Fenced blocks register payloads for Copy / Run link actions.
"""

from __future__ import annotations

import html
import re
import uuid
from pathlib import Path
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
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_QUOTE_RE = re.compile(r"^>\s?(.*)$")
_HR_RE = re.compile(r"^(-{3,}|\*{3,})\s*$")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+|file:[^)\s]+)\)")
_IMAGE_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
_MAX_CHAT_IMAGE_WIDTH = 520


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
        f'color:#e2e8f0; white-space:pre-wrap;">{body}</pre>'
        "</td></tr></table>"
    )


def resolve_chat_image_src(src: str, image_root: Path | None = None) -> str | None:
    """Return a Qt-safe ``file://`` or data URI, or None if the target is not an image file."""
    raw = (src or "").strip().strip('"').strip("'")
    if not raw:
        return None
    if raw.startswith("data:image/"):
        return raw
    if raw.startswith(("http://", "https://")):
        return None
    local = raw[7:] if raw.startswith("file://") else raw
    path = Path(local)
    if not path.is_absolute() and image_root is not None:
        path = image_root / local
    try:
        path = path.expanduser()
        if path.suffix.lower() not in _IMAGE_EXTS:
            return None
        resolved = path.resolve()
    except OSError:
        return None
    if not resolved.is_file():
        return None
    return resolved.as_uri()


def _render_image_html(alt: str, src: str, image_root: Path | None) -> str:
    resolved = resolve_chat_image_src(src, image_root)
    alt_e = html.escape(alt or "image")
    if not resolved:
        return f'<span style="color:#94a3b8;">[{alt_e}]</span>'
    src_e = html.escape(resolved, quote=True)
    return (
        f'<div style="margin:8px 0 4px 0;">'
        f'<img src="{src_e}" alt="{alt_e}" width="{_MAX_CHAT_IMAGE_WIDTH}" />'
        f'<div style="color:#94a3b8; font-size:11px; margin-top:2px;">{alt_e}</div>'
        f"</div>"
    )


def _render_inline(text: str, image_root: Path | None = None) -> str:
    """Escape text, then restore images, links, bold and inline code spans."""
    if not text:
        return ""
    placeholders: dict[str, str] = {}

    def _hold(html_frag: str) -> str:
        key = f"@@EURIKAHTML{len(placeholders)}@@"
        placeholders[key] = html_frag
        return key

    def _image_sub(m: re.Match[str]) -> str:
        return _hold(_render_image_html(m.group(1), m.group(2), image_root))

    def _link_sub(m: re.Match[str]) -> str:
        label = html.escape(m.group(1))
        href = html.escape(m.group(2), quote=True)
        return _hold(
            f'<a href="{href}" style="color:#93c5fd; text-decoration:underline;">{label}</a>'
        )

    def _code_sub(m: re.Match[str]) -> str:
        inner = html.escape(m.group(1))
        return _hold(
            f'<code style="background-color:#1e293b; color:#fde68a; '
            f'font-family:monospace; padding:1px 4px;">{inner}</code>'
        )

    protected = _IMAGE_RE.sub(_image_sub, text)
    protected = _LINK_RE.sub(_link_sub, protected)
    protected = _INLINE_CODE_RE.sub(_code_sub, protected)
    pieces: list[str] = []
    pos = 0
    for m in _BOLD_RE.finditer(protected):
        pieces.append(html.escape(protected[pos : m.start()]).replace("\n", "<br>"))
        bold_inner = m.group(1)
        if "@@EURIKAHTML" in bold_inner:
            pieces.append(f"<b>{bold_inner}</b>")
        else:
            pieces.append(f"<b>{html.escape(bold_inner)}</b>")
        pos = m.end()
    pieces.append(html.escape(protected[pos:]).replace("\n", "<br>"))
    out = "".join(pieces)
    for key, frag in placeholders.items():
        out = out.replace(key, frag)
    return out


def _next_nonempty(lines: list[str], start: int) -> str | None:
    for look in lines[start:]:
        if look.strip():
            return look
    return None


def _render_text_block(text: str, image_root: Path | None = None) -> str:
    """Paragraphs, headings, quotes, images, lists (no ``<ol>`` — Qt leaks numbering)."""
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
        ordered = bool(list_ordered)
        rows: list[str] = []
        for i, item in enumerate(list_buf, start=1):
            marker = f"{i}." if ordered else "•"
            rows.append(
                f'<p style="margin:2px 0 2px 16px;">{html.escape(marker)}&nbsp;'
                f"{_render_inline(item, image_root)}</p>"
            )
        parts.append("".join(rows))
        list_buf = []
        list_ordered = None

    para: list[str] = []

    def flush_para() -> None:
        nonlocal para
        if not para:
            return
        body = _render_inline("\n".join(para), image_root)
        parts.append(f'<p style="margin:4px 0;">{body}</p>')
        para = []

    for idx, line in enumerate(lines):
        img_line = _IMAGE_LINE_RE.match(line.strip())
        if img_line:
            flush_para()
            flush_list()
            parts.append(_render_image_html(img_line.group(1), img_line.group(2), image_root))
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            flush_para()
            flush_list()
            level = len(heading.group(1))
            size = {1: 16, 2: 15, 3: 14}.get(level, 13)
            parts.append(
                f'<p style="margin:8px 0 4px 0; font-size:{size}px;">'
                f"<b>{_render_inline(heading.group(2), image_root)}</b></p>"
            )
            continue
        if _HR_RE.match(line.strip()):
            flush_para()
            flush_list()
            parts.append('<hr style="border:0; border-top:1px solid #334155; margin:8px 0;" />')
            continue
        quote = _QUOTE_RE.match(line)
        if quote:
            flush_para()
            flush_list()
            parts.append(
                f'<p style="margin:4px 0 4px 12px; color:#94a3b8;">'
                f"{_render_inline(quote.group(1), image_root)}</p>"
            )
            continue
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
            nxt = _next_nonempty(lines, idx + 1)
            if list_buf and nxt is not None and _LIST_ITEM_RE.match(nxt):
                continue
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
    image_root: Path | str | None = None,
) -> str:
    """Convert light markdown to Qt-rich HTML. Mutates ``payloads`` for fences."""
    store: MutableMapping[str, str] = payloads if payloads is not None else {}
    root = Path(image_root) if image_root else None
    chunks: list[str] = []
    for kind, lang, body in split_fenced_segments(text or ""):
        if kind == "fence":
            chunks.append(_render_fence(body, lang, store))
        else:
            chunks.append(_render_text_block(body, root))
    return "".join(chunks) or _render_inline(text or "", root)


def format_chat_line_html(
    role: str,
    text: str,
    *,
    is_error: bool = False,
    payloads: MutableMapping[str, str] | None = None,
    image_root: Path | str | None = None,
    dark: bool | None = None,
) -> str:
    """Isolated message card. Tables prevent Qt from continuing lists across appends."""
    from qt_app.ui.styles import is_dark_theme

    use_dark = is_dark_theme() if dark is None else bool(dark)
    body = render_chat_markdown(text, payloads=payloads, image_root=image_root)
    if role == "user":
        name = "You"
        name_color = "#93c5fd" if use_dark else "#1e40af"
        accent = "#3b82f6"
        bg = "#1e293b" if use_dark else "#eff6ff"
        fg = "#e5e7eb" if use_dark else "#111827"
    elif is_error:
        name = "Eurika"
        name_color = "#fca5a5" if use_dark else "#b91c1c"
        accent = "#ef4444"
        bg = "#3f1d1d" if use_dark else "#fef2f2"
        fg = "#fecaca" if use_dark else "#7f1d1d"
    else:
        name = "Eurika"
        name_color = "#86efac" if use_dark else "#15803d"
        accent = "#22c55e"
        bg = "#052e16" if use_dark else "#f0fdf4"
        fg = "#e5e7eb" if use_dark else "#14532d"
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" '
        f'style="margin:0 0 12px 0;">'
        f"<tr>"
        f'<td width="4" bgcolor="{accent}">&nbsp;</td>'
        f'<td bgcolor="{bg}" style="padding:8px 10px;">'
        f'<p style="margin:0 0 6px 0; font-family:sans-serif; font-size:12px; '
        f'color:{name_color};"><b>{name}</b></p>'
        f'<div style="font-family:sans-serif; font-size:13px; color:{fg};">{body}</div>'
        f"</td></tr></table>"
        # Extra break so the next QTextBrowser.insertHtml cannot inherit list format.
        "<p style=\"margin:0; font-size:1px; color:transparent;\">&nbsp;</p>"
    )
