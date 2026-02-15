"""Tests for patch_apply with remove_cyclic_import, remove_unused_import, split_module, extract_class."""
from pathlib import Path
from patch_apply import apply_patch_plan


def test_apply_remove_unused_import(tmp_path: Path) -> None:
    """remove_unused_import: AST removes unused imports (ROADMAP 2.4.1)."""
    (tmp_path / "m.py").write_text("import os\nimport json\nx = 1\n", encoding="utf-8")
    plan = {
        "operations": [
            {
                "target_file": "m.py",
                "kind": "remove_unused_import",
                "description": "Remove unused imports",
                "diff": "# Removed.",
                "smell_type": None,
            }
        ]
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert report["modified"] == ["m.py"]
    content = (tmp_path / "m.py").read_text()
    assert "import os" not in content or "import json" not in content
    assert "x = 1" in content


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


def test_apply_split_module_by_function_fallback(tmp_path: Path) -> None:
    """split_module uses split_module_by_function when import/class extraction yields nothing."""
    target = tmp_path / "mod.py"
    target.write_text(
        '"""Module with standalone function."""\n'
        "import json\n\n"
        "def process_data(data):\n"
        "    x = json.loads(data)\n"
        "    return x.get('key', 0)\n"
    )
    plan = {
        "operations": [
            {
                "target_file": "mod.py",
                "kind": "split_module",
                "description": "Split",
                "diff": "# TODO\n",
                "params": {"imports_from": ["other_unused"]},
            }
        ]
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert "mod.py" in report["modified"]
    assert "mod_process_data.py" in report["modified"]
    extracted = tmp_path / "mod_process_data.py"
    assert extracted.exists()
    assert "def process_data" in extracted.read_text()
    assert "from mod_process_data import process_data" in (tmp_path / "mod.py").read_text()


def test_apply_split_module_by_class_fallback(tmp_path: Path) -> None:
    """split_module uses split_module_by_class when import-based extraction yields nothing."""
    target = tmp_path / "god.py"
    target.write_text(
        '"""God module with large self-contained class."""\n'
        "class BigHandler:\n"
        "    def a(self): return 1\n"
        "    def b(self): return 2\n"
        "    def c(self): return 3\n"
    )
    plan = {
        "operations": [
            {
                "target_file": "god.py",
                "kind": "split_module",
                "description": "Split",
                "diff": "# TODO\n",
                "params": {"imports_from": []},
            }
        ]
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert "god.py" in report["modified"]
    assert "god_bighandler.py" in report["modified"]
    extracted = tmp_path / "god_bighandler.py"
    assert extracted.exists()
    assert "class BigHandler" in extracted.read_text()
    assert "from god_bighandler import BigHandler" in (tmp_path / "god.py").read_text()


def test_apply_split_module_extracts_when_def_uses_multiple_imports(tmp_path: Path) -> None:
    """split_module extracts def using multiple imports (relaxed: assign to first stem cluster)."""
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
    assert "mixed_extracted.py" in report["modified"]
    extracted = tmp_path / "mixed_extracted.py"
    assert extracted.exists()
    assert "def f" in extracted.read_text()
    assert "from mixed_extracted import f" in (tmp_path / "mixed.py").read_text()


def test_apply_split_module_by_function_skips_when_uses_module_constant(tmp_path: Path) -> None:
    """split_module_by_function does NOT extract functions that reference module-level constants."""
    target = tmp_path / "mod.py"
    target.write_text(
        "CONST = 42\n\n"
        "def uses_const():\n"
        "    return CONST + 1\n"
    )
    plan = {
        "operations": [
            {
                "target_file": "mod.py",
                "kind": "split_module",
                "description": "Split",
                "diff": "# TODO\n",
                "params": {"imports_from": ["other"]},
            }
        ]
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert "mod.py" in report["modified"]
    assert (tmp_path / "mod_uses_const.py").exists() is False
    assert "# TODO" in (tmp_path / "mod.py").read_text()


def test_apply_split_module_fallback_to_diff_when_no_extractable(tmp_path: Path) -> None:
    """split_module falls back to appending diff when no defs, no extractable class, no standalone function."""
    target = tmp_path / "tiny.py"
    target.write_text("x = 1\ny = 2\n")
    plan = {
        "operations": [
            {
                "target_file": "tiny.py",
                "kind": "split_module",
                "description": "Split",
                "diff": "# TODO: split tiny.py\n",
                "params": {"imports_from": []},
            }
        ]
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert "tiny.py" in report["modified"]
    assert (tmp_path / "tiny_extracted.py").exists() is False
    assert "# TODO: split tiny.py" in (tmp_path / "tiny.py").read_text()


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

def test_apply_introduce_facade(tmp_path: Path) -> None:
    """introduce_facade creates {stem}_api.py re-exporting public symbols."""
    (tmp_path / "bottleneck.py").write_text(
        "def foo(): return 1\n"
        "class Bar: pass\n"
        "def _private(): pass\n"
    )
    plan = {
        "operations": [
            {
                "target_file": "bottleneck.py",
                "kind": "introduce_facade",
                "description": "Introduce facade",
                "diff": "",
                "params": {"callers": ["a.py", "b.py"]},
            }
        ]
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert "bottleneck_api.py" in report["modified"]
    facade = tmp_path / "bottleneck_api.py"
    assert facade.exists()
    content = facade.read_text()
    assert "from bottleneck import foo, Bar" in content or "from bottleneck import Bar, foo" in content
    assert "__all__" in content
    assert "Facade for bottleneck" in content
    assert "a.py" in content or "b.py" in content


def test_apply_introduce_facade_skips_when_api_exists(tmp_path: Path) -> None:
    """introduce_facade skips if *_api.py already exists."""
    (tmp_path / "m.py").write_text("def f(): pass\n")
    (tmp_path / "m_api.py").write_text("existing\n")
    plan = {"operations": [{"target_file": "m.py", "kind": "introduce_facade", "description": "x", "diff": "", "params": {}}]}
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert report["modified"] == []
    assert "m.py" in report["skipped"] or report["skipped"]
    assert (tmp_path / "m_api.py").read_text() == "existing\n"


def test_apply_remove_cyclic_import_dry_run(tmp_path: Path) -> None:
    """Dry run reports would-be modified file."""
    target = tmp_path / 'mod.py'
    target.write_text('import foo\n')
    plan = {'operations': [{'target_file': 'mod.py', 'kind': 'remove_cyclic_import', 'description': 'Remove', 'diff': '', 'params': {'target_module': 'foo'}}]}
    report = apply_patch_plan(tmp_path, plan, dry_run=True)
    assert 'mod.py' in report['modified']
    assert 'import foo' in target.read_text()