"""Tests for patch_apply with remove_cyclic_import operation."""

from pathlib import Path

import pytest

from patch_apply import apply_patch_plan


def test_apply_remove_cyclic_import(tmp_path: Path) -> None:
    """Apply remove_cyclic_import operation modifies file via AST."""
    target = tmp_path / "mod.py"
    target.write_text('import bar\nimport foo\nx = 1\n')
    plan = {
        "operations": [
            {
                "target_file": "mod.py",
                "kind": "remove_cyclic_import",
                "description": "Remove import to break cycle",
                "diff": "# removed",
                "smell_type": "cyclic_dependency",
                "params": {"target_module": "foo"},
            },
        ],
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert "mod.py" in report["modified"]
    content = target.read_text()
    assert "import foo" not in content
    assert "import bar" in content
    assert "x = 1" in content


def test_apply_remove_cyclic_import_dry_run(tmp_path: Path) -> None:
    """Dry run reports would-be modified file."""
    target = tmp_path / "mod.py"
    target.write_text("import foo\n")
    plan = {
        "operations": [
            {
                "target_file": "mod.py",
                "kind": "remove_cyclic_import",
                "description": "Remove",
                "diff": "",
                "params": {"target_module": "foo"},
            },
        ],
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=True)
    assert "mod.py" in report["modified"]
    assert "import foo" in target.read_text()

