from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.analysis.graph import ProjectGraph
from eurika.analysis.self_map import build_graph_from_self_map


def test_build_graph_from_self_map_via_package(tmp_path: Path) -> None:
    self_map = tmp_path / "self_map.json"
    self_map.write_text(
        '{"modules":[{"path":"a.py"},{"path":"b.py"}],"dependencies":{"a.py":["b"],"b.py":[]}}',
        encoding="utf-8",
    )

    graph = build_graph_from_self_map(self_map)
    assert isinstance(graph, ProjectGraph)
    fan = graph.fan_in_out()
    assert fan["a.py"][1] == 1
    assert fan["b.py"][0] == 1
