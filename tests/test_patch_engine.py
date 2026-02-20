"""Tests for patch_engine (apply_patch, verify_patch, rollback_patch, apply_and_verify, list_backups)."""
from pathlib import Path
from patch_engine import (
    apply_patch,
    apply_and_verify,
    list_backups,
    rollback,
    rollback_patch,
    verify_patch,
)

def test_apply_and_verify_modifies_files(tmp_path: Path) -> None:
    """apply_and_verify applies plan and runs verify step; with passing pytest no rollback."""
    (tmp_path / 'foo.py').write_text('x = 1\n', encoding='utf-8')
    (tmp_path / 'test_foo.py').write_text('def test_ok(): pass\n', encoding='utf-8')
    plan = {'operations': [{'target_file': 'foo.py', 'diff': '# TODO: refactor (eurika)\n', 'smell_type': 'god_module', 'kind': 'refactor_module'}]}
    report = apply_and_verify(tmp_path, plan, backup=True, verify=True)
    assert report['modified'] == ['foo.py']
    assert report['errors'] == []
    assert 'verify' in report
    assert report['verify']['success'] is True
    assert 'verify_duration_ms' in report
    assert isinstance(report['verify_duration_ms'], int)
    assert (tmp_path / 'foo.py').read_text(encoding='utf-8') == 'x = 1\n\n# TODO: refactor (eurika)\n'
    assert report.get('run_id')
    assert (tmp_path / '.eurika_backups' / report['run_id'] / 'foo.py').exists()

def test_apply_and_verify_no_verify(tmp_path: Path) -> None:
    """With verify=False, no pytest run; report has verify placeholder."""
    (tmp_path / 'a.py').write_text('pass\n', encoding='utf-8')
    plan = {'operations': [{'target_file': 'a.py', 'diff': '# eurika\n', 'smell_type': 'hub', 'kind': 'split'}]}
    report = apply_and_verify(tmp_path, plan, backup=False, verify=False)
    assert report['modified'] == ['a.py']
    assert report['verify']['success'] is None
    assert report['verify_duration_ms'] == 0

def test_rollback_restores_files(tmp_path: Path) -> None:
    """rollback restores from .eurika_backups/<run_id>."""
    backup_dir = tmp_path / '.eurika_backups' / '20250101_120000'
    backup_dir.mkdir(parents=True)
    (backup_dir / 'bar.py').write_text('original\n', encoding='utf-8')
    (tmp_path / 'bar.py').write_text('modified\n', encoding='utf-8')
    result = rollback(tmp_path, run_id='20250101_120000')
    assert result['errors'] == []
    assert 'bar.py' in result['restored']
    assert (tmp_path / 'bar.py').read_text(encoding='utf-8') == 'original\n'

def test_rollback_latest_when_no_run_id(tmp_path: Path) -> None:
    """rollback with run_id=None uses latest backup dir."""
    (tmp_path / '.eurika_backups' / 'run1').mkdir(parents=True)
    (tmp_path / '.eurika_backups' / 'run1' / 'f.py').write_text('x\n', encoding='utf-8')
    (tmp_path / 'f.py').write_text('y\n', encoding='utf-8')
    result = rollback(tmp_path, run_id=None)
    assert result['errors'] == []
    assert result['run_id'] == 'run1'
    assert (tmp_path / 'f.py').read_text(encoding='utf-8') == 'x\n'

def test_list_backups_empty(tmp_path: Path) -> None:
    """list_backups returns empty list when no backups."""
    info = list_backups(tmp_path)
    assert info['run_ids'] == []
    assert '.eurika_backups' in info['backup_dir']

def test_list_backups_finds_runs(tmp_path: Path) -> None:
    """list_backups returns sorted run_ids."""
    (tmp_path / '.eurika_backups' / '20250102_000000').mkdir(parents=True)
    (tmp_path / '.eurika_backups' / '20250101_000000').mkdir(parents=True)
    info = list_backups(tmp_path)
    assert len(info['run_ids']) == 2
    assert '20250101_000000' in info['run_ids']
    assert '20250102_000000' in info['run_ids']


