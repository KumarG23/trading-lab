from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

CORE_SYMBOLS = ["SPY", "QQQ", "AMD", "NVDA"]

DEFAULT_SCAN_UNIVERSE = [
    # Indices / large liquid anchors
    "SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN", "GOOGL", "NFLX",
    # Liquid tech / AI / semis
    "PLTR", "SOFI", "HOOD", "COIN", "RBLX", "U", "AI", "PATH", "SNOW", "DDOG", "NET", "CRWD", "ZS", "SHOP",
    "SQ", "PYPL", "AFRM", "UPST", "MARA", "RIOT", "CLSK", "HUT", "SMCI", "ARM", "MU", "INTC", "MRVL", "ON", "WDC",
    # Lower-priced liquid growth / retail-interest names
    "RKLB", "IONQ", "ACHR", "JOBY", "ASTS", "OPEN", "LCID", "RIVN", "NIO", "BBAI", "SOUN", "SERV", "WULF", "IREN",
    "DKNG", "ROKU", "FUBO", "CHPT", "RUN", "ENPH", "SEDG", "QS", "DNA", "RXRX", "BEAM", "CRSP", "EDIT", "NTLA",
    # Financials / cyclicals / energy movers
    "BAC", "F", "GM", "CCL", "NCLH", "DAL", "UAL", "AAL", "UBER", "LYFT", "X", "CLF", "FCX", "SLV", "GLD", "USO",
    # ETFs useful for regime / volatility context
    "TQQQ", "SQQQ", "SOXL", "SOXS", "ARKK", "XLF", "XLE", "XLK", "XBI", "KRE", "VXX",
]


def score_universe(
    bars: list[dict[str, Any]],
    *,
    symbols: list[str],
    min_price: float = 2.0,
    max_price: float = 300.0,
    min_dollar_volume: float = 250_000.0,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    wanted = {s.upper() for s in symbols}
    for bar in bars:
        symbol = str(bar.get("symbol", "")).upper()
        if symbol in wanted:
            grouped[symbol].append(bar)

    rows: list[dict[str, Any]] = []
    for symbol, symbol_bars in grouped.items():
        ordered = sorted(symbol_bars, key=lambda item: str(item["timestamp"]))
        if len(ordered) < 2:
            continue
        last = ordered[-1]
        latest_close = float(last["close"])
        if latest_close < min_price or latest_close > max_price:
            continue
        current_day = str(last["timestamp"])[:10]
        current_bars = [b for b in ordered if str(b["timestamp"])[:10] == current_day]
        prior_bars = [b for b in ordered if str(b["timestamp"])[:10] != current_day]
        if not current_bars or not prior_bars:
            continue
        prior_close = float(prior_bars[-1]["close"])
        current_volume = sum(float(b["volume"]) for b in current_bars)
        prior_days: dict[str, float] = defaultdict(float)
        for bar in prior_bars:
            prior_days[str(bar["timestamp"])[:10]] += float(bar["volume"])
        avg_prior_volume = mean(prior_days.values()) if prior_days else 0.0
        dollar_volume = current_volume * latest_close
        if dollar_volume < min_dollar_volume:
            continue
        change_pct = ((latest_close - prior_close) / prior_close * 100.0) if prior_close else 0.0
        relative_volume = (current_volume / avg_prior_volume) if avg_prior_volume else 0.0
        intraday_range_pct = ((max(float(b["high"]) for b in current_bars) - min(float(b["low"]) for b in current_bars)) / latest_close * 100.0) if latest_close else 0.0
        score = _score(change_pct=change_pct, relative_volume=relative_volume, dollar_volume=dollar_volume, intraday_range_pct=intraday_range_pct, price=latest_close)
        rows.append(
            {
                "symbol": symbol,
                "score": round(score, 3),
                "price": round(latest_close, 4),
                "change_pct": round(change_pct, 3),
                "relative_volume": round(relative_volume, 3),
                "dollar_volume": round(dollar_volume, 2),
                "intraday_range_pct": round(intraday_range_pct, 3),
                "why": _why(change_pct, relative_volume, intraday_range_pct, latest_close),
            }
        )
    return sorted(rows, key=lambda row: (-float(row["score"]), row["symbol"]))


def filter_stocks_in_play(
    scored: list[dict[str, Any]],
    *,
    min_score: float = 35.0,
    min_abs_change_pct: float = 2.0,
    min_relative_volume: float = 1.2,
    min_intraday_range_pct: float = 2.5,
) -> list[dict[str, Any]]:
    return [
        row
        for row in scored
        if float(row.get("score") or 0) >= min_score
        and (
            abs(float(row.get("change_pct") or 0)) >= min_abs_change_pct
            or float(row.get("relative_volume") or 0) >= min_relative_volume
            or float(row.get("intraday_range_pct") or 0) >= min_intraday_range_pct
        )
    ]


def pick_watchlist(scored: list[dict[str, Any]], *, core_symbols: list[str] | None = None, max_symbols: int = 30) -> list[str]:
    selected: list[str] = []
    for symbol in core_symbols or CORE_SYMBOLS:
        _append_unique(selected, symbol.upper())
    for row in scored:
        _append_unique(selected, str(row["symbol"]).upper())
        if len(selected) >= max_symbols:
            break
    return selected[:max_symbols]


def _score(*, change_pct: float, relative_volume: float, dollar_volume: float, intraday_range_pct: float, price: float) -> float:
    movement = min(abs(change_pct), 20.0) * 4.0
    relvol = min(relative_volume, 10.0) * 8.0
    liquidity = min(dollar_volume / 1_000_000.0, 25.0)
    range_component = min(intraday_range_pct, 12.0) * 2.0
    price_bonus = 8.0 if 3.0 <= price <= 80.0 else 3.0 if price <= 150 else 0.0
    return movement + relvol + liquidity + range_component + price_bonus


def _why(change_pct: float, relative_volume: float, intraday_range_pct: float, price: float) -> list[str]:
    reasons: list[str] = []
    if abs(change_pct) >= 3:
        reasons.append(f"{change_pct:+.1f}% mover")
    if relative_volume >= 1.5:
        reasons.append(f"{relative_volume:.1f}x relative volume")
    if intraday_range_pct >= 2:
        reasons.append(f"{intraday_range_pct:.1f}% intraday range")
    if 3 <= price <= 80:
        reasons.append("small-account price band")
    return reasons or ["liquid watchlist candidate"]


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)
