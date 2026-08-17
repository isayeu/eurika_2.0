from __future__ import annotations

import json
from pathlib import Path

from eurika.agent.panels import PanelService
from eurika.agent.workspace import WorkspaceTools
from eurika.ml.root import _source_checkout_root, resolve_market_root


def test_market_root_honors_dedicated_environment(
    tmp_path: Path, monkeypatch
) -> None:
    expected = tmp_path / "market-home"
    monkeypatch.setenv("EURIKA_MARKET_ROOT", str(expected))

    assert resolve_market_root() == expected.resolve()


def test_source_checkout_detection_rejects_installed_package_layout(tmp_path: Path) -> None:
    installed_module = tmp_path / "site-packages" / "eurika" / "ml" / "root.py"
    installed_module.parent.mkdir(parents=True)
    installed_module.touch()

    assert _source_checkout_root(installed_module) is None


def test_source_checkout_detection_requires_repository_markers(tmp_path: Path) -> None:
    module = tmp_path / "checkout" / "eurika" / "ml" / "root.py"
    module.parent.mkdir(parents=True)
    module.touch()
    (tmp_path / "checkout" / ".git").mkdir()
    (tmp_path / "checkout" / "pyproject.toml").touch()

    assert _source_checkout_root(module) == (tmp_path / "checkout").resolve()


def test_desktop_market_panel_ignores_coding_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    coding_workspace = tmp_path / "external-project"
    market_root = tmp_path / "eurika-product"
    coding_workspace.mkdir()
    ml_root = market_root / ".eurika" / "ml"
    ml_root.mkdir(parents=True)
    (ml_root / "paper_portfolio.json").write_text(
        json.dumps({"equity_usdt": 1234.5}),
        encoding="utf-8",
    )
    monkeypatch.setenv("EURIKA_MARKET_ROOT", str(market_root))

    state = PanelService(WorkspaceTools(coding_workspace)).state("market")

    assert state["data"]["portfolio"]["equity_usdt"] == 1234.5
    assert not (coding_workspace / ".eurika" / "ml").exists()