def test_apply_patch_only(tmp_path: Path) -> None:
    """apply_patch applies plan without running verify."""
    (tmp_path / 'z.py').write_text('a = 1\n', encoding='utf-8')
    plan = {'operations': [{'target_file': 'z.py', 'diff': '# eurika\n', 'kind': 'refactor_module'}]}
    report = apply_patch(tmp_path, plan, backup=True)
    assert report['modified'] == ['z.py']
    assert report.get('run_id')
    assert 'verify' not in report
    assert (tmp_path / 'z.py').read_text(encoding='utf-8') == 'a = 1\n\n# eurika\n'


def test_verify_patch_returns_dict(tmp_path: Path) -> None:
    """verify_patch runs pytest and returns success/returncode/stdout/stderr."""
    # Empty dir: pytest exits 5 (no tests collected) or 0 (no tests)
    out = verify_patch(tmp_path, timeout=10)
    assert 'success' in out
    assert 'returncode' in out
    assert 'stdout' in out
    assert 'stderr' in out


def test_verify_patch_custom_cmd(tmp_path: Path) -> None:
    """verify_patch with verify_cmd override runs that command instead of pytest."""
    out = verify_patch(tmp_path, timeout=10, verify_cmd="python -c \"exit(0)\"")
    assert out['success'] is True
    assert out['returncode'] == 0


def test_verify_patch_pyproject_verify_cmd(tmp_path: Path) -> None:
    """verify_patch uses [tool.eurika] verify_cmd from pyproject.toml when no override."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.eurika]\nverify_cmd = "true"\n',
        encoding="utf-8",
    )
    out = verify_patch(tmp_path, timeout=10)
    assert out['success'] is True


def test_rollback_patch_same_as_rollback(tmp_path: Path) -> None:
    """rollback_patch is equivalent to rollback."""
    (tmp_path / '.eurika_backups' / 'r1').mkdir(parents=True)
    (tmp_path / '.eurika_backups' / 'r1' / 'f.py').write_text('old\n', encoding='utf-8')
    (tmp_path / 'f.py').write_text('new\n', encoding='utf-8')
    r1 = rollback_patch(tmp_path, 'r1')
    r2 = rollback(tmp_path, 'r1')
    assert (tmp_path / 'f.py').read_text(encoding='utf-8') == 'old\n'
    assert r1.get('restored') == r2.get('restored')


def test_apply_and_verify_py_compile_fallback_when_no_tests(tmp_path: Path) -> None:
    """When pytest returns 5 (no tests) and verify_cmd=None, fallback to py_compile on modified files."""
    (tmp_path / 'foo.py').write_text('x = 1\n', encoding='utf-8')
    # No test_*.py → pytest returns 5 "no tests ran"
    plan = {
        'operations': [
            {'target_file': 'foo.py', 'diff': '\n# eurika\n', 'kind': 'refactor_module'},
        ]
    }
    report = apply_and_verify(tmp_path, plan, backup=True, verify=True, auto_rollback=True, verify_cmd=None)
    assert report['verify']['success'] is True
    assert report['verify'].get('py_compile_fallback') is True
    assert report.get('rollback') is None
    assert '# eurika' in (tmp_path / 'foo.py').read_text(encoding='utf-8')


def test_apply_and_verify_auto_rollback_on_failure(tmp_path: Path) -> None:
    """When verify fails and auto_rollback=True, files are restored."""
    (tmp_path / 'bad.py').write_text('x = 1\n', encoding='utf-8')
    (tmp_path / 'test_bad.py').write_text(
        'def test_import(): __import__("bad")\n', encoding='utf-8'
    )
    # Apply a diff that makes bad.py fail at import (syntax or runtime)
    plan = {
        'operations': [
            {
                'target_file': 'bad.py',
                'diff': '\nraise RuntimeError("eurika verify fail")\n',
                'kind': 'refactor_module',
            }
        ]
    }
    report = apply_and_verify(tmp_path, plan, backup=True, verify=True, auto_rollback=True)
    assert report['verify']['success'] is False
    assert report.get('rollback', {}).get('done') is True
    assert report.get('rollback', {}).get('trigger') == 'verify_failed'
    assert (tmp_path / 'bad.py').read_text(encoding='utf-8') == 'x = 1\n'