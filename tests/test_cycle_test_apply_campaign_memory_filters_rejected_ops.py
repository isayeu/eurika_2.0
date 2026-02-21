"""Extracted from parent module to reduce complexity."""

from pathlib import Path

def test_apply_campaign_memory_filters_rejected_ops(tmp_path: Path) -> None:
    """apply_campaign_memory skips ops rejected in prior sessions."""
    from eurika.storage import SessionMemory, operation_key
    from cli.orchestration.prepare import apply_campaign_memory
    mem = SessionMemory(tmp_path)
    rejected = [{'target_file': 'foo.py', 'kind': 'split_module', 'params': {'location': ''}}]
    mem.record('prior', approved=[], rejected=rejected)
    ops = [{'target_file': 'foo.py', 'kind': 'split_module', 'params': {'location': ''}}, {'target_file': 'bar.py', 'kind': 'remove_unused_import', 'params': {}}]
    patch_plan = {'operations': ops}
    out_plan, out_ops, skipped = apply_campaign_memory(tmp_path, patch_plan, ops)
    assert len(out_ops) == 1
    assert out_ops[0].get('target_file') == 'bar.py'
    assert len(skipped) == 1
    assert operation_key(skipped[0]) == operation_key(rejected[0])
