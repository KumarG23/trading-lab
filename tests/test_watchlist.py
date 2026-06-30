from pathlib import Path

from trading_lab.watchlist import load_symbols


def test_load_symbols_prefers_scanner_watchlist_file(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text('{"watchlist": ["spy", "sofi", "pltr"]}', encoding="utf-8")

    assert load_symbols("AAPL,MSFT", watchlist_file=path) == ["SPY", "SOFI", "PLTR"]


def test_load_symbols_falls_back_to_cli_symbols_when_file_missing(tmp_path):
    assert load_symbols("aapl, msft, AAPL", watchlist_file=tmp_path / "missing.json") == ["AAPL", "MSFT"]
