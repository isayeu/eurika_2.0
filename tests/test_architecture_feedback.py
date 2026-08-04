import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from architecture_feedback import FeedbackStore


def test_feedback_store_append_and_aggregate(tmp_path: Path) -> None:
    storage = tmp_path / "architecture_feedback.json"
    store = FeedbackStore(storage_path=storage)

    project_root = tmp_path / "proj"
    project_root.mkdir()

    store.append(project_root=project_root, action="explain_risk", outcome="accepted", target="foo.py")
    store.append(project_root=project_root, action="explain_risk", outcome="rejected", target="bar.py")
    store.append(project_root=project_root, action="summarize_evolution", outcome="accepted")

    # Ensure file written and can be reloaded.
    assert storage.exists()
    raw = json.loads(storage.read_text(encoding="utf-8"))
    assert "feedback" in raw
    assert len(raw["feedback"]) == 3

    # Recreate store from disk and check aggregation.
    store2 = FeedbackStore(storage_path=storage)
    stats = store2.aggregate_by_action()

    assert stats["explain_risk"]["accepted"] == 1
    assert stats["explain_risk"]["rejected"] == 1
    assert stats["summarize_evolution"]["accepted"] == 1

