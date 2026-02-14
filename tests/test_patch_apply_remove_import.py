"""Tests for patch_apply with remove_cyclic_import, split_module, and extract_class operations."""
from pathlib import Path
from patch_apply import apply_patch_plan


def test_apply_split_module(tmp_path: Path) -> None:
    """split_module extracts definitions into new file when params.imports_from present."""
    target = tmp_path / "god.py"
    target.write_text(
        '"""God module."""\n'
        "from foo import bar\n\n"
        "def use_bar():\n"
        "    return bar()\n"
    )
    plan = {
        "operations": [
            {
                "target_file": "god.py",
                "kind": "split_module",
                "description": "Split god module",
                "diff": "",
                "params": {"imports_from": ["foo"]},
            }
        ]
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert "god.py" in report["modified"]
    assert "god_extracted.py" in report["modified"]
    extracted = tmp_path / "god_extracted.py"
    assert extracted.exists()
    assert "def use_bar" in extracted.read_text()
    assert "from god_extracted import use_bar" in (tmp_path / "god.py").read_text()


def test_apply_split_module_fallback_to_diff_when_no_extractable(tmp_path: Path) -> None:
    """split_module falls back to appending diff when no defs use only one of imports_from."""
    target = tmp_path / "mixed.py"
    target.write_text("from a import x\nfrom b import y\n\ndef f():\n    return x() + y()\n")
    plan = {
        "operations": [
            {
                "target_file": "mixed.py",
                "kind": "split_module",
                "description": "Split",
                "diff": "# TODO: split mixed.py\n",
                "params": {"imports_from": ["a", "b"]},
            }
        ]
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert "mixed.py" in report["modified"]
    assert (tmp_path / "mixed_extracted.py").exists() is False
    assert "# TODO: split mixed.py" in (tmp_path / "mixed.py").read_text()


def test_apply_extract_class(tmp_path: Path) -> None:
    """extract_class extracts methods into new class when params present."""
    target = tmp_path / "big.py"
    target.write_text(
        '"""Big class."""\n'
        "class Big:\n"
        "    def pure(self, x, y):\n"
        "        return x + y\n"
    )
    plan = {
        "operations": [
            {
                "target_file": "big.py",
                "kind": "extract_class",
                "description": "Extract pure methods",
                "diff": "",
                "params": {"target_class": "Big", "methods_to_extract": ["pure"]},
            }
        ]
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert "big.py" in report["modified"]
    assert "big_bigextracted.py" in report["modified"]
    extracted = tmp_path / "big_bigextracted.py"
    assert extracted.exists()
    assert "def pure" in extracted.read_text()
    assert "BigExtracted.pure" in (tmp_path / "big.py").read_text()


def test_apply_extract_class_skips_when_methods_use_self(tmp_path: Path) -> None:
    """extract_class skips when requested methods use self.attr."""
    target = tmp_path / "big.py"
    target.write_text("class Big:\n    def uses_self(self):\n        return self.x\n")
    plan = {
        "operations": [
            {
                "target_file": "big.py",
                "kind": "extract_class",
                "description": "Extract",
                "diff": "",
                "params": {"target_class": "Big", "methods_to_extract": ["uses_self"]},
            }
        ]
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert report["modified"] == []
    assert "big.py" in report["skipped"]
    assert not (tmp_path / "big_bigextracted.py").exists()


def test_apply_remove_cyclic_import(tmp_path: Path) -> None:
    """Apply remove_cyclic_import operation modifies file via AST."""
    target = tmp_path / 'mod.py'
    target.write_text('import bar\nimport foo\nx = 1\n')
    plan = {'operations': [{'target_file': 'mod.py', 'kind': 'remove_cyclic_import', 'description': 'Remove import to break cycle', 'diff': '# removed', 'smell_type': 'cyclic_dependency', 'params': {'target_module': 'foo'}}]}
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert 'mod.py' in report['modified']
    content = target.read_text()
    assert 'import foo' not in content
    assert 'import bar' in content
    assert 'x = 1' in content

def test_apply_remove_cyclic_import_dry_run(tmp_path: Path) -> None:
    """Dry run reports would-be modified file."""
    target = tmp_path / 'mod.py'
    target.write_text('import foo\n')
    plan = {'operations': [{'target_file': 'mod.py', 'kind': 'remove_cyclic_import', 'description': 'Remove', 'diff': '', 'params': {'target_module': 'foo'}}]}
    report = apply_patch_plan(tmp_path, plan, dry_run=True)
    assert 'mod.py' in report['modified']
    assert 'import foo' in target.read_text()