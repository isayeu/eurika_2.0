"""«приступай» / «что дальше» follow DEVELOPMENT.md, not a frozen VISION A1 slogan."""
from __future__ import annotations

from pathlib import Path

from eurika.api.chat_utils import (
    format_continue_dev_brief,
    format_docs_plan_fallback,
    format_market_dev_brief,
    format_roadmap_next_steps,
)


def _write_dev(root: Path, focus: str) -> None:
    docs = root / "docs"
    docs.mkdir(parents=True)
    docs.joinpath("DEVELOPMENT.md").write_text(
        f"# Разработка\n\n## Текущий фокус\n\n{focus}\n\n## Порядок\n\n1. test.\n",
        encoding="utf-8",
    )
    docs.joinpath("VISION.md").write_text(
        "# Vision\n\n## Продуктовый горизонт после окна (не порядок разработки)\n\n"
        "### A. Продукт / UX\n1. Chat-first.\n",
        encoding="utf-8",
    )


def test_continue_dev_brief_reads_development_focus(tmp_path: Path) -> None:
    _write_dev(tmp_path, "1. **RV11 diagnostics only.** Do not attach planner.")
    text = format_continue_dev_brief(tmp_path)
    assert "DEVELOPMENT.md" in text
    assert "RV11 diagnostics only" in text
    assert "VISION A1" not in text
    assert "мелкий chat UX" not in text


def test_development_focus_leads_with_h5() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    from eurika.api.chat_utils import format_roadmap_next_steps

    text = format_roadmap_next_steps(root)
    assert "CR-H H5" in text
    rv11 = text.find("RV11")
    if rv11 != -1:
        assert text.find("CR-H H5") < rv11


def test_roadmap_next_steps_prefers_development(tmp_path: Path) -> None:
    _write_dev(tmp_path, "1. Host admin read-only.")
    text = format_roadmap_next_steps(tmp_path)
    assert "DEVELOPMENT.md" in text
    assert "Host admin read-only" in text
    assert "мелкий chat UX / goals polish (A1)" not in text
    assert "Market entry" in text


def test_market_plan_fallback_is_freeze_not_file_inventory(tmp_path: Path) -> None:
    _write_dev(tmp_path, "1. **CR-H H5 Thinking.**")
    (tmp_path / "docs" / "VISION.md").write_text(
        "# Vision\n\n### B. Market paper (по статистике journal)\n"
        "15. **Метки всё ещё частично свои же.**\n",
        encoding="utf-8",
    )
    text = format_docs_plan_fallback(tmp_path, "какие планы по развитию маркета?")
    assert "From docs:" not in text
    assert "freeze" in text.lower()
    assert "Метки всё ещё частично свои же" in text
    assert format_market_dev_brief(tmp_path).startswith("## Планы Market")
    coding = format_docs_plan_fallback(tmp_path, "что дальше?")
    assert "CR-H H5" in coding
