"""Tests for patch_apply module."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from patch_apply import apply_patch_plan, list_backups, restore_backup

def test_apply_patch_plan_dry_run(tmp_path: Path) -> None:
    """Dry-run does not modify files."""
    (tmp_path / 'a.py').write_text('print(1)\n')
    plan = {'project_root': str(tmp_path), 'operations': [{'target_file': 'a.py', 'kind': 'refactor_module', 'description': 'refactor a', 'diff': '# TODO: refactor\n'}]}
    report = apply_patch_plan(tmp_path, plan, dry_run=True)
    assert report['dry_run'] is True
    assert report['modified'] == ['a.py']
    assert report['errors'] == []
    assert (tmp_path / 'a.py').read_text() == 'print(1)\n'

def test_apply_patch_plan_apply(tmp_path: Path) -> None:
    """With dry_run=False, diff is appended to target file."""
    (tmp_path / 'b.py').write_text('x = 1\n')
    plan = {'project_root': str(tmp_path), 'operations': [{'target_file': 'b.py', 'kind': 'refactor_module', 'description': 'refactor b', 'diff': '# TODO: refactor b\n'}]}
    report = apply_patch_plan(tmp_path, plan, dry_run=False)
    assert report['dry_run'] is False
    assert report['modified'] == ['b.py']
    assert report['errors'] == []
    content = (tmp_path / 'b.py').read_text()
    assert content == 'x = 1\n\n# TODO: refactor b\n'

def test_apply_patch_plan_dedupes_modified(tmp_path: Path) -> None:
    """Same file modified by multiple ops appears once in report (e.g. clean_imports + refactor)."""
    (tmp_path / "a.py").write_text("import os\nx = 1\n")
    plan = {
        "operations": [
            {"target_file": "a.py", "kind": "remove_unused_import", "description": "clean", "diff": "", "smell_type": None},
            {"target_file": "a.py", "kind": "refactor_module", "description": "hint", "diff": "# TODO: refactor\n"},
        ],
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert report["modified"] == ["a.py"]
    assert report["errors"] == []


def test_apply_patch_plan_skips_missing(tmp_path: Path) -> None:
    """Missing target file is skipped."""
    plan = {'project_root': str(tmp_path), 'operations': [{'target_file': 'nonexistent.py', 'kind': 'refactor_module', 'description': 'n/a', 'diff': '# TODO\n'}]}
    report = apply_patch_plan(tmp_path, plan, dry_run=False)
    assert report['modified'] == []
    assert report['skipped'] == ['nonexistent.py']
    assert report['errors'] == []

def test_apply_patch_plan_creates_backup(tmp_path: Path) -> None:
    """With backup=True, original file is copied to .eurika_backups/<run_id>/ before apply."""
    (tmp_path / 'c.py').write_text('original\n')
    plan = {'project_root': str(tmp_path), 'operations': [{'target_file': 'c.py', 'kind': 'refactor_module', 'description': 'n/a', 'diff': '# appended\n'}]}
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=True)
    assert report['dry_run'] is False
    assert report['modified'] == ['c.py']
    assert report['errors'] == []
    assert report['backup_dir'] is not None
    backup_dir = Path(report['backup_dir'])
    assert backup_dir.is_dir()
    backup_file = backup_dir / 'c.py'
    assert backup_file.read_text() == 'original\n'
    assert (tmp_path / 'c.py').read_text() == 'original\n\n# appended\n'

def test_list_backups_empty(tmp_path: Path) -> None:
    """No backup dir yields empty run_ids."""
    info = list_backups(tmp_path)
    assert info['run_ids'] == []
    assert '.eurika_backups' in info['backup_dir']

def test_apply_patch_plan_skips_already_present(tmp_path: Path) -> None:
    """If diff is already in file, skip appending (avoid duplicate comments)."""
    (tmp_path / 'd.py').write_text('code\n\n# TODO: refactor\n')
    plan = {'project_root': str(tmp_path), 'operations': [{'target_file': 'd.py', 'kind': 'refactor_module', 'description': 'n/a', 'diff': '# TODO: refactor\n'}]}
    report = apply_patch_plan(tmp_path, plan, dry_run=False)
    assert report['modified'] == []
    assert report['skipped'] == ['d.py']
    assert report['errors'] == []
    assert (tmp_path / 'd.py').read_text() == 'code\n\n# TODO: refactor\n'

def test_apply_refactor_module_produces_real_split(tmp_path: Path) -> None:
    """refactor_module tries split_module chain; extracts when possible instead of TODO."""
    (tmp_path / "mod.py").write_text(
        '"""Module with standalone function."""\n'
        "import json\n\n"
        "def process(x):\n"
        "    return json.loads(x)\n"
    )
    plan = {
        "operations": [
            {
                "target_file": "mod.py",
                "kind": "refactor_module",
                "description": "Refactor",
                "diff": "# TODO: refactor mod.py\n",
            }
        ]
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert "mod.py" in report["modified"]
    extracted = next((f for f in report["modified"] if f != "mod.py"), None)
    assert extracted is not None, f"Expected extracted file, got {report['modified']}"
    assert (tmp_path / extracted).exists()
    assert "def process" in (tmp_path / extracted).read_text()
    assert "# TODO: refactor" not in (tmp_path / "mod.py").read_text()


def test_apply_refactor_code_smell_appends_todo(tmp_path: Path) -> None:
    """refactor_code_smell falls through to default; appends TODO comment."""
    (tmp_path / "m.py").write_text("def foo():\n    pass\n")
    plan = {
        "operations": [
            {
                "target_file": "m.py",
                "kind": "refactor_code_smell",
                "description": "Refactor long_function",
                "diff": "\n# TODO (eurika): refactor long_function 'foo' — consider extracting helper\n",
                "smell_type": "long_function",
                "params": {"location": "foo", "metric": 55},
            }
        ]
    }
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert report["modified"] == ["m.py"]
    content = (tmp_path / "m.py").read_text()
    assert "TODO (eurika): refactor long_function 'foo'" in content


def test_apply_patch_plan_skips_when_marker_exists(tmp_path: Path) -> None:
    """If # TODO: Refactor {target} marker exists, skip refactor_module (avoid duplicates when diff varies)."""
    (tmp_path / 'e.py').write_text('code\n\n# TODO: Refactor e.py (god_module -> refactor_module)\n# Suggested steps:\n# - old hint\n')
    plan = {'operations': [{'target_file': 'e.py', 'kind': 'refactor_module', 'description': 'n/a', 'diff': '# TODO: Refactor e.py (god_module -> refactor_module)\n# Suggested steps:\n# - new hint\n'}]}
    report = apply_patch_plan(tmp_path, plan, dry_run=False)
    assert report['modified'] == []
    assert report['skipped'] == ['e.py']
    content = (tmp_path / 'e.py').read_text()
    assert content.count('# TODO: Refactor e.py') == 1


