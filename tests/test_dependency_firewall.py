from __future__ import annotations

from pathlib import Path

from eurika.checks.dependency_firewall import ImportRule, collect_dependency_violations


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_collect_dependency_violations_detects_forbidden_import(tmp_path) -> None:
    _write(tmp_path / "cli" / "handler.py", "import patch_apply\n")
    violations = collect_dependency_violations(
        tmp_path,
        rules=(ImportRule(path_pattern="cli/", forbidden_imports=("patch_apply",)),),
    )
    assert len(violations) == 1
    assert violations[0].path == "cli/handler.py"
    assert violations[0].forbidden_module == "patch_apply"


def test_collect_dependency_violations_ignores_tests_and_valid_imports(tmp_path) -> None:
    _write(tmp_path / "tests" / "test_sample.py", "import patch_apply\n")
    _write(tmp_path / "eurika" / "analysis" / "ok.py", "import json\n")
    violations = collect_dependency_violations(
        tmp_path,
        rules=(ImportRule(path_pattern="eurika/analysis/", forbidden_imports=("patch_apply",)),),
    )
    assert violations == []
