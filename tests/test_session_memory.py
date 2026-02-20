"""Tests for session approval memory (ROADMAP 2.7.5)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.storage import SessionMemory, operation_key


def test_session_memory_records_and_reads_rejections(tmp_path: Path) -> None:
    mem = SessionMemory(tmp_path)
    approved = [{"target_file": "a.py", "kind": "remove_unused_import", "params": {"location": "f"}}]
    rejected = [{"target_file": "b.py", "kind": "split_module", "params": {"location": "g"}}]
    mem.record("s1", approved=approved, rejected=rejected)
    keys = mem.rejected_keys("s1")
    assert operation_key(rejected[0]) in keys
    assert operation_key(approved[0]) not in keys


def test_campaign_memory_skips_rejected_from_any_session(tmp_path: Path) -> None:
    """Rejected ops in one session are skipped in next run via campaign_keys_to_skip."""
    mem = SessionMemory(tmp_path)
    rejected = [{"target_file": "x.py", "kind": "extract_class", "params": {"location": ""}}]
    mem.record("s1", approved=[], rejected=rejected)
    skip = mem.campaign_keys_to_skip()
    assert operation_key(rejected[0]) in skip


def test_campaign_memory_skips_repeated_verify_failures(tmp_path: Path) -> None:
    """Ops that failed verify 2+ times are in campaign_keys_to_skip."""
    mem = SessionMemory(tmp_path)
    ops = [{"target_file": "y.py", "kind": "split_module", "params": {}}]
    mem.record_verify_failure(ops)
    mem.record_verify_failure(ops)
    skip = mem.campaign_keys_to_skip()
    assert operation_key(ops[0]) in skip


def test_campaign_memory_single_verify_failure_not_skipped(tmp_path: Path) -> None:
    """Single verify failure does not add to skip (need 2+)."""
    mem = SessionMemory(tmp_path)
    ops = [{"target_file": "z.py", "kind": "split_module", "params": {}}]
    mem.record_verify_failure(ops)
    skip = mem.campaign_keys_to_skip()
    assert operation_key(ops[0]) not in skip
