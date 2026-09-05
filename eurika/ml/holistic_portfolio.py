"""Unified cash pool for holistic portfolio (trade + earn).

Single bankroll (~1000 USDT): ``cash_free`` funds earn deposits and trade margin.
Sub-books (assistant_*, earn_positions) hold detail; holistic is the allocator.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from eurika.ml.market_store import ml_root
from eurika.ml.paper_portfolio import DEFAULT_START_EQUITY_USDT

DEFAULT_HOLISTIC_START_USDT = float(DEFAULT_START_EQUITY_USDT)


def _now_ms() -> int:
    return int(time.time() * 1000)


def holistic_portfolio_path(root: str | Path) -> Path:
    return ml_root(root) / "holistic_portfolio.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_holistic() -> dict[str, Any]:
    eq = float(DEFAULT_HOLISTIC_START_USDT)
    now = _now_ms()
    return {
        "version": 1,
        "start_equity_usdt": eq,
        "equity_usdt": eq,
        "cash_free_usdt": eq,
        "earn_principal_usdt": 0.0,
        "earn_accrued_usdt": 0.0,
        "trade_margin_usdt": 0.0,
        "trade_realized_pnl_usdt": 0.0,
        "note": "unified portfolio cash; trade+earn share one pool",
        "created_ms": now,
        "updated_ms": now,
        "last_accrue_ms": now,
        "migrated_legacy": False,
    }


def load_holistic(root: str | Path) -> dict[str, Any]:
    data = _read_json(holistic_portfolio_path(root), None)
    if not isinstance(data, dict):
        return default_holistic()
    out = default_holistic()
    out.update(
        {
            k: data[k]
            for k in data
            if k in out
            or k in ("version", "note", "created_ms", "updated_ms", "last_accrue_ms", "migrated_legacy")
        }
    )
    return out


def save_holistic(root: str | Path, port: Mapping[str, Any]) -> None:
    blob = dict(port)
    blob["updated_ms"] = _now_ms()
    _write_json(holistic_portfolio_path(root), blob)


def _sum_earn_positions(root: str | Path) -> tuple[float, float]:
    from eurika.ml.earn_monitor import load_earn_positions

    principal = 0.0
    accrued = 0.0
    for pos in load_earn_positions(root):
        principal += float(pos.get("amount") or 0.0)
        accrued += float(pos.get("accrued_usdt") or 0.0)
    return principal, accrued


def _trade_margin_from_book(root: str | Path) -> float:
    from eurika.ml.assistant_paper import load_opens, load_pending

    total = 0.0
    for row in list(load_opens(root)) + list(load_pending(root)):
        total += float(row.get("margin_usdt") or 0.0)
    return total


def total_equity(port: Mapping[str, Any]) -> float:
    return (
        float(port.get("cash_free_usdt") or 0.0)
        + float(port.get("earn_principal_usdt") or 0.0)
        + float(port.get("earn_accrued_usdt") or 0.0)
        + float(port.get("trade_margin_usdt") or 0.0)
    )


def migrate_legacy_if_needed(root: str | Path) -> bool:
    """Consolidate separate earn/trade books into one holistic pool (once)."""
    path = holistic_portfolio_path(root)
    if path.is_file():
        return False
    from eurika.ml.assistant_paper import assistant_portfolio_path, load_portfolio
    from eurika.ml.earn_monitor import earn_portfolio_path, load_earn_portfolio

    h = default_holistic()
    start = float(DEFAULT_HOLISTIC_START_USDT)
    earn_p = load_earn_portfolio(root) if earn_portfolio_path(root).is_file() else {}
    trade_p = load_portfolio(root) if assistant_portfolio_path(root).is_file() else {}
    earn_principal = float(earn_p.get("principal_usdt") or 0.0)
    earn_accrued = float(earn_p.get("accrued_usdt") or 0.0)
    trade_margin = _trade_margin_from_book(root)
    trade_realized = float(trade_p.get("realized_pnl_usdt") or 0.0)
    h["earn_principal_usdt"] = earn_principal
    h["earn_accrued_usdt"] = earn_accrued
    h["trade_margin_usdt"] = trade_margin
    h["trade_realized_pnl_usdt"] = trade_realized
    # Margin locked in opens/pending is not free cash — subtract it from the pool.
    h["cash_free_usdt"] = max(
        0.0,
        start - earn_principal - trade_margin + trade_realized,
    )
    if earn_portfolio_path(root).is_file() or assistant_portfolio_path(root).is_file():
        h["migrated_legacy"] = True
    h["equity_usdt"] = total_equity(h)
    save_holistic(root, h)
    return True


def _repair_legacy_margin_double_count(h: dict[str, Any]) -> bool:
    """One-time fix: legacy migration counted open margin in both cash and trade_margin."""
    if not h.get("migrated_legacy") or h.get("legacy_margin_repaired"):
        return False
    start = float(h.get("start_equity_usdt") or DEFAULT_HOLISTIC_START_USDT)
    realized = float(h.get("trade_realized_pnl_usdt") or 0.0)
    accrued = float(h.get("earn_accrued_usdt") or 0.0)
    expected = start + realized + accrued
    actual = total_equity(h)
    excess = actual - expected
    if excess <= 0.001:
        h["legacy_margin_repaired"] = True
        return False
    h["cash_free_usdt"] = max(0.0, float(h.get("cash_free_usdt") or 0.0) - excess)
    h["equity_usdt"] = total_equity(h)
    h["legacy_margin_repaired"] = True
    h["legacy_margin_repair_usdt"] = round(excess, 6)
    return True


def ensure_holistic(root: str | Path) -> dict[str, Any]:
    migrate_legacy_if_needed(root)
    path = holistic_portfolio_path(root)
    if not path.is_file():
        port = default_holistic()
        save_holistic(root, port)
        return port
    return load_holistic(root)


def reconcile_holistic(root: str | Path) -> dict[str, Any]:
    """Sync holistic totals from earn positions + trade book."""
    h = ensure_holistic(root)
    ep, ea = _sum_earn_positions(root)
    tm = _trade_margin_from_book(root)
    old_tm = float(h.get("trade_margin_usdt") or 0.0)
    # Book dropped margin (cancel/expire) → return gap to cash.
    if old_tm > tm + 1e-9:
        h["cash_free_usdt"] = float(h.get("cash_free_usdt") or 0.0) + (old_tm - tm)
        h["trade_margin_usdt"] = tm
    elif tm > old_tm + 1e-9:
        # Do not reinflate margin from a stale on-disk book without reserve().
        h["trade_margin_usdt"] = old_tm
    else:
        h["trade_margin_usdt"] = tm
    h["earn_principal_usdt"] = ep
    h["earn_accrued_usdt"] = ea
    _repair_legacy_margin_double_count(h)
    h["equity_usdt"] = total_equity(h)
    save_holistic(root, h)
    return h


def trade_portfolio_overlay(root: str | Path, base: Mapping[str, Any]) -> dict[str, Any]:
    """Portfolio dict for ``propose_size`` backed by holistic cash.

    Uses ``load_holistic`` (not full reconcile) so mid-flight reserve/release
    is not clobbered by on-disk pending before ``save_pending``.
    """
    h = load_holistic(root)
    ep, ea = _sum_earn_positions(root)
    view = dict(h)
    view["earn_principal_usdt"] = ep
    view["earn_accrued_usdt"] = ea
    view["equity_usdt"] = total_equity(view)
    port = dict(base)
    port["equity_usdt"] = float(view["equity_usdt"])
    port["margin_used_usdt"] = float(view.get("trade_margin_usdt") or 0.0)
    port["_holistic_cash_free"] = float(view.get("cash_free_usdt") or 0.0) + redeemable_earn_usdt(root)
    return port


def unwind_earn_to_cash(root: str | Path) -> dict[str, Any]:
    """Redeem all flexible earn into cash_free (futures-only ops mode)."""
    from eurika.ml.earn_monitor import apply_earn_actions, load_earn_positions

    by_asset: dict[str, float] = {}
    for pos in load_earn_positions(root):
        if str(pos.get("kind") or "flexible").lower() == "locked":
            continue
        asset = str(pos.get("asset") or "USDT").upper()
        by_asset[asset] = by_asset.get(asset, 0.0) + float(pos.get("amount") or 0.0) + float(
            pos.get("accrued_usdt") or 0.0
        )
    actions = [
        {"product": "earn", "action": "redeem", "asset": asset, "amount_usdt": amt}
        for asset, amt in by_asset.items()
        if amt > 1e-9
    ]
    out = apply_earn_actions(root, actions) if actions else {"applied": {}}
    h = reconcile_holistic(root)
    return {"redeemed": by_asset, "applied": out.get("applied"), "holistic": h}


def restore_holistic_start_equity(root: str | Path) -> dict[str, Any]:
    """Top up cash so equity ≈ start + realized (repair stranded margin leaks)."""
    h = reconcile_holistic(root)
    start = float(h.get("start_equity_usdt") or DEFAULT_HOLISTIC_START_USDT)
    realized = float(h.get("trade_realized_pnl_usdt") or 0.0)
    target = start + realized
    actual = float(h.get("equity_usdt") or 0.0)
    gap = target - actual
    if gap > 0.01:
        receive_cash(root, gap)
        h = reconcile_holistic(root)
        h["bankroll_repair_usdt"] = round(gap, 6)
        save_holistic(root, h)
    return h


def can_spend_cash(root: str | Path, amount: float) -> bool:
    h = load_holistic(root)
    return float(amount) > 0 and float(h.get("cash_free_usdt") or 0.0) >= float(amount)


def spend_cash(root: str | Path, amount: float) -> bool:
    h = ensure_holistic(root)
    amt = float(amount)
    if amt <= 0 or float(h.get("cash_free_usdt") or 0.0) < amt:
        return False
    h["cash_free_usdt"] = float(h.get("cash_free_usdt") or 0.0) - amt
    h["equity_usdt"] = total_equity(h)
    save_holistic(root, h)
    return True


def receive_cash(root: str | Path, amount: float) -> None:
    h = ensure_holistic(root)
    h["cash_free_usdt"] = float(h.get("cash_free_usdt") or 0.0) + max(0.0, float(amount))
    h["equity_usdt"] = total_equity(h)
    save_holistic(root, h)


def redeemable_earn_usdt(root: str | Path, *, asset: str = "USDT", flexible_only: bool = True) -> float:
    """Principal (+ accrued) in earn that can be auto-redeemed for trade margin."""
    from eurika.ml.earn_monitor import load_earn_positions

    want = str(asset or "USDT").upper()
    total = 0.0
    for pos in load_earn_positions(root):
        if str(pos.get("asset") or "").upper() != want:
            continue
        if flexible_only and str(pos.get("kind") or "flexible").lower() == "locked":
            continue
        total += float(pos.get("amount") or 0.0) + float(pos.get("accrued_usdt") or 0.0)
    return max(0.0, total)


def fund_cash_from_earn(root: str | Path, amount_usdt: float, *, asset: str = "USDT") -> float:
    """Move earn principal into holistic ``cash_free``; returns USDT redeemed."""
    need = max(0.0, float(amount_usdt))
    if need <= 0:
        return 0.0
    redeemable = redeemable_earn_usdt(root, asset=asset)
    if redeemable <= 0:
        return 0.0
    from eurika.ml.earn_monitor import apply_earn_actions

    amt = min(need, redeemable)
    out = apply_earn_actions(
        root,
        [{"product": "earn", "action": "redeem", "asset": str(asset).upper(), "amount_usdt": amt}],
    )
    raw_applied = out.get("applied")
    applied: dict[str, Any] = raw_applied if isinstance(raw_applied, dict) else {}
    if int(applied.get("redeem") or 0) <= 0:
        return 0.0
    return amt


def trade_spendable_cash_usdt(root: str | Path) -> float:
    """Cash on hand plus flexible earn available for auto-redeem before trades."""
    h = reconcile_holistic(root)
    return float(h.get("cash_free_usdt") or 0.0) + redeemable_earn_usdt(root)


def reserve_trade_margin(root: str | Path, margin_usdt: float) -> bool:
    h = ensure_holistic(root)
    m = float(margin_usdt)
    if m <= 0:
        return True
    cash = float(h.get("cash_free_usdt") or 0.0)
    if cash < m:
        fund_cash_from_earn(root, m - cash)
        h = load_holistic(root)
        cash = float(h.get("cash_free_usdt") or 0.0)
    if cash < m:
        return False
    h["cash_free_usdt"] -= m
    h["trade_margin_usdt"] = float(h.get("trade_margin_usdt") or 0.0) + m
    h["equity_usdt"] = total_equity(h)
    save_holistic(root, h)
    return True


def release_trade_margin(root: str | Path, margin_usdt: float, pnl_usdt: float = 0.0) -> None:
    h = ensure_holistic(root)
    m = max(0.0, float(margin_usdt))
    pnl = float(pnl_usdt)
    h["trade_margin_usdt"] = max(0.0, float(h.get("trade_margin_usdt") or 0.0) - m)
    h["trade_realized_pnl_usdt"] = float(h.get("trade_realized_pnl_usdt") or 0.0) + pnl
    h["cash_free_usdt"] = float(h.get("cash_free_usdt") or 0.0) + m + pnl
    h["equity_usdt"] = total_equity(h)
    save_holistic(root, h)


def add_earn_accrual(root: str | Path, delta_usdt: float) -> None:
    h = ensure_holistic(root)
    d = max(0.0, float(delta_usdt))
    h["earn_accrued_usdt"] = float(h.get("earn_accrued_usdt") or 0.0) + d
    h["equity_usdt"] = total_equity(h)
    h["last_accrue_ms"] = _now_ms()
    save_holistic(root, h)


def format_holistic_for_prompt(root: str | Path) -> str:
    h = reconcile_holistic(root)
    eq = float(h.get("equity_usdt") or 0.0)
    start = float(h.get("start_equity_usdt") or eq)
    lines = [
        "HOLISTIC CASH POOL (единый банк trade+earn)",
        f"  equity={eq:.2f} USDT start={start:.2f} Δ={eq-start:+.2f}",
        f"  cash_free={float(h.get('cash_free_usdt') or 0):.2f} "
        f"earn_principal={float(h.get('earn_principal_usdt') or 0):.2f} "
        f"earn_accrued={float(h.get('earn_accrued_usdt') or 0):.4f}",
        f"  trade_margin={float(h.get('trade_margin_usdt') or 0):.2f} "
        f"trade_realized_pnl={float(h.get('trade_realized_pnl_usdt') or 0):+.3f}",
        "  deposit/redeem earn и margin trade берутся из cash_free; не дублируй капитал.",
        f"  trade_spendable={trade_spendable_cash_usdt(root):.2f} "
        "(cash_free + flexible earn; перед trade недостающая маржа redeem из earn автоматически).",
    ]
    return "\n".join(lines)
