"""Literate git commit/push protocol for Chat HITL."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from eurika.api.chat_git import (
    apply_pending_git,
    assert_safe_git_argv,
    commit_selected,
    looks_like_secret_path,
    parse_status_porcelain,
    select_commit_paths,
)


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test"],
        cwd=str(root),
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(root),
        capture_output=True,
        check=True,
    )
    (root / "README").write_text("init\n", encoding="utf-8")
    subprocess.run(["git", "add", "README"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(root),
        capture_output=True,
        check=True,
    )


def test_assert_safe_git_argv_blocks_hooks_force_config() -> None:
    with pytest.raises(ValueError):
        assert_safe_git_argv(["git", "commit", "--no-verify", "-m", "x"])
    with pytest.raises(ValueError):
        assert_safe_git_argv(["git", "push", "--force"])
    with pytest.raises(ValueError):
        assert_safe_git_argv(["git", "push", "-f"])
    with pytest.raises(ValueError):
        assert_safe_git_argv(["git", "push", "--force-with-lease"])
    with pytest.raises(ValueError):
        assert_safe_git_argv(["git", "config", "user.email", "x"])
    with pytest.raises(ValueError):
        assert_safe_git_argv(["git", "commit", "--amend", "-m", "x"])
    assert_safe_git_argv(["git", "commit", "-F", "-"])
    assert_safe_git_argv(["git", "push", "-u", "origin", "HEAD"])
    assert_safe_git_argv(["git", "add", "--", "a.py", "b.py"])


def test_secret_paths_are_skipped() -> None:
    assert looks_like_secret_path(".env") is True
    assert looks_like_secret_path("credentials.json") is True
    assert looks_like_secret_path("id_rsa") is True
    assert looks_like_secret_path("cert.pem") is True
    assert looks_like_secret_path(".env.example") is False
    assert looks_like_secret_path("eurika/api/chat_git.py") is False
    include, skipped = select_commit_paths(["a.py", ".env", "docs/CHAT.md"])
    assert include == ["a.py", "docs/CHAT.md"]
    assert skipped == [".env"]


def test_commit_selected_does_not_add_all_or_secrets(tmp_path: Path) -> None:
    recorded: list[list[str]] = []
    real_run = subprocess.run

    def _spy(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args")
        if isinstance(cmd, list):
            recorded.append(list(cmd))
        return real_run(*args, **kwargs)

    import eurika.api.chat_git as git_mod

    monkey_path = pytest.MonkeyPatch()
    monkey_path.setattr(git_mod.subprocess, "run", _spy)
    try:
        _init_repo(tmp_path)
        (tmp_path / "keep.py").write_text("x=1\n", encoding="utf-8")
        (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
        (tmp_path / "noise.py").write_text("y=2\n", encoding="utf-8")
        ok, out, term = commit_selected(
            tmp_path, "Keep only the intended module", ["keep.py", ".env"]
        )
        assert ok, out
        assert "-A" not in term
        assert "--no-verify" not in term
        assert "git add -- keep.py" in term
        assert ".env" not in term
        log = subprocess.run(
            ["git", "log", "-1", "--name-only", "--pretty=format:"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            check=True,
        )
        names = {n.strip() for n in log.stdout.splitlines() if n.strip()}
        assert names == {"keep.py"}
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            check=True,
        )
        assert ".env" in status.stdout
        assert "noise.py" in status.stdout
        joined = " ".join(" ".join(c) for c in recorded)
        assert "add -A" not in joined
        assert "--no-verify" not in joined
        assert any(c[:3] == ["git", "commit", "-F"] for c in recorded)
    finally:
        monkey_path.undo()


def test_chat_commit_and_push_hitl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    work = tmp_path / "work"
    origin = tmp_path / "origin.git"
    work.mkdir()
    subprocess.run(["git", "init", "--bare", str(origin)], capture_output=True, check=True)
    _init_repo(work)
    subprocess.run(
        ["git", "remote", "add", "origin", str(origin)],
        cwd=str(work),
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"],
        cwd=str(work),
        capture_output=True,
        check=True,
    )
    (work / "keep.py").write_text("print(1)\n", encoding="utf-8")
    (work / ".env").write_text("SECRET=1\n", encoding="utf-8")
    preview = chat_mod.chat_send(work, "закоммить и запушь")
    text = preview.get("text") or ""
    assert preview.get("error") is None
    assert "keep.py" in text
    assert ".env" in text and "секрет" in text.lower()
    assert "применяй" in text
    assert "git add -A" not in text
    state = json.loads(
        (work / ".eurika" / "chat_history" / "dialog_state.json").read_text(encoding="utf-8")
    )
    pending = state.get("pending_git_commit") or {}
    assert pending.get("push_after") is True
    assert pending.get("action") == "commit_push"
    assert "keep.py" in (pending.get("paths") or [])
    assert ".env" not in (pending.get("paths") or [])
    applied = chat_mod.chat_send(work, "применяй")
    assert applied.get("error") is None, applied
    assert "git add -A" not in str(applied.get("terminal_cmd") or "")
    assert "--force" not in str(applied.get("terminal_cmd") or "")
    log = subprocess.run(
        ["git", "log", "-1", "--oneline"],
        cwd=str(work),
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.stdout.strip()
    remote_log = subprocess.run(
        ["git", "log", "-1", "--oneline"],
        cwd=str(origin),
        capture_output=True,
        text=True,
        check=True,
    )
    assert remote_log.stdout.strip() == log.stdout.strip()


def test_force_push_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import eurika.api.chat as chat_mod
    from eurika.api.chat_direct import is_force_push_request, resolve_direct_handler

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    _init_repo(tmp_path)
    assert is_force_push_request("git push --force") is True
    assert resolve_direct_handler(tmp_path, "git push --force")[0] == "git_push"
    out = chat_mod.chat_send(tmp_path, "git push --force")
    text = (out.get("text") or "").lower()
    assert "force" in text
    assert "применяй" not in (out.get("text") or "")
    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        pending = state.get("pending_git_commit") or {}
        assert not pending.get("message")


def test_combined_request_routes_to_commit_not_bare_push(tmp_path: Path) -> None:
    from eurika.api.chat_direct import (
        is_git_commit_and_push_request,
        resolve_direct_handler,
    )

    assert is_git_commit_and_push_request("закоммить и запушь") is True
    assert is_git_commit_and_push_request("commit and push") is True
    assert resolve_direct_handler(tmp_path, "закоммить и запушь")[0] == "git_commit"
    assert resolve_direct_handler(tmp_path, "запушь")[0] == "git_push"


def test_parse_porcelain_renames() -> None:
    paths = parse_status_porcelain("R  old.py -> new.py\n?? .env\n M keep.py\n")
    assert paths == ["new.py", ".env", "keep.py"]


def test_apply_push_only_after_commit(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "--bare", str(origin)], capture_output=True, check=True)
    _init_repo(work)
    subprocess.run(
        ["git", "remote", "add", "origin", str(origin)],
        cwd=str(work),
        capture_output=True,
        check=True,
    )
    (work / "extra.py").write_text("z=3\n", encoding="utf-8")
    ok, out, _term = commit_selected(work, "Add extra module", ["extra.py"])
    assert ok, out
    result = apply_pending_git(
        work,
        {
            "message": "Push test to origin",
            "action": "push",
            "push_after": True,
            "paths": [],
        },
    )
    assert result["ok"], result
    remote = subprocess.run(
        ["git", "log", "-1", "--oneline"],
        cwd=str(origin),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "extra" in remote.stdout.lower() or remote.stdout.strip()
