import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_graph import ProjectGraph


def make_simple_self_map(tmp_path: Path) -> Path:
    """
    Build a tiny self_map.json:
      a.py -> b.py
      b.py -> (no deps)
      c.py -> a.py, b.py (extra leaf)
    Contains a trivial self-dependency on a, which forms a 1-node cycle.
    """
    data = {
        "modules": [
            {"path": "a.py", "lines": 10, "functions": [], "classes": []},
            {"path": "b.py", "lines": 10, "functions": [], "classes": []},
            {"path": "c.py", "lines": 10, "functions": [], "classes": []},
        ],
        "dependencies": {
            "a.py": ["a", "b"],  # a imports a, b  (self-import should be ignored at higher level)
            "c.py": ["a", "b"],
        },
        "summary": {"files": 3, "total_lines": 30},
    }
    path = tmp_path / "self_map.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_project_graph_basic_structure(tmp_path):
    self_map_path = make_simple_self_map(tmp_path)
    self_map = json.loads(self_map_path.read_text(encoding="utf-8"))

    g = ProjectGraph.from_self_map(self_map)

    # Nodes correspond to module file paths
    assert g.nodes == {"a.py", "b.py", "c.py"}

    fan = g.fan_in_out()
    # a.py depends on b.py (self-import resolved to a.py, which is allowed)
    assert fan["a.py"][1] >= 1
    # b.py has at least one incoming edge (from a or c)
    assert fan["b.py"][0] >= 1

    # Cycle detection works (self-cycle on a.py)
    cycles = g.find_cycles()
    assert ["a.py"] in cycles

