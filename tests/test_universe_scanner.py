from trading_lab.universe_scanner import DEFAULT_SCAN_UNIVERSE, filter_stocks_in_play, pick_watchlist, score_universe


def _bar(symbol, day, minute, close, volume=1000):
    return {
        "symbol": symbol,
        "timestamp": f"2026-06-{day:02d}T13:{30 + minute:02d}:00Z",
        "open": close,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": volume,
    }


def test_score_universe_prefers_movers_with_volume_and_tradeable_price():
    bars = []
    for minute in range(3):
        bars.append(_bar("CHEAP", 29, minute, 4.0, 1000))
        bars.append(_bar("CHEAP", 30, minute, 4.8, 9000))
        bars.append(_bar("SLEEP", 29, minute, 20.0, 5000))
        bars.append(_bar("SLEEP", 30, minute, 20.1, 4000))
        bars.append(_bar("RICH", 29, minute, 900.0, 10000))
        bars.append(_bar("RICH", 30, minute, 950.0, 20000))

    scored = score_universe(bars, symbols=["CHEAP", "SLEEP", "RICH"], min_price=2, max_price=300, min_dollar_volume=10_000)

    assert [row["symbol"] for row in scored] == ["CHEAP", "SLEEP"]
    assert scored[0]["relative_volume"] > 1
    assert scored[0]["change_pct"] > scored[1]["change_pct"]
    assert scored[0]["score"] > scored[1]["score"]


def test_pick_watchlist_keeps_core_symbols_and_top_scanner_matches():
    scored = [
        {"symbol": "SOFI", "score": 90},
        {"symbol": "PLTR", "score": 80},
        {"symbol": "HOOD", "score": 70},
    ]

    watchlist = pick_watchlist(scored, core_symbols=["SPY", "QQQ"], max_symbols=4)

    assert watchlist == ["SPY", "QQQ", "SOFI", "PLTR"]


def test_filter_stocks_in_play_rejects_liquid_but_inert_names():
    scored = [
        {"symbol": "MOVE", "score": 52, "change_pct": 3.1, "relative_volume": 1.0, "intraday_range_pct": 2.0},
        {"symbol": "RVOL", "score": 48, "change_pct": 0.5, "relative_volume": 1.5, "intraday_range_pct": 1.0},
        {"symbol": "RANGE", "score": 43, "change_pct": 0.2, "relative_volume": 0.9, "intraday_range_pct": 3.0},
        {"symbol": "SLEEP", "score": 42, "change_pct": 0.2, "relative_volume": 0.9, "intraday_range_pct": 1.0},
        {"symbol": "WEAK", "score": 20, "change_pct": 5.0, "relative_volume": 2.0, "intraday_range_pct": 5.0},
    ]

    filtered = filter_stocks_in_play(scored)

    assert [row["symbol"] for row in filtered] == ["MOVE", "RVOL", "RANGE"]


def test_default_scan_universe_contains_more_than_large_cap_megafaang():
    assert len(DEFAULT_SCAN_UNIVERSE) >= 75
    for symbol in ["SOFI", "HOOD", "RKLB", "IONQ", "OPEN", "PLTR"]:
        assert symbol in DEFAULT_SCAN_UNIVERSE
