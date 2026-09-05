"""Tests for format_project_overview — purpose from docs, not file-type heuristics."""

from __future__ import annotations

from pathlib import Path

from eurika.api.chat_utils import format_project_overview


def test_overview_reads_readme_purpose(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Grid Bot\n\n"
        "Spot grid trading bot for Binance with inventory-first LIMIT orders.\n\n"
        "## Install\n\npip install -r requirements.txt\n",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        '"""Fallback doc."""\n'
        'import argparse\n'
        'parser = argparse.ArgumentParser(description="should not win over README")\n',
        encoding="utf-8",
    )
    text = format_project_overview(tmp_path)
    assert "Grid Bot" in text or "grid trading" in text.lower()
    assert "inventory-first" in text.lower() or "LIMIT" in text
    assert "Python-приложение" not in text
    assert "По типам:" not in text


def test_overview_entry_point_when_no_readme(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text(
        "import argparse\n"
        'parser = argparse.ArgumentParser(description="Binance spot LIMIT grid bot")\n',
        encoding="utf-8",
    )
    text = format_project_overview(tmp_path)
    assert "Binance spot LIMIT grid" in text
    assert "main.py" in text


def test_overview_structure_lists_packages(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# X\n\nDoes things.\n", encoding="utf-8")
    (tmp_path / "grid").mkdir()
    (tmp_path / "grid" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "grid" / "engine.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "exchange").mkdir()
    (tmp_path / "exchange" / "broker.py").write_text("x=1\n", encoding="utf-8")
    text = format_project_overview(tmp_path)
    assert "`grid/`" in text
    assert "engine.py" in text
    assert "`exchange/`" in text


def test_overview_with_self_map(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# App\n\nMy app does work.\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "self_map.json").write_text(
        '{"modules":[{"path":"app.py","lines":1,"functions":[],"classes":[]}],'
        '"dependencies":{},"summary":{"files":1,"total_lines":1}}',
        encoding="utf-8",
    )
    text = format_project_overview(tmp_path)
    assert "1 модул" in text
    assert "My app does work" in text
