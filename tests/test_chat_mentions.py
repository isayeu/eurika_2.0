"""Tests for Chat @-mention autocomplete catalog (A1 Cursor-like)."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.api.chat_mentions import (
    build_mention_catalog,
    extract_at_token,
    filter_mention_candidates,
    load_modules_from_self_map,
    mention_candidates,
    smell_mention_ids,
)


def test_smell_mention_ids_excludes_cyclic_alias() -> None:
    ids = smell_mention_ids()
    assert "god_module" in ids
    assert "cyclic_dependency" in ids
    assert "cyclic" not in ids


def test_load_modules_from_self_map(tmp_path: Path) -> None:
    assert load_modules_from_self_map(None) == []
    assert load_modules_from_self_map(tmp_path) == []
    (tmp_path / "self_map.json").write_text(
        json.dumps(
            {
                "modules": [
                    {"path": "patch_engine.py"},
                    {"path": "eurika/api/chat.py"},
                    {"path": "patch_engine.py"},
                    {"name": "orphan_name.py"},
                    "bare.py",
                    {"path": "bad path with spaces.py"},
                ]
            }
        ),
        encoding="utf-8",
    )
    mods = load_modules_from_self_map(tmp_path)
    assert mods == ["patch_engine.py", "eurika/api/chat.py", "orphan_name.py", "bare.py"]


def test_filter_mention_candidates_prefix_basename() -> None:
    catalog = [
        "god_module",
        "hub",
        "patch_engine.py",
        "patch_apply.py",
        "eurika/api/chat.py",
        "code_awareness.py",
    ]
    assert filter_mention_candidates(catalog, "god") == ["god_module"]
    pats = filter_mention_candidates(catalog, "pat")
    assert pats[0] in {"patch_engine.py", "patch_apply.py"}
    assert "patch_engine.py" in pats
    assert "patch_apply.py" in pats
    chats = filter_mention_candidates(catalog, "chat")
    assert "eurika/api/chat.py" in chats


def test_mention_candidates_without_self_map_still_has_smells(tmp_path: Path) -> None:
    out = mention_candidates(tmp_path, "god")
    assert out == ["god_module"]
    catalog = build_mention_catalog(tmp_path)
    assert catalog == smell_mention_ids()


def test_mention_candidates_with_self_map(tmp_path: Path) -> None:
    (tmp_path / "self_map.json").write_text(
        json.dumps({"modules": [{"path": "patch_engine.py"}, {"path": "code_awareness.py"}]}),
        encoding="utf-8",
    )
    out = mention_candidates(tmp_path, "pat")
    assert "patch_engine.py" in out
    full = build_mention_catalog(tmp_path)
    assert full.index("god_module") < full.index("patch_engine.py")


def test_extract_at_token() -> None:
    assert extract_at_token("hello", 5) is None
    assert extract_at_token("рефактори @pat", 14) == (10, 14, "pat")
    assert extract_at_token("@", 1) == (0, 1, "")
    assert extract_at_token("a@b", 3) is None  # mid-word / email-ish
    assert extract_at_token("x @god_module y", 13) == (2, 13, "god_module")
    # Cursor in middle of token
    assert extract_at_token("@patch_engine", 4) == (0, 4, "pat")
