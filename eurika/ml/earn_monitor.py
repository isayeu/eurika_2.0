"""Paper Simple Earn / Advanced Earn book (read rates from Binance, sim yield).

Isolated from MLP exam bank. Agent deposits/redeems via ``portfolio_actions``.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from eurika.ml.market_store import ml_root

DEFAULT_EARN_START_USDT = 1000.0
DEFAULT_EARN_ASSETS = ("USDT", "USDC", "BTC", "ETH", "BNB", "SOL")
_EARN_ACTIONS = frozenset({"deposit", "redeem", "hold", "accrue"})


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ts_iso(ms: int | None = None) -> str:
    t = int(ms or _now_ms()) / 1000.0
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def earn_portfolio_path(root: str | Path) -> Path:
    return ml_root(root) / "earn_portfolio.json"


def earn_positions_path(root: str | Path) -> Path:
    return ml_root(root) / "earn_positions.json"


def earn_rates_cache_path(root: str | Path) -> Path:
    return ml_root(root) / "earn_rates_cache.json"


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


def default_earn_portfolio() -> dict[str, Any]:
    eq = float(DEFAULT_EARN_START_USDT)
    now = _now_ms()
    return {
        "version": 1,
        "start_equity_usdt": eq,
        "equity_usdt": eq,
        "cash_usdt": eq,
        "principal_usdt": 0.0,
        "accrued_usdt": 0.0,
        "note": "paper earn book; rates from Binance Simple Earn",
        "created_ms": now,
        "updated_ms": now,
        "last_accrue_ms": now,
    }


def load_earn_portfolio(root: str | Path) -> dict[str, Any]:
    data = _read_json(earn_portfolio_path(root), None)
    if not isinstance(data, dict):
        return default_earn_portfolio()
    out = default_earn_portfolio()
    out.update({k: data[k] for k in data if k in out or k in ("version", "note", "created_ms", "last_accrue_ms")})
    return out


def save_earn_portfolio(root: str | Path, port: Mapping[str, Any]) -> None:
    blob = dict(port)
    blob["updated_ms"] = _now_ms()
    _write_json(earn_portfolio_path(root), blob)


def ensure_earn_portfolio(root: str | Path) -> dict[str, Any]:
    path = earn_portfolio_path(root)
    if not path.is_file():
        port = default_earn_portfolio()
        save_earn_portfolio(root, port)
        return port
    return load_earn_portfolio(root)


def load_earn_positions(root: str | Path) -> list[dict[str, Any]]:
    data = _read_json(earn_positions_path(root), {"positions": []})
    rows = data.get("positions") if isinstance(data, dict) else data
    return [dict(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def save_earn_positions(root: str | Path, positions: Sequence[dict[str, Any]]) -> None:
    _write_json(earn_positions_path(root), {"positions": list(positions)})


def fetch_earn_rates(
    root: str | Path,
    *,
    assets: Sequence[str] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Pull flexible+locked APR from Binance; cache under ``earn_rates_cache.json``."""
    from eurika.integrations.binance_readonly import (
        simple_earn_flexible_products,
        simple_earn_locked_products,
    )

    want = {str(a).upper() for a in (assets or DEFAULT_EARN_ASSETS)}
    flex = simple_earn_flexible_products(size=100, timeout=timeout)
    locked = simple_earn_locked_products(size=100, timeout=timeout)
    products: list[dict[str, Any]] = []
    for row in list(flex.get("products") or []) + list(locked.get("products") or []):
        if not isinstance(row, dict):
            continue
        asset = str(row.get("asset") or "").upper()
        if want and asset not in want:
            continue
        products.append(dict(row))
    products.sort(key=lambda r: (-float(r.get("apr") or 0.0), str(r.get("asset") or "")))
    payload = {
        "fetched_ms": _now_ms(),
        "fetched_iso": _ts_iso(),
        "ok": bool(flex.get("ok") or locked.get("ok")),
        "error": flex.get("error") or locked.get("error"),
        "products": products,
    }
    _write_json(earn_rates_cache_path(root), payload)
    return payload


def load_earn_rates(root: str | Path) -> dict[str, Any]:
    data = _read_json(earn_rates_cache_path(root), {})
    return data if isinstance(data, dict) else {}


def _best_product(rates: Mapping[str, Any], asset: str, kind: str = "flexible") -> dict[str, Any] | None:
    asset_u = asset.upper()
    best: dict[str, Any] | None = None
    for row in rates.get("products") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("asset") or "").upper() != asset_u:
            continue
        if str(row.get("kind") or "flexible") != kind:
            continue
        if best is None or float(row.get("apr") or 0.0) > float(best.get("apr") or 0.0):
            best = dict(row)
    return best


def accrue_earn_yield(root: str | Path, *, now_ms: int | None = None) -> dict[str, Any]:
    """Accrue paper yield on open earn positions since last accrual."""
    now = int(now_ms or _now_ms())
    port = ensure_earn_portfolio(root)
    positions = load_earn_positions(root)
    last = int(port.get("last_accrue_ms") or port.get("updated_ms") or now)
    elapsed_sec = max(0.0, (now - last) / 1000.0)
    if elapsed_sec < 1.0 or not positions:
        port["last_accrue_ms"] = now
        save_earn_portfolio(root, port)
        return {"accrued_usdt": 0.0, "positions": len(positions)}

    total = 0.0
    for pos in positions:
        apr = float(pos.get("apr") or 0.0)
        amt = float(pos.get("amount") or 0.0)
        if apr <= 0 or amt <= 0:
            continue
        # Simple continuous approx: amount * apr * (seconds / year)
        delta = amt * apr * (elapsed_sec / (365.25 * 24 * 3600))
        pos["accrued_usdt"] = float(pos.get("accrued_usdt") or 0.0) + delta
        total += delta
    from eurika.ml.holistic_portfolio import add_earn_accrual, reconcile_holistic

    if total > 0:
        add_earn_accrual(root, total)
    port["accrued_usdt"] = float(port.get("accrued_usdt") or 0.0) + total
    port["principal_usdt"] = sum(float(p.get("amount") or 0.0) for p in positions)
    port["cash_usdt"] = 0.0
    port["equity_usdt"] = float(port.get("principal_usdt") or 0.0) + float(port.get("accrued_usdt") or 0.0)
    port["last_accrue_ms"] = now
    save_earn_portfolio(root, port)
    save_earn_positions(root, positions)
    reconcile_holistic(root)
    return {"accrued_usdt": total, "positions": len(positions)}


def apply_earn_actions(
    root: str | Path,
    actions: Sequence[Mapping[str, Any]],
    *,
    rates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from eurika.ml.holistic_portfolio import receive_cash, reconcile_holistic, spend_cash, ensure_holistic

    ensure_holistic(root)
    port = ensure_earn_portfolio(root)
    positions = load_earn_positions(root)
    rates_blob = dict(rates or load_earn_rates(root))
    applied = {"deposit": 0, "redeem": 0, "hold": 0, "ignored": 0}

    for raw in actions:
        act = str(raw.get("action") or "").strip().lower()
        if act not in _EARN_ACTIONS:
            applied["ignored"] += 1
            continue
        if act == "hold":
            applied["hold"] += 1
            continue
        asset = str(raw.get("asset") or "USDT").strip().upper()
        kind = str(raw.get("earn_type") or raw.get("kind") or "flexible").strip().lower()
        if kind not in {"flexible", "locked"}:
            kind = "flexible"
        try:
            amount = float(raw.get("amount_usdt") or raw.get("amount") or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        if act == "deposit":
            if amount <= 0 or not spend_cash(root, amount):
                applied["ignored"] += 1
                continue
            prod = _best_product(rates_blob, asset, kind=kind)
            apr = float(prod.get("apr") or raw.get("apr") or 0.03) if prod else float(raw.get("apr") or 0.03)
            positions.append(
                {
                    "id": f"earn-{uuid.uuid4().hex[:8]}",
                    "asset": asset,
                    "kind": kind,
                    "amount": amount,
                    "apr": apr,
                    "product_id": str((prod or {}).get("product_id") or f"{kind}:{asset}"),
                    "deposited_ms": _now_ms(),
                    "accrued_usdt": 0.0,
                    "note": str(raw.get("note") or "")[:300],
                }
            )
            applied["deposit"] += 1
            continue
        if act == "redeem":
            if amount <= 0:
                applied["ignored"] += 1
                continue
            left = amount
            new_positions: list[dict[str, Any]] = []
            for pos in positions:
                if left <= 0:
                    new_positions.append(pos)
                    continue
                if str(pos.get("asset") or "").upper() != asset:
                    new_positions.append(pos)
                    continue
                pos_amt = float(pos.get("amount") or 0.0)
                pos_acc = float(pos.get("accrued_usdt") or 0.0)
                if pos_amt <= left:
                    receive_cash(root, pos_amt + pos_acc)
                    left -= pos_amt
                    applied["redeem"] += 1
                    continue
                frac = left / pos_amt
                redeem_acc = pos_acc * frac
                receive_cash(root, left + redeem_acc)
                pos["amount"] = pos_amt - left
                pos["accrued_usdt"] = pos_acc - redeem_acc
                new_positions.append(pos)
                left = 0.0
                applied["redeem"] += 1
            positions = new_positions
            continue
        applied["ignored"] += 1

    port["principal_usdt"] = sum(float(p.get("amount") or 0.0) for p in positions)
    port["accrued_usdt"] = sum(float(p.get("accrued_usdt") or 0.0) for p in positions)
    port["cash_usdt"] = 0.0
    port["equity_usdt"] = float(port.get("principal_usdt") or 0.0) + float(port.get("accrued_usdt") or 0.0)
    save_earn_portfolio(root, port)
    save_earn_positions(root, positions)
    h = reconcile_holistic(root)
    return {"applied": applied, "equity_usdt": h.get("equity_usdt"), "cash_usdt": h.get("cash_free_usdt")}


def format_earn_book_for_prompt(root: str | Path, *, rates: Mapping[str, Any] | None = None) -> str:
    port = load_earn_portfolio(root)
    positions = load_earn_positions(root)
    rates_blob = dict(rates or load_earn_rates(root))
    eq = float(port.get("equity_usdt") or 0.0)
    start = float(port.get("start_equity_usdt") or eq)
    lines = [
        "EARN PAPER BOOK (Simple/Advanced Earn sim; not live subscribe)",
        f"  equity={eq:.2f} USDT start={start:.2f} Δ={eq-start:+.2f}",
        f"  cash={float(port.get('cash_usdt') or 0):.2f} principal={float(port.get('principal_usdt') or 0):.2f} "
        f"accrued={float(port.get('accrued_usdt') or 0):.4f}",
    ]
    lines.append("POSITIONS")
    if not positions:
        lines.append("  none")
    else:
        for pos in positions[:12]:
            lines.append(
                f"  {pos.get('asset')} {pos.get('kind')} amt={float(pos.get('amount') or 0):.2f} "
                f"apr={float(pos.get('apr') or 0)*100:.2f}% accrued={float(pos.get('accrued_usdt') or 0):.4f}"
            )
    lines.append("TOP EARN RATES (cached)")
    products = list(rates_blob.get("products") or [])[:10]
    if not products:
        lines.append("  (нет кэша — fetch_earn_rates или Binance keys)")
    else:
        for row in products:
            dur = row.get("duration_days")
            tag = f" locked {dur}d" if dur else ""
            lines.append(
                f"  {row.get('asset')} {row.get('kind')}{tag} apr={float(row.get('apr') or 0)*100:.2f}%"
            )
    live_note = rates_blob.get("fetched_iso")
    if live_note:
        lines.append(f"  rates_as_of={live_note}")
    return "\n".join(lines)
