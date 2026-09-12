"""Static project-local call graph (RV11)."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.analysis.call_graph import build_call_graph
from eurika.analysis.call_graph_eval import (
    EXPECTED_EDGES,
    FORBIDDEN_EDGES,
    attach_call_graph_diagnostics,
    evaluate_call_graph_accuracy,
    score_call_edges,
)
from eurika.api.architecture import get_graph


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_call_graph_resolves_local_imported_and_method_calls(tmp_path: Path) -> None:
    _write(
        tmp_path / "helpers.py",
        "def external(value):\n    return value\n",
    )
    _write(
        tmp_path / "main.py",
        "from helpers import external as imported\n\n"
        "def local():\n    return 1\n\n"
        "def run(value):\n    local()\n    result = imported(value)\n    return result\n\n"
        "class Service:\n"
        "    def first(self):\n        self.second()\n\n"
        "    def second(self):\n        return 2\n",
    )

    graph = build_call_graph(tmp_path)

    assert ("main.py:run", "main.py:local") in graph.edges
    assert ("main.py:run", "helpers.py:external") in graph.edges
    assert ("main.py:Service.first", "main.py:Service.second") in graph.edges
    assert (
        "main.py:run:param:value",
        "helpers.py:external:param:value",
        "argument",
    ) in graph.data_flow.edges
    assert (
        "helpers.py:external:param:value",
        "helpers.py:external:return",
        "return",
    ) in graph.data_flow.edges
    assert (
        "helpers.py:external:return",
        "main.py:run:local:result",
        "assignment",
    ) in graph.data_flow.edges
    assert (
        "main.py:run:local:result",
        "main.py:run:return",
        "return",
    ) in graph.data_flow.edges
    assert graph.parse_errors == []


def test_call_graph_ignores_external_and_reports_parse_errors(tmp_path: Path) -> None:
    _write(tmp_path / "main.py", "import os\n\ndef run():\n    os.getcwd()\n")
    _write(tmp_path / "broken.py", "def nope(:\n")

    graph = build_call_graph(tmp_path)

    assert graph.edges == set()
    assert graph.parse_errors == ["broken.py: SyntaxError"]


def test_api_graph_exposes_call_graph_without_replacing_import_graph(tmp_path: Path) -> None:
    _write(tmp_path / "a.py", "def run():\n    return helper()\n\ndef helper():\n    return 1\n")
    (tmp_path / "self_map.json").write_text(
        json.dumps({"modules": [{"path": "a.py"}], "dependencies": {}}),
        encoding="utf-8",
    )

    payload = get_graph(tmp_path, include_calls=True)

    assert payload["nodes"][0]["id"] == "a.py"
    assert {"from": "a.py:run", "to": "a.py:helper"} in payload["call_graph"]["edges"]
    assert payload["call_graph"]["data_flow"]["node_format"].startswith("<file>:<function>")
    diag = payload["call_graph"]["diagnostics"]
    assert diag["read_only"] is True
    assert diag["planner_attached"] is False
    assert diag["cost"]["edges"] >= 1
    assert diag["accuracy"]["recall"] == 1.0
    assert diag["accuracy"]["false_resolutions"] == 0


def test_call_graph_eval_scores_labeled_fixture() -> None:
    accuracy = evaluate_call_graph_accuracy(use_cache=False)
    assert accuracy["recall"] == 1.0
    assert accuracy["precision_labeled"] == 1.0
    assert accuracy["found_expected_n"] == len(EXPECTED_EDGES)
    assert accuracy["false_resolutions"] == 0
    assert accuracy["missing"] == []
    assert accuracy["elapsed_ms"] >= 0


def test_call_graph_eval_treats_forbidden_resolution_as_false_hit() -> None:
    found = set(EXPECTED_EDGES) | {next(iter(FORBIDDEN_EDGES))}
    scored = score_call_edges(found)
    assert scored["false_resolutions"] == 1
    assert scored["precision_labeled"] < 1.0
    assert scored["recall"] == 1.0


def test_call_graph_diagnostics_are_project_cost_not_import_graph(tmp_path: Path) -> None:
    _write(tmp_path / "only.py", "def a():\n    return b()\n\ndef b():\n    return 1\n")
    payload = attach_call_graph_diagnostics(tmp_path)
    assert payload["diagnostics"]["cost"]["nodes"] == 2
    assert payload["diagnostics"]["cost"]["edges"] == 1
    assert payload["diagnostics"]["planner_attached"] is False


def test_call_graph_not_imported_by_planner_or_policy() -> None:
    roots = [
        Path(__file__).resolve().parents[1] / "eurika" / "orchestration",
        Path(__file__).resolve().parents[1] / "eurika" / "reasoning",
        Path(__file__).resolve().parents[1] / "eurika" / "api" / "planning_coupling.py",
        Path(__file__).resolve().parents[1] / "eurika" / "api" / "critic_coupling.py",
    ]
    hits: list[str] = []
    for root in roots:
        files = [root] if root.is_file() else list(root.rglob("*.py"))
        for path in files:
            text = path.read_text(encoding="utf-8")
            if "call_graph" in text:
                hits.append(str(path))
    assert hits == []
