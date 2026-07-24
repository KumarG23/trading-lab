from trading_lab.market_regime import bullish_market_regime, market_regime_label


def _spy_bar(minute: int, close: float, volume: float = 1000) -> dict:
    return {
        "symbol": "SPY",
        "timestamp": f"2026-07-20T13:{30 + minute:02d}:00Z",
        "open": close,
        "high": close + 0.1,
        "low": close - 0.1,
        "close": close,
        "volume": volume,
    }


def test_bullish_market_regime_requires_spy_above_rising_vwap():
    rising = [_spy_bar(i, 100 + i * 0.2) for i in range(6)]
    falling = [_spy_bar(i, 101 - i * 0.2) for i in range(6)]

    assert bullish_market_regime(rising) is True
    assert bullish_market_regime(falling) is False


def test_bullish_market_regime_does_not_block_when_spy_context_is_missing():
    assert bullish_market_regime([]) is True
    assert market_regime_label([]) == "unknown"
