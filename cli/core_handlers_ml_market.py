"""CLI: eurika ml-market {sync,paper,train,status} — paper ML market loop (no live orders)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from eurika.ml.features import DEFAULT_WINDOW
from eurika.ml.market_store import DEFAULT_INTERVAL, DEFAULT_SYMBOL
from eurika.ml.paper_trader import DEFAULT_HORIZON, DEFAULT_THR, fee_for_market
from eurika.utils.env import load_project_dotenv


def handle_ml_market(args: Any) -> int:
    """Dispatch ml-market subcommands."""
    path = getattr(args, "path", None)
    root = path.resolve() if path is not None else None
    if root is None:
        from pathlib import Path

        root = Path(".").resolve()
    load_project_dotenv(root)
    sub = getattr(args, "ml_market_command", None)
    if sub == "sync":
        return _cmd_sync(args, root)
    if sub == "paper":
        return _cmd_paper(args, root)
    if sub == "train":
        return _cmd_train(args, root)
    if sub == "status":
        return _cmd_status(args, root)
    print("eurika ml-market: need subcommand sync|paper|train|status")
    return 1


def _cmd_sync(args: Any, root: Any) -> int:
    from eurika.ml.market_store import parse_markets, sync_klines

    symbol = getattr(args, "symbol", None) or DEFAULT_SYMBOL
    interval = getattr(args, "interval", None) or DEFAULT_INTERVAL
    limit = int(getattr(args, "limit", 500) or 500)
    markets = parse_markets(getattr(args, "market", None) or "spot")
    ok_all = True
    for kind in markets:
        out = sync_klines(root, symbol=symbol, interval=interval, limit=limit, market=kind)
        if out.get("ok"):
            print(
                f"ml-market sync: {out['symbol']} {out.get('market', kind)} {out['interval']} "
                f"added={out['added']} total={out['total']}\n  {out['path']}"
            )
        else:
            ok_all = False
            print(f"ml-market sync failed ({kind}): {out.get('error')}")
    return 0 if ok_all else 1


def _cmd_paper(args: Any, root: Any) -> int:
    from eurika.ml.paper_trader import run_paper_backfill
    from eurika.ml.market_model import predict_action
    from eurika.ml.features import feature_vector
    from eurika.ml.market_store import load_candles, normalize_market

    symbol = getattr(args, "symbol", None) or DEFAULT_SYMBOL
    interval = getattr(args, "interval", None) or DEFAULT_INTERVAL
    market = normalize_market(getattr(args, "market", None) or "spot")
    window = int(getattr(args, "window", DEFAULT_WINDOW) or DEFAULT_WINDOW)
    horizon = int(getattr(args, "horizon", DEFAULT_HORIZON) or DEFAULT_HORIZON)
    raw_fee = getattr(args, "fee", None)
    fee = float(raw_fee) if raw_fee is not None else fee_for_market(market)
    thr = float(getattr(args, "thr", DEFAULT_THR) if getattr(args, "thr", None) is not None else DEFAULT_THR)
    append = not bool(getattr(args, "replace", False))
    use_model = bool(getattr(args, "use_model", False))

    policy_fn: Callable[[Sequence[float]], str] | None = None
    if use_model:

        def _model_policy(vec: Sequence[float]) -> str:
            return str(predict_action(root, vec)["action"])

        policy_fn = _model_policy

    out = run_paper_backfill(
        root,
        symbol=symbol,
        interval=interval,
        window=window,
        horizon=horizon,
        fee=fee,
        thr=thr,
        policy=policy_fn,
        append=append,
        market=market,
    )
    if not out.get("ok"):
        print(f"ml-market paper failed: {out.get('error')}")
        return 1
    acc = out.get("accuracy")
    acc_s = f"{acc:.3f}" if isinstance(acc, float) else "n/a"
    print(
        f"ml-market paper: market={market} written={out['written']} correct={out['correct']} "
        f"incorrect={out['incorrect']} hold_skip={out['skipped_hold']} accuracy={acc_s}"
    )
    print(f"  {out['path']}")
    # Hint next live-closed bar suggestion (no order)
    candles = load_candles(root, symbol, interval, market=market)
    vec = feature_vector(candles, window=window)
    if vec is not None:
        sug = predict_action(root, vec)
        print(f"  next_suggestion: {sug['action']} (source={sug['source']}) — paper only, no live order")
    return 0


def _cmd_train(args: Any, root: Any) -> int:
    from eurika.ml.market_model import train_market_policy

    epochs = int(getattr(args, "epochs", 40) or 40)
    out = train_market_policy(root, epochs=epochs)
    if not out.get("ok"):
        print(f"ml-market train failed: {out.get('error')}")
        return 1
    print(
        f"ml-market train: samples={out.get('samples')} "
        f"train_accuracy={out.get('train_accuracy')} loss={out.get('final_loss')} "
        f"device={out.get('device')}"
    )
    print(f"  {out.get('weights')}")
    return 0


def _cmd_status(args: Any, root: Any) -> int:
    from eurika.ml.market_model import model_status
    from eurika.ml.market_store import market_status
    from eurika.ml.paper_trader import paper_status

    mkt = market_status(root)
    paper = paper_status(root)
    model = model_status(root)
    print("ml-market status (read-only / paper — no live orders)")
    print(f"  market_dir: {mkt.get('market_dir')}")
    for s in mkt.get("series") or []:
        mk = s.get("market") or "spot"
        print(f"    [{mk}] {s.get('symbol')} {s.get('interval')}: candles={s.get('count')} ({s.get('file')})")
    if not mkt.get("series"):
        print("    (empty — run: eurika ml-market sync)")
    acc = paper.get("accuracy")
    acc_s = f"{acc:.3f}" if isinstance(acc, float) else "n/a"
    print(
        f"  paper_trades: count={paper.get('count')} buys={paper.get('buys')} "
        f"sells={paper.get('sells')} accuracy={acc_s}"
    )
    print(f"    {paper.get('path')}")
    print(f"  model: torch={model.get('torch_available')} weights={model.get('weights_exist')}")
    meta = model.get("meta") or {}
    if isinstance(meta, dict) and meta.get("train_accuracy") is not None:
        print(f"    train_accuracy={meta.get('train_accuracy')} samples={meta.get('samples')}")
    print(f"    {model.get('weights')}")
    print("  hint: eurika ml-market sync && eurika ml-market paper && eurika ml-market train")
    return 0
