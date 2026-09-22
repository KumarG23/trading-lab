"""Offline-only, fixed-parameter ETF research simulation. No order/broker integration."""
from __future__ import annotations

from datetime import date
from math import isfinite

SYMBOLS = ("SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "VNQ")
NOTIONAL = 10_000.0


def validate_bars(raw: list[dict], sessions: list[date]) -> dict[str, dict[date, dict]]:
    wanted = set(sessions)
    if len(wanted) != len(sessions) or sessions != sorted(sessions):
        raise ValueError("sessions must be unique and ordered")
    data: dict[str, dict[date, dict]] = {symbol: {} for symbol in SYMBOLS}
    for bar in raw:
        symbol = bar["symbol"]
        if symbol not in data:
            raise ValueError(f"unexpected symbol: {symbol}")
        day = date.fromisoformat(bar["timestamp"][:10])
        if day not in wanted:
            raise ValueError(f"unexpected session {symbol} {day}")
        if day in data[symbol]:
            raise ValueError(f"duplicate bar {symbol} {day}")
        values = [float(bar[key]) for key in ("open", "high", "low", "close", "volume")]
        o, h, l, c, v = values
        if not all(isfinite(x) for x in values) or min(o, h, l, c) <= 0 or v <= 0 or l > min(o, c) or h < max(o, c):
            raise ValueError(f"invalid bar {symbol} {day}")
        data[symbol][day] = dict(zip(("open", "high", "low", "close", "volume"), values))
    for symbol in SYMBOLS:
        missing = wanted - data[symbol].keys()
        if missing:
            raise ValueError(f"missing {len(missing)} sessions for {symbol}; first {min(missing)}")
    return data


def simulate(data: dict[str, dict[date, dict]], sessions: list[date], start: date, end: date) -> dict:
    indices = [i for i, d in enumerate(sessions) if start <= d <= end]
    if not indices or indices[0] < 200:
        raise ValueError("phase needs at least 200 prior completed sessions")
    if indices != list(range(indices[0], indices[-1] + 1)):
        raise ValueError("non-contiguous phase")
    cash = NOTIONAL
    shares: dict[str, float] = {}
    peaks: dict[str, float] = {}
    equity_curve = []
    transactions = 0
    stops = 0
    turnover = 0.0
    decisions = []
    fee = 0.005

    def sell(symbol: str, qty: float, price: float) -> None:
        nonlocal cash, transactions, turnover
        if qty <= 1e-10:
            return
        cash += qty * (price * (1 - 0.001) - fee)
        turnover += qty * price
        transactions += 1
        left = shares[symbol] - qty
        if left <= 1e-10:
            shares.pop(symbol)
            peaks.pop(symbol)
        else:
            shares[symbol] = left

    for i in indices:
        day = sessions[i]
        prev = sessions[i - 1]
        opening = {s: data[s][day]["open"] for s in SYMBOLS}
        # Prior standing stops have priority over new weekly opening orders.
        # A gap-stopped ticker cannot be repurchased at that same opening.
        stopped_today = set()
        for symbol in list(shares):
            if opening[symbol] <= peaks[symbol] * 0.88:
                sell(symbol, shares[symbol], opening[symbol])
                stops += 1
                stopped_today.add(symbol)
        # Week boundary is determined by the immediately preceding exchange session,
        # including sessions before a phase begins. No phase-boundary special rebalance.
        weekly = (day.isocalendar().year, day.isocalendar().week) != (prev.isocalendar().year, prev.isocalendar().week)
        if weekly:
            spy_closes = [data["SPY"][sessions[j]]["close"] for j in range(i - 200, i)]
            selected = []
            if spy_closes[-1] > sum(spy_closes) / 200:
                for symbol in SYMBOLS:
                    closes = [data[symbol][sessions[j]]["close"] for j in range(i - 200, i)]
                    momentum = closes[-1] / closes[-64] - 1  # 63 completed intervals
                    if symbol not in stopped_today and closes[-1] > sum(closes) / 200 and momentum > 0:
                        selected.append((symbol, momentum))
            targets = [s for s, _ in sorted(selected, key=lambda x: (-x[1], x[0]))[:2]]
            decisions.append({"signal_close": prev.isoformat(), "fill_open": day.isoformat(),
                              "selected": targets, "gap_stopped_before_rebalance": sorted(stopped_today)})
            open_equity = cash + sum(q * opening[s] for s, q in shares.items())
            target_value = open_equity / 2 if targets else 0.0  # unused slot stays cash
            for symbol in list(shares):
                desired = target_value / opening[symbol] if symbol in targets else 0
                sell(symbol, max(0, shares[symbol] - desired), opening[symbol])
            for symbol in targets:
                price = opening[symbol] * (1 + 0.0005)
                desired = target_value / opening[symbol]
                qty = min(max(0, desired - shares.get(symbol, 0)), max(0, cash) / (price + fee))
                if qty > 1e-10:
                    cash -= qty * (price + fee)
                    turnover += qty * opening[symbol]
                    shares[symbol] = shares.get(symbol, 0) + qty
                    peaks[symbol] = max(peaks.get(symbol, 0), price)
        # Standing stop is based on entry fill and completed previous closes only.
        # Gap below stop fills at adverse opening price; otherwise at stop price.
        for symbol in list(shares):
            stop = peaks[symbol] * 0.88
            bar = data[symbol][day]
            if bar["open"] <= stop or bar["low"] <= stop:
                sell(symbol, shares[symbol], min(bar["open"], stop))
                stops += 1
        for symbol in shares:
            peaks[symbol] = max(peaks[symbol], data[symbol][day]["close"])
        equity_curve.append((day.isoformat(), cash + sum(q * data[s][day]["close"] for s, q in shares.items())))
    final = equity_curve[-1][1]
    high = NOTIONAL
    drawdown = 0.0
    for _, value in equity_curve:
        high = max(high, value)
        drawdown = min(drawdown, value / high - 1)
    spy_start = data["SPY"][sessions[indices[0] - 1]]["close"]
    spy_end = data["SPY"][sessions[indices[-1]]]["close"]
    return {
        "start": start.isoformat(), "end": end.isoformat(), "sessions": len(indices),
        "return": final / NOTIONAL - 1, "final_equity": final,
        "cagr_252": (final / NOTIONAL) ** (252 / len(indices)) - 1,
        "max_drawdown": drawdown, "sell_transactions": transactions, "stops": stops,
        "turnover_notional": turnover / NOTIONAL, "weekly_decisions": decisions,
        "spy_adjusted_close_return_context": spy_end / spy_start - 1,
    }
