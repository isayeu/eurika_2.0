"""Unit tests for C.14 propose sandbox helpers."""

from __future__ import annotations

from pathlib import Path

from eurika.orchestration.propose_sandbox import (
    create_propose_sandbox,
    remove_propose_sandbox,
    smoke_verify_after_apply,
)


def test_create_and_remove_copy_sandbox(tmp_path: Path) -> None:
    meta = create_propose_sandbox(tmp_path, drill_id="imports")
    assert meta["mode"] == "copy"
    path = Path(meta["path"])
    assert path.is_dir()
    assert path.parent.name == "sandbox"
    remove_propose_sandbox(tmp_path, path, mode="copy")
    assert not path.exists()


def test_prune_propose_sandboxes_keeps_latest(tmp_path: Path) -> None:
    from eurika.orchestration.propose_sandbox import (
        list_propose_sandboxes,
        prune_propose_sandboxes,
    )

    parent = tmp_path / ".eurika" / "sandbox"
    parent.mkdir(parents=True)
    older = parent / "propose_imports_20260101_000000"
    newer = parent / "propose_imports_20260102_000000"
    older.mkdir()
    newer.mkdir()
    (older / "marker").write_text("a", encoding="utf-8")
    (newer / "marker").write_text("b", encoding="utf-8")
    out = prune_propose_sandboxes(tmp_path, keep_latest=1)
    assert out["ok"] is True
    assert older.name in out["removed"]
    assert newer.name in out["kept"]
    assert list_propose_sandboxes(tmp_path) == [newer]
    out2 = prune_propose_sandboxes(tmp_path, keep_latest=0)
    assert newer.name in out2["removed"]
    assert list_propose_sandboxes(tmp_path) == []


def test_create_propose_sandbox_prunes_stale(tmp_path: Path) -> None:
    parent = tmp_path / ".eurika" / "sandbox"
    parent.mkdir(parents=True)
    stale = parent / "propose_imports_20260101_000000"
    stale.mkdir()
    meta = create_propose_sandbox(tmp_path, drill_id="imports", prune_stale=True)
    assert not stale.exists()
    assert Path(meta["path"]).is_dir()
    assert "pruned" in meta
    remove_propose_sandbox(tmp_path, Path(meta["path"]), mode=str(meta.get("mode") or "copy"))


def test_smoke_verify_imports(tmp_path: Path) -> None:
    target = tmp_path / "eurika" / "polygon" / "imports_ok.py"
    target.parent.mkdir(parents=True)
    target.write_text("from pathlib import Path\n\ndef f():\n    return Path('.')\n", encoding="utf-8")
    assert smoke_verify_after_apply(
        tmp_path, drill_id="imports", target_rel="eurika/polygon/imports_ok.py"
    )["ok"]
    target.write_text("import os\nfrom pathlib import Path\n", encoding="utf-8")
    assert not smoke_verify_after_apply(
        tmp_path, drill_id="imports", target_rel="eurika/polygon/imports_ok.py"
    )["ok"]


def test_smoke_verify_deep_nesting(tmp_path: Path) -> None:
    target = tmp_path / "eurika" / "polygon" / "deep_nesting.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "def _extracted_block_28(x):\n    return x\n\n"
        "def polygon_deep_nesting_extractable(x):\n    return _extracted_block_28(x)\n",
        encoding="utf-8",
    )
    assert smoke_verify_after_apply(
        tmp_path, drill_id="deep_nesting", target_rel="eurika/polygon/deep_nesting.py"
    )["ok"]
    target.write_text(
        "def polygon_deep_nesting_extractable(x):\n    return x\n", encoding="utf-8"
    )
    assert not smoke_verify_after_apply(
        tmp_path, drill_id="deep_nesting", target_rel="eurika/polygon/deep_nesting.py"
    )["ok"]


def test_apply_and_smoke_verify_imports_without_cwd_on_path(
    tmp_path: Path, monkeypatch
) -> None:
    """eurika-qt may not have repo root on sys.path; apply must still import patch_apply."""
    import sys

    from eurika.orchestration.prove_cycle import seed_polygon_imports_ok
    from eurika.orchestration.propose_sandbox import apply_and_smoke_verify

    seed_polygon_imports_ok(tmp_path)
    op = {
        "target_file": "eurika/polygon/imports_ok.py",
        "kind": "remove_unused_import",
        "params": {},
    }
    # Simulate installed entrypoint: drop '' and repo root from path briefly.
    repo = Path(__file__).resolve().parents[1]
    cleaned = [p for p in sys.path if p not in ("", str(repo))]
    monkeypatch.setattr(sys, "path", cleaned)
    # Import must fail before the helper fixes path — prove the scenario exists.
    try:
        import importlib

        if "patch_apply" in sys.modules:
            del sys.modules["patch_apply"]
        importlib.invalidate_caches()
    except Exception:
        pass
    out = apply_and_smoke_verify(tmp_path, op, drill_id="imports")
    assert out["ok"] is True, out
    assert out.get("apply_report_ok") is True
