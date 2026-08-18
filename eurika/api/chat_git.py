"""Literate git commit/push for Chat HITL (Cursor-like protocol).

Never: git config, --no-verify, force push, interactive rebase, add -A.
Commit only listed paths; skip secret-looking files; push via -u origin HEAD.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Iterable

_FORBIDDEN_FLAGS = frozenset(
    {
        "--no-verify",
        "--no-gpg-sign",
        "--force",
        "--force-with-lease",
        "--amend",
        "--interactive",
        "--hard",
        "--mixed",
        "--soft",
        "-i",
        "-f",
    }
)
_ALLOWED_SUBCOMMANDS = frozenset(
    {
        "status",
        "diff",
        "log",
        "add",
        "commit",
        "push",
        "rev-parse",
        "rev-list",
        "remote",
        "symbolic-ref",
    }
)
_SECRET_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".netrc",
        "credentials.json",
        "secrets.json",
        "auth.json",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "id_dsa",
    }
)
_SECRET_SUFFIXES = (".pem", ".p12", ".pfx", ".key")
_PROTECTED_BRANCHES = frozenset({"main", "master"})


def looks_like_secret_path(path: str) -> bool:
    """True for credential / env files that must not be committed."""
    raw = (path or "").replace("\\", "/").strip()
    if not raw:
        return False
    name = Path(raw).name
    lower = name.lower()
    if lower.endswith(".example") or lower.endswith(".sample"):
        return False
    if name in _SECRET_NAMES or lower in _SECRET_NAMES:
        return True
    if lower.startswith(".env.") and not lower.endswith(".example"):
        return True
    if any(lower.endswith(suf) for suf in _SECRET_SUFFIXES):
        return True
    return False


def assert_safe_git_argv(argv: list[str]) -> None:
    """Refuse destructive / hook-skipping git flags before subprocess."""
    if not argv or argv[0] != "git":
        raise ValueError(f"not a git argv: {argv!r}")
    if len(argv) < 2:
        raise ValueError("git subcommand required")
    sub = argv[1]
    if sub == "-C":
        raise ValueError("git -C is not used; cwd is the project root")
    if sub == "config":
        raise ValueError("git config is not allowed")
    if sub not in _ALLOWED_SUBCOMMANDS:
        raise ValueError(f"git {sub} is not allowed")
    for token in argv[2:]:
        if token == "--":
            break
        if token in _FORBIDDEN_FLAGS:
            raise ValueError(f"forbidden git flag: {token}")
        # Combined shorts like -am are not used; still catch -f*
        if token.startswith("-") and not token.startswith("--"):
            if "f" in token[1:] and sub == "push":
                raise ValueError("forbidden git flag: -f")
            if "i" in token[1:] and sub in {"add", "rebase", "commit"}:
                raise ValueError("forbidden git flag: -i")


def git_run(
    project_root: Path,
    args: list[str],
    *,
    input_text: str | None = None,
    timeout: int = 60,
) -> tuple[int, str, list[str]]:
    """Run a vetted git command in project_root. Returns (code, output, argv)."""
    argv = ["git", *args]
    assert_safe_git_argv(argv)
    r = subprocess.run(
        argv,
        cwd=str(project_root),
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    out = ((r.stdout or "") + ("\n" + r.stderr if r.stderr else "")).strip()
    return (r.returncode, out, argv)


def parse_status_porcelain(status_out: str) -> list[str]:
    """Paths from ``git status --porcelain`` (unmerged/renames → new path)."""
    files: list[str] = []
    for line in (status_out or "").splitlines():
        if len(line) < 4:
            continue
        body = line[3:]
        if " -> " in body:
            body = body.split(" -> ", 1)[-1]
        path = body.strip().strip('"')
        if path:
            files.append(path)
    seen: set[str] = set()
    out: list[str] = []
    for p in files:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def select_commit_paths(paths: Iterable[str]) -> tuple[list[str], list[str]]:
    """Split dirty paths into committable vs skipped secrets."""
    include: list[str] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        path = (raw or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        if looks_like_secret_path(path) or "/.env" in path.replace("\\", "/"):
            skipped.append(path)
            continue
        if ".." in Path(path).parts:
            skipped.append(path)
            continue
        include.append(path)
    return (include, skipped)


def collect_commit_preview(project_root: Path) -> dict[str, Any]:
    """status + log + branch + safe path list for HITL preview."""
    root = Path(project_root)
    code, status, _ = git_run(root, ["status", "--porcelain", "-unormal"])
    if code != 0:
        return {
            "ok": False,
            "error": status or "git status failed",
            "include": [],
            "skipped_secrets": [],
            "status": status,
            "log": "",
            "branch": "",
            "protected": False,
        }
    dirty = parse_status_porcelain(status)
    include, skipped = select_commit_paths(dirty)
    log_code, log_out, _ = git_run(root, ["log", "-8", "--oneline"])
    log = log_out if log_code == 0 else ""
    b_code, branch_out, _ = git_run(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch_out.strip() if b_code == 0 else ""
    return {
        "ok": True,
        "error": None,
        "include": include,
        "skipped_secrets": skipped,
        "status": status,
        "log": log,
        "branch": branch,
        "protected": branch in _PROTECTED_BRANCHES,
    }


def inspect_push(project_root: Path) -> dict[str, Any]:
    """Current branch, origin, upstream, commits-ahead for push preview."""
    root = Path(project_root)
    b_code, branch_out, _ = git_run(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch_out.strip() if b_code == 0 else ""
    r_code, remotes, _ = git_run(root, ["remote"])
    has_origin = r_code == 0 and "origin" in remotes.split()
    u_code, upstream_out, _ = git_run(root, ["rev-parse", "--abbrev-ref", "@{upstream}"])
    upstream = upstream_out.strip() if u_code == 0 else ""
    ahead = None
    if upstream:
        a_code, ahead_out, _ = git_run(root, ["rev-list", "--count", f"{upstream}..HEAD"])
        if a_code == 0:
            try:
                ahead = int(ahead_out.strip() or "0")
            except ValueError:
                ahead = None
    return {
        "branch": branch,
        "protected": branch in _PROTECTED_BRANCHES,
        "has_origin": has_origin,
        "upstream": upstream,
        "needs_upstream": not bool(upstream),
        "ahead": ahead,
    }


def commit_selected(
    project_root: Path, message: str, paths: list[str]
) -> tuple[bool, str, str]:
    """``git add -- <paths>`` then ``git commit -F -``. Never -A / --no-verify."""
    msg = (message or "").strip()
    if not msg:
        return (False, "commit message is empty", "")
    include, skipped = select_commit_paths(paths)
    if skipped and not include:
        return (
            False,
            "нет безопасных файлов для коммита (пропущены секреты: "
            + ", ".join(skipped)
            + ")",
            "",
        )
    if not include:
        return (False, "нет изменений для коммита", "")
    root = Path(project_root)
    add_code, add_out, add_argv = git_run(root, ["add", "--", *include])
    if add_code != 0:
        return (False, add_out or "git add failed", " ".join(add_argv))
    commit_code, commit_out, commit_argv = git_run(
        root,
        ["commit", "-F", "-"],
        input_text=msg + "\n",
    )
    term = f"$ git add -- {' '.join(include)} && git commit -F -"
    if commit_code != 0:
        return (False, commit_out or "git commit failed", term)
    extra = f"\nпропущены секреты: {', '.join(skipped)}" if skipped else ""
    return (True, (commit_out or "ok") + extra, term)


def push_current_branch(project_root: Path) -> tuple[bool, str, str]:
    """``git push`` or ``git push -u origin HEAD``. Never --force."""
    info = inspect_push(project_root)
    if not info.get("has_origin"):
        return (False, "нет remote origin — push некуда", "")
    if info.get("needs_upstream"):
        args = ["push", "-u", "origin", "HEAD"]
        term = "$ git push -u origin HEAD"
    else:
        args = ["push"]
        term = "$ git push"
    code, out, _argv = git_run(Path(project_root), args, timeout=120)
    if code != 0:
        return (False, out or "git push failed", term)
    return (True, out or "ok", term)


def apply_pending_git(project_root: Path, pending: dict[str, Any]) -> dict[str, Any]:
    """Execute HITL commit and/or push from ``pending_git_commit``."""
    action = str(pending.get("action") or "commit").strip() or "commit"
    push_after = bool(pending.get("push_after")) or action in {"push", "commit_push"}
    do_commit = action in {"commit", "commit_push"}
    do_push = push_after or action == "push"
    texts: list[str] = []
    cmds: list[str] = []
    outs: list[str] = []
    ok = True
    if do_commit:
        message = str(pending.get("message") or "").strip()
        paths = [str(p) for p in (pending.get("paths") or []) if str(p).strip()]
        if not paths:
            preview = collect_commit_preview(project_root)
            paths = list(preview.get("include") or [])
        cok, cout, cterm = commit_selected(project_root, message, paths)
        cmds.append(cterm)
        outs.append(cout)
        if cok:
            texts.append(f"Коммит выполнен: {cout}")
        else:
            texts.append(f"Ошибка коммита: {cout}")
            ok = False
            do_push = False
    if do_push:
        pok, pout, pterm = push_current_branch(project_root)
        cmds.append(pterm)
        outs.append(pout)
        if pok:
            texts.append(f"Push выполнен: {pout}")
        else:
            texts.append(f"Ошибка push: {pout}")
            ok = False
    term_cmd = " && ".join(c for c in cmds if c)
    term_out = "\n\n".join(o for o in outs if o)
    return {
        "ok": ok,
        "text": "\n".join(texts) if texts else "Нечего выполнять.",
        "terminal_cmd": term_cmd,
        "terminal_output": term_out,
        "error": None if ok else term_out or "git failed",
    }


def format_commit_preview_blocks(
    *,
    status_out: str,
    diff_out: str,
    preview: dict[str, Any],
    proposed: str,
    token: str,
    push_after: bool,
    push_info: dict[str, Any] | None = None,
) -> list[str]:
    """Chat markdown for HITL git preview."""
    blocks = [f"**git status**\n```\n{status_out or '(пусто)'}\n```"]
    if diff_out:
        clipped = diff_out[:4000] + ("..." if len(diff_out) > 4000 else "")
        blocks.append(f"**git diff**\n```\n{clipped}\n```")
    log = str(preview.get("log") or "").strip()
    if log:
        blocks.append(f"**недавние коммиты (стиль)**\n```\n{log}\n```")
    include = list(preview.get("include") or [])
    if include:
        listed = "\n".join(f"- `{p}`" for p in include[:40])
        more = f"\n- … ещё {len(include) - 40}" if len(include) > 40 else ""
        blocks.append(f"**в коммит войдут** ({len(include)})\n{listed}{more}")
    skipped = list(preview.get("skipped_secrets") or [])
    if skipped:
        blocks.append(
            "**пропускаю (похоже на секреты)**\n"
            + "\n".join(f"- `{p}`" for p in skipped)
        )
    branch = str(preview.get("branch") or "")
    if preview.get("protected"):
        blocks.append(
            f"Ветка `{branch}` — основная. Обычный push после Apply разрешён; "
            "force push Эврика не делает."
        )
    if push_after:
        info = push_info or {}
        if not info.get("has_origin"):
            blocks.append("Push после коммита **не смогу**: нет remote `origin`.")
        elif info.get("needs_upstream"):
            blocks.append("После коммита: `git push -u origin HEAD`.")
        else:
            blocks.append("После коммита: `git push`.")
    verb = "коммит и push" if push_after else "коммит"
    blocks.append(
        f"\nПредлагаю {verb} с сообщением: «{proposed}». "
        f"Напиши **применяй token:{token}** для подтверждения (или нажми [Apply])."
    )
    return blocks
