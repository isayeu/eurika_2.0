"""Tests for Market journal persistence and weekly/size rotation."""

from __future__ import annotations

from pathlib import Path

from eurika.ml import market_journal as mj


def test_append_and_load_market_journal(tmp_path: Path) -> None:
    p = mj.append_market_journal(tmp_path, "тест синхронизация", kind="sync")
    assert p == mj.market_journal_path(tmp_path)
    assert p.is_file()
    mj.append_market_journal(
        tmp_path,
        "итог: BTCUSDT → удача",
        kind="outcome",
        reason="model",
        bar_ts=1_700_000_000_000,
        symbol="btcusdt",
        market="spot",
        extras={"edge": 0.002, "correct": True},
    )
    rows = mj.load_market_journal(tmp_path)
    assert len(rows) == 2
    assert rows[0]["kind"] == "sync"
    assert rows[0]["message"] == "тест синхронизация"
    assert rows[1]["kind"] == "outcome"
    assert rows[1]["reason"] == "model"
    assert rows[1]["bar_ts"] == 1_700_000_000_000
    assert rows[1]["symbol"] == "BTCUSDT"
    assert rows[1]["market"] == "spot"
    assert rows[1]["edge"] == 0.002
    assert rows[1]["correct"] is True
    assert "ts" in rows[0]
    last = mj.load_market_journal(tmp_path, limit=1)
    assert len(last) == 1
    assert last[0]["kind"] == "outcome"


def test_journal_fields_from_event() -> None:
    fields = mj.journal_fields_from_event(
        {
            "kind": "outcome",
            "message": "text",
            "exit_reason": "sl",
            "exit_ts": 99,
            "symbol": "ETHUSDT",
            "market": "futures",
            "edge": -0.01,
            "fee": 0.0007,
            "fee_source": "maker_taker",
            "entry_fee": 0.0002,
            "exit_fee": 0.0005,
            "entry_liquidity": "maker",
            "exit_liquidity": "taker",
            "entry_style": "oco",
            "fill_leg": "limit",
        }
    )
    assert fields["reason"] == "sl"
    assert fields["bar_ts"] == 99
    assert fields["symbol"] == "ETHUSDT"
    assert fields["market"] == "futures"
    assert fields["fee"] == 0.0007
    assert fields["fee_source"] == "maker_taker"
    assert fields["entry_fee"] == 0.0002
    assert fields["exit_fee"] == 0.0005
    assert fields["entry_liquidity"] == "maker"
    assert fields["exit_liquidity"] == "taker"
    assert fields["entry_style"] == "oco"
    assert fields["fill_leg"] == "limit"

    fields2 = mj.journal_fields_from_event(
        {"reason": "pending", "bar_ts": 1, "symbol": "BTCUSDT", "utc_hour": 8}
    )
    assert fields2["utc_hour"] == 8


def test_rotate_market_journal_by_size(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mj, "JOURNAL_ROTATE_MAX_BYTES", 200)
    monkeypatch.setattr(mj, "JOURNAL_ARCHIVE_KEEP", 2)
    path = mj.market_journal_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"ts": 1, "kind": "sync", "message": "' + ("x" * 300) + '"}\n', encoding="utf-8")
    # No stamp yet + oversized → rotate on append
    mj.append_market_journal(tmp_path, "после ротации", kind="info")
    assert path.is_file()
    rows = mj.load_market_journal(tmp_path)
    assert any("ротация" in str(r.get("message")) for r in rows)
    assert any(r.get("message") == "после ротации" for r in rows)
    archives = list(path.parent.glob("market_journal_*.jsonl"))
    assert len(archives) == 1


def test_rotate_market_journal_by_week(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mj, "JOURNAL_ROTATE_DAYS", 7)
    path = mj.market_journal_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"ts": 1, "kind": "hold", "message": "old"}\n', encoding="utf-8")
    # Stamp from 8 days ago
    old_ms = int(__import__("time").time() * 1000) - 8 * 86_400_000
    mj._save_rotate_stamp(tmp_path, old_ms)
    arch = mj.maybe_rotate_market_journal(tmp_path)
    assert arch is not None and arch.is_file()
    rows = mj.load_market_journal(tmp_path)
    assert len(rows) == 1
    assert "ротация" in rows[0]["message"]
