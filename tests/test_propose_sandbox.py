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
