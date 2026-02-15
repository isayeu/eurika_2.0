"""Tests for eurika.refactor.extract_class."""
from pathlib import Path

from eurika.refactor.extract_class import extract_class, suggest_extract_class


def test_suggest_extract_class_finds_god_class(tmp_path: Path) -> None:
    """suggest_extract_class returns (class_name, methods) for class with 6+ extractable methods."""
    target = tmp_path / "big.py"
    methods = "\n".join(f"    def m{i}(self): return {i}" for i in range(6))
    target.write_text(f"class Big:\n{methods}\n")
    result = suggest_extract_class(target)
    assert result is not None
    assert result[0] == "Big"
    assert len(result[1]) >= 6


def test_suggest_extract_class_returns_none_when_few_methods(tmp_path: Path) -> None:
    """suggest_extract_class returns None when class has < 6 methods."""
    target = tmp_path / "small.py"
    target.write_text("class Small:\n    def a(self): pass\n")
    assert suggest_extract_class(target) is None


def test_suggest_extract_class_returns_none_when_all_use_self(tmp_path: Path) -> None:
    """suggest_extract_class returns None when all methods use self.attr."""
    target = tmp_path / "selfy.py"
    methods = "\n".join(f"    def m{i}(self): return self.x" for i in range(6))
    target.write_text(f"class Selfy:\n{methods}\n")
    assert suggest_extract_class(target) is None


def test_extract_class_includes_module_level_constants(tmp_path: Path) -> None:
    """extract_class adds module-level constants (e.g. GOALS_FILE) used in extracted methods."""
    target = tmp_path / "goals.py"
    target.write_text("""from pathlib import Path

GOALS_FILE = Path("goals.json")

class GoalSystem:
    def __init__(self):
        self.data = self._load_data()

    def _load_data(self):
        import json
        if not GOALS_FILE.exists():
            return {}
        return json.loads(GOALS_FILE.read_text(encoding="utf-8"))

    def other(self):
        return self.data
""", encoding="utf-8")
    result = extract_class(target, "GoalSystem", ["_load_data"], target_file="goals.py")
    assert result is not None
    _, new_content, _ = result
    assert "GOALS_FILE" in new_content
    assert "Path" in new_content
