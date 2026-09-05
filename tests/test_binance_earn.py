"""Tests for Binance Simple Earn read-only helpers."""

from __future__ import annotations

from eurika.integrations import binance_readonly as br


def test_earn_product_row_flexible() -> None:
    row = br._earn_product_row(
        {
            "asset": "USDT",
            "productId": "USDT001",
            "latestAnnualPercentageRate": "0.0523",
            "minPurchaseAmount": "10",
            "canPurchase": True,
        },
        kind="flexible",
    )
    assert row is not None
    assert row["asset"] == "USDT"
    assert abs(row["apr"] - 0.0523) < 1e-6


def test_simple_earn_flexible_products_mock(monkeypatch) -> None:
    def fake_get(path, **kwargs):
        assert "flexible/list" in path
        return {
            "rows": [
                {
                    "asset": "USDC",
                    "productId": "USDC001",
                    "latestAnnualPercentageRate": "4.5",
                }
            ],
            "total": 1,
        }

    monkeypatch.setattr(br, "_sapi_get", fake_get)
    monkeypatch.setattr(br, "binance_credentials_status", lambda: {"ready": True})
    out = br.simple_earn_flexible_products()
    assert out["ok"] is True
    assert out["products"][0]["asset"] == "USDC"
    assert out["products"][0]["apr"] == 0.045
