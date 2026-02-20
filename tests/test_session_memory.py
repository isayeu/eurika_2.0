"""Tests for session approval memory."""

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