def test_apply_extract_nested_function(tmp_path: Path) -> None:
    """extract_nested_function: real extraction when long function has self-contained nested."""
    code = (
        "def long_foo():\n"
        "    x = 1\n"
        "    def inner():\n"
        "        return 99\n"
        "    return inner()\n"
    )
    (tmp_path / "m.py").write_text(code)
    plan = {"operations": [{
        "target_file": "m.py",
        "kind": "extract_nested_function",
        "params": {"location": "long_foo", "nested_function_name": "inner"},
    }]}
    report = apply_patch_plan(tmp_path, plan, dry_run=False, backup=False)
    assert report["modified"] == ["m.py"]
    content = (tmp_path / "m.py").read_text()
    assert "def inner():" in content
    assert content.index("def inner():") < content.index("def long_foo():")
    assert "return inner()" in content


def test_apply_patch_plan_refactor_code_smell_not_skipped_by_architectural_todo(tmp_path: Path) -> None:
    """refactor_code_smell is applied even when file has architectural TODO (different op types)."""
    (tmp_path / 'x.py').write_text('def long_fn(): pass\n\n# TODO: Refactor x.py (god_module)\n')
    plan = {'operations': [{
        'target_file': 'x.py',
        'kind': 'refactor_code_smell',
        'diff': '\n# TODO (eurika): refactor long_function \'long_fn\' — consider extracting helper\n',
    }]}
    report = apply_patch_plan(tmp_path, plan, dry_run=False)
    assert report['modified'] == ['x.py']
    content = (tmp_path / 'x.py').read_text()
    assert 'TODO (eurika): refactor long_function' in content


def test_restore_backup(tmp_path: Path) -> None:
    """Restore reverts files from backup run."""
    (tmp_path / 'f.py').write_text('v1\n')
    plan = {'project_root': str(tmp_path), 'operations': [{'target_file': 'f.py', 'kind': 'refactor_module', 'description': 'n/a', 'diff': '# added\n'}]}
    apply_patch_plan(tmp_path, plan, dry_run=False, backup=True)
    assert (tmp_path / 'f.py').read_text() == 'v1\n\n# added\n'
    report = restore_backup(tmp_path, run_id=None)
    assert report['errors'] == []
    assert 'f.py' in report['restored']
    assert report['run_id'] is not None
    assert (tmp_path / 'f.py').read_text() == 'v1\n'