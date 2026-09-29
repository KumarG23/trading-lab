"""Offline V3 counterfactual outcome resolver. No broker, network, or order authority.

Plans must be fixed using decision-time evidence *before* scoring outcomes. One-minute
IEX bars can be sparse: an unobserved minute is a data gap, not a license to invent
an entry, an exit, or an end-of-day fill.
"""
from __future__ import annotations

import math
from datetime import timedelta

from .fill_engine import entry_fill_price, exit_fill, apply_slippage, round_trip_fees
from .market_calendar import ET, XNYSCalendar
from .v3_news_history import instant
from .v3_universe import ELIGIBLE

MINUTE = timedelta(minutes=1)


def resolve_outcome(plan: dict, bars: list[dict], *, as_of: str,
                    entry_slippage_bps: float = 5, exit_slippage_bps: float = 10,
                    fee_per_share: float = 0.005) -> dict:
    """Resolve a predeclared long stop-entry plan only from fully completed bars.

    A pending/data-gap result contains no P&L. This is a research counterfactual,
    not an executable portfolio return or proof of liquidity/fill probability.
    """
    decision = instant(plan["decision_at"])
    deadline = instant(plan["entry_deadline_at"])
    now = instant(as_of)
    calendar = XNYSCalendar()
    opening, closing = calendar.session_bounds(decision.astimezone(ET).date())
    entry, stop, target, shares = (plan[k] for k in ("planned_entry", "stop", "target", "shares"))
    if (plan.get("symbol") not in ELIGIBLE or not isinstance(plan.get("event_id"), str)
            or not plan["event_id"] or any(type(x) not in (int, float) or not math.isfinite(x) for x in (entry, stop, target, shares))
            or not (0 < stop < entry < target and type(shares) is int and shares > 0)
            or entry * shares > 200 or (entry - stop) * shares > 2
            or not .002 <= (entry - stop) / entry <= .05
            or target - entry < 2 * (entry - stop) - 1e-9
            or not opening <= decision < closing - timedelta(minutes=90)
            or not decision < deadline <= min(decision + timedelta(minutes=10), closing - timedelta(minutes=90))
            or any(type(x) not in (int, float) or not math.isfinite(x) or x < 0
                   for x in (entry_slippage_bps, exit_slippage_bps, fee_per_share))):
        raise ValueError("invalid V3 research plan")
    if now < decision:
        raise ValueError("as_of precedes decision")
    first = decision.replace(second=0, microsecond=0) + MINUTE
    source = {}
    for bar in bars:
        if bar.get("symbol") != plan["symbol"]:
            continue
        if bar.get("feed") != "iex":
            raise ValueError("unproven IEX bar provenance")
        stamp = instant(bar["timestamp"])
        if not first <= stamp < closing or stamp + MINUTE > now:
            continue
        values = [bar.get(k) for k in ("open", "high", "low", "close", "volume")]
        if (stamp in source or any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in values)
                or not bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]):
            raise ValueError("duplicate or invalid completed market bar")
        source[stamp] = bar
    base = {"schema": "v3-research-outcome-v1", "event_id": plan["event_id"],
            "symbol": plan["symbol"], "decision_at": decision.isoformat(),
            "mode": "offline_counterfactual_no_orders", "execution_eligible": False}
    entered = None
    entered_at = None
    clock = first
    while clock < closing:
        if entered is None and clock > deadline:
            return base | {"status": "no_fill", "net_dollars": 0.0}
        if clock + MINUTE > now:
            return base | {"status": "pending"}
        bar = source.get(clock)
        if bar is None:
            return base | {"status": "data_gap", "missing_bar_at": clock.isoformat()}
        if entered is None:
            # A gap through the target cannot be called a realistic stop-entry fill.
            if bar["open"] < target:
                entered = entry_fill_price(planned_entry=entry, direction="long", bar=bar,
                                           slippage_bps=entry_slippage_bps)
                if (entered is not None and (entered >= target or entered * shares > 200
                                             or (entered - stop) * shares > 2)):
                    entered = None
            if entered is not None:
                entered_at = clock.isoformat()
        if entered is not None:
            reason_price = exit_fill(stop=stop, target=target, direction="long", bar=bar,
                                     slippage_bps=exit_slippage_bps, allow_open_gap=clock.isoformat() != entered_at)
            if reason_price:
                reason, price = reason_price
                if reason == "target":
                    # Do not book favorable gap-through-target improvement from IEX OHLC.
                    price = min(price, apply_slippage(target, direction="long", kind="exit",
                                                      bps=exit_slippage_bps))
                return _resolved(base, entry, stop, shares, entered, entered_at, price, clock + MINUTE,
                                 reason, fee_per_share)
        clock += MINUTE
    if entered is None:
        return base | {"status": "no_fill", "net_dollars": 0.0}
    last = source[closing - MINUTE]
    price = apply_slippage(last["close"], direction="long", kind="exit", bps=exit_slippage_bps)
    return _resolved(base, entry, stop, shares, entered, entered_at, price, closing,
                     "session_close", fee_per_share)


def _resolved(base, planned_entry, stop, shares, actual_entry, entered_at, exit_price, closed_at, reason, fee):
    fees = round_trip_fees(shares, fee_per_share=fee)
    net = round((exit_price - actual_entry) * shares - fees, 4)
    planned_risk = (planned_entry - stop) * shares
    return base | {"status": "resolved", "entered_at": entered_at, "closed_at": closed_at.isoformat(),
                   "actual_entry": actual_entry, "actual_exit": exit_price, "exit_reason": reason,
                   "fees": fees, "net_dollars": net, "net_r": round(net / planned_risk, 4)}
