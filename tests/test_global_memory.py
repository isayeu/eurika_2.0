"""Tests for cross-project memory (ROADMAP 3.0.2)."""
import os
from pathlib import Path

def test_get_global_memory_root_default() -> None:
    """Default is ~/.eurika when env not set."""
    from eurika.storage.global_memory import get_global_memory_root
    old = os.environ.pop('EURIKA_GLOBAL_MEMORY', None)
    old_disable = os.environ.pop('EURIKA_DISABLE_GLOBAL_MEMORY', None)
    try:
        root = get_global_memory_root()
        assert root is not None
        assert root.name == '.eurika'
        assert str(root).endswith('.eurika')
    finally:
        if old is not None:
            os.environ['EURIKA_GLOBAL_MEMORY'] = old
        if old_disable is not None:
            os.environ['EURIKA_DISABLE_GLOBAL_MEMORY'] = old_disable

def test_get_global_memory_root_disabled() -> None:
    """EURIKA_DISABLE_GLOBAL_MEMORY=1 returns None."""
    from eurika.storage.global_memory import get_global_memory_root
    os.environ['EURIKA_DISABLE_GLOBAL_MEMORY'] = '1'
    try:
        assert get_global_memory_root() is None
    finally:
        del os.environ['EURIKA_DISABLE_GLOBAL_MEMORY']

def test_merge_learning_stats() -> None:
    """Merge sums total/success/fail per key."""
    from eurika.storage.global_memory import merge_learning_stats
    local = {'a|b': {'total': 5, 'success': 2, 'fail': 3}}
    global_s = {'a|b': {'total': 3, 'success': 1, 'fail': 2}, 'c|d': {'total': 1, 'success': 0, 'fail': 1}}
    merged = merge_learning_stats(local, global_s)
    assert merged['a|b'] == {'total': 8, 'success': 3, 'fail': 5}
    assert merged['c|d'] == {'total': 1, 'success': 0, 'fail': 1}

def test_append_and_aggregate_global(tmp_path: Path) -> None:
    """Append learn to global store and aggregate (with custom dir)."""
    from eurika.storage.global_memory import append_learn_to_global, aggregate_global_by_smell_action, get_merged_learning_stats
    os.environ['EURIKA_GLOBAL_MEMORY'] = str(tmp_path)
    try:
        append_learn_to_global(project_root=Path('/proj/a'), modules=['foo.py'], operations=[{'kind': 'remove_unused_import', 'smell_type': 'unknown', 'target_file': 'foo.py'}], risks=[], verify_success=True)
        stats = aggregate_global_by_smell_action()
        assert 'unknown|remove_unused_import' in stats
        assert stats['unknown|remove_unused_import']['total'] == 1
        assert stats['unknown|remove_unused_import']['success'] == 1
        local_root = tmp_path / 'local_proj'
        local_root.mkdir()
        merged = get_merged_learning_stats(local_root)
        assert 'unknown|remove_unused_import' in merged
        assert merged['unknown|remove_unused_import']['total'] >= 1
    finally:
        del os.environ['EURIKA_GLOBAL_MEMORY']

def test_append_noop_when_disabled(tmp_path: Path) -> None:
    """append_learn_to_global is no-op when global memory disabled."""
    from eurika.storage.global_memory import append_learn_to_global, aggregate_global_by_smell_action
    os.environ['EURIKA_DISABLE_GLOBAL_MEMORY'] = '1'
    try:
        append_learn_to_global(project_root=tmp_path, modules=['x.py'], operations=[], risks=[], verify_success=True)
        assert aggregate_global_by_smell_action() == {}
    finally:
        del os.environ['EURIKA_DISABLE_GLOBAL_MEMORY']