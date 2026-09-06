"""Tests for shared LLM lease (.eurika/llm_lease.json)."""

from __future__ import annotations

from pathlib import Path

from eurika.orchestration import llm_lease as ll


def test_acquire_release_and_idle_quiet(tmp_path: Path) -> None:
    t0 = 1_000_000
    got = ll.acquire(
        tmp_path,
        holder="chat:1",
        priority="interactive",
        purpose="chat",
        now_ms=t0,
        ttl_ms=60_000,
    )
    assert got["ok"] is True
    assert ll.is_idle_for(tmp_path, quiet_ms=3_000, now_ms=t0) is False

    denied = ll.acquire(
        tmp_path,
        holder="self:1",
        priority="self_dev",
        purpose="idle",
        now_ms=t0 + 100,
        ttl_ms=60_000,
    )
    assert denied["ok"] is False
    assert denied["reason"] == "busy"

    released = ll.release(tmp_path, holder="chat:1", now_ms=t0 + 200)
    assert released["ok"] is True
    assert ll.is_idle_for(tmp_path, quiet_ms=3_000, now_ms=t0 + 500) is False
    assert ll.is_idle_for(tmp_path, quiet_ms=3_000, now_ms=t0 + 200 + 3_000) is True


def test_higher_priority_preempts_lower(tmp_path: Path) -> None:
    t0 = 2_000_000
    assert ll.acquire(
        tmp_path,
        holder="self:1",
        priority="self_dev",
        purpose="idle",
        now_ms=t0,
    )["ok"]
    market = ll.acquire(
        tmp_path,
        holder="market:1",
        priority="market",
        purpose="cursor_hour",
        now_ms=t0 + 10,
    )
    assert market["ok"] is True
    assert market["lease"]["holder"] == "market:1"

    still = ll.acquire(
        tmp_path,
        holder="self:2",
        priority="self_dev",
        purpose="idle",
        now_ms=t0 + 20,
    )
    assert still["ok"] is False


def test_stale_lease_reclaimed(tmp_path: Path) -> None:
    t0 = 3_000_000
    ll.acquire(
        tmp_path,
        holder="chat:stale",
        priority="interactive",
        purpose="chat",
        now_ms=t0,
        ttl_ms=1_000,
    )
    later = ll.acquire(
        tmp_path,
        holder="self:fresh",
        priority="self_dev",
        purpose="idle",
        now_ms=t0 + 5_000,
        ttl_ms=60_000,
    )
    assert later["ok"] is True
    assert later["lease"]["holder"] == "self:fresh"


def test_same_holder_renews(tmp_path: Path) -> None:
    t0 = 4_000_000
    first = ll.acquire(
        tmp_path,
        holder="chat:same",
        priority="interactive",
        purpose="chat",
        now_ms=t0,
    )
    assert first["ok"] is True
    second = ll.acquire(
        tmp_path,
        holder="chat:same",
        priority="interactive",
        purpose="chat",
        now_ms=t0 + 50,
    )
    assert second["ok"] is True
    assert second.get("renewed") is True
