"""Integration tests for Human-in-the-loop CLI (ROADMAP 2.7.6)."""
import sys
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from cli.orchestrator import _select_hybrid_operations, run_fix_cycle

def test_hybrid_non_interactive_approves_all_without_prompting() -> None:
    """With non_interactive=True, all ops approved, input() never called."""
    ops = [{'target_file': 'a.py', 'kind': 'split_module', 'explainability': {'risk': 'high'}}, {'target_file': 'b.py', 'kind': 'remove_unused_import', 'explainability': {'risk': 'low'}}]
    approved, rejected = _select_hybrid_operations(ops, quiet=False, non_interactive=True)
    assert approved == ops
    assert rejected == []

def test_hybrid_non_interactive_deterministic_no_stdin() -> None:
    """non_interactive with empty stdin (CI pipe) behaves deterministically."""
    ops = [{'target_file': 'x.py', 'kind': 'refactor_code_smell'}]
    with patch('sys.stdin.isatty', return_value=False):
        approved, rejected = _select_hybrid_operations(ops, quiet=False, non_interactive=False)
    assert approved == ops
    assert rejected == []

def test_hybrid_interactive_approve_reject_mocked() -> None:
    """Mocked input: a, r produces correct approved/rejected split."""
    ops = [{'target_file': 'a.py', 'kind': 'split_module'}, {'target_file': 'b.py', 'kind': 'remove_unused_import'}]
    with patch.object(sys.stdin, 'isatty', return_value=True), patch('builtins.input', side_effect=['a', 'r']):
        approved, rejected = _select_hybrid_operations(ops, quiet=False, non_interactive=False)
    assert len(approved) == 1
    assert approved[0]['target_file'] == 'a.py'
    assert len(rejected) == 1
    assert rejected[0]['target_file'] == 'b.py'

def test_hybrid_interactive_all_approve_mocked() -> None:
    """Mocked input: A approves all remaining."""
    ops = [{'target_file': 'a.py', 'kind': 'x'}, {'target_file': 'b.py', 'kind': 'y'}]
    with patch.object(sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value='A'):
        approved, rejected = _select_hybrid_operations(ops, quiet=False, non_interactive=False)
    assert len(approved) == 2
    assert rejected == []

def test_hybrid_interactive_reject_rest_mocked() -> None:
    """Mocked input: r, R rejects first and rest."""
    ops = [{'target_file': 'a.py', 'kind': 'x'}, {'target_file': 'b.py', 'kind': 'y'}, {'target_file': 'c.py', 'kind': 'z'}]
    with patch.object(sys.stdin, 'isatty', return_value=True), patch('builtins.input', side_effect=['r', 'R']):
        approved, rejected = _select_hybrid_operations(ops, quiet=False, non_interactive=False)
    assert approved == []
    assert len(rejected) == 3

def test_fix_hybrid_non_interactive_ci_no_hang(tmp_path: Path) -> None:
    """eurika fix with hybrid + non-interactive runs without stdin (CI scenario)."""
    (tmp_path / 'foo.py').write_text('x = 1\n')
    from unittest.mock import MagicMock
    with patch('cli.orchestrator._fix_cycle_deps') as mock_deps:
        mock_deps.return_value = {'run_scan': lambda *a: 0}
        with patch('cli.orchestrator._prepare_fix_cycle_operations') as mock_prep:
            result = MagicMock()
            result.output = {'policy_decisions': []}
            ops = [{'target_file': 'foo.py', 'kind': 'remove_unused_import', 'explainability': {'risk': 'low'}}]
            mock_prep.return_value = (None, result, {'operations': ops}, ops)
            out = run_fix_cycle(tmp_path, runtime_mode='hybrid', non_interactive=True, dry_run=True, quiet=True)
    assert 'report' in out or 'operations' in out
    assert out.get('dry_run') is True