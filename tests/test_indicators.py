from trading_lab.indicators import ema, rsi, volume_profile, vwap


def test_vwap_uses_typical_price_weighted_by_volume():
    bars = [
        {"high": 10, "low": 8, "close": 9, "volume": 100},
        {"high": 12, "low": 10, "close": 11, "volume": 300},
    ]

    assert vwap(bars) == 10.5


def test_ema_returns_latest_exponential_average():
    assert ema([1, 2, 3, 4, 5], period=3) == 4.0625


def test_rsi_handles_all_gains_as_100():
    closes = list(range(1, 17))

    assert rsi(closes, period=14) == 100.0


def test_volume_profile_reports_current_average_and_ratio():
    bars = [
        {"volume": 100},
        {"volume": 200},
        {"volume": 400},
    ]

    profile = volume_profile(bars, lookback=3)

    assert profile["current_volume"] == 400
    assert profile["avg_volume"] == 233.3333
    assert profile["volume_ratio"] == 1.7143
    assert profile["trend"] == "above_average"
