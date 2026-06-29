# Day-Trading Strategy Research Brief — 2026-06-29

Purpose: choose the next strategies for the Agentic Trading Lab based on research-backed, testable intraday edges rather than retail folklore. This is for a $200 paper/fake account first, then Alpaca paper orders later, then live only after explicit approval.

## Current bot state

The active loop is **paper/proposal only**:

- Uses Alpaca 1-minute market data.
- Scans a fixed large-cap/ETF watchlist every 5 minutes during market hours.
- Current implemented strategy: 5-minute Opening Range Breakout (ORB).
- Logs proposals and simulated paper positions to local SQLite.
- No broker orders.
- No Robinhood MCP.
- Paper budget: `$200`.
- Default risk: `1%` = `$2` per setup.
- Max position notional: `2x equity` = `$400`.

## Source notes

### 1. Stocks-in-play Opening Range Breakout

Source: Concretum Group summary of Zarattini, Barbon, Aziz, "A Profitable Day Trading Strategy For The U.S. Equity Market".

Key facts from the source:

- Tests more than 7,000 U.S. stocks from 2016–2023.
- Focuses on 5-minute ORB while comparing 15/30/60-minute ranges.
- Performance improves by restricting to **Stocks in Play**: unusual activity from news, earnings, or fundamental catalysts.
- Reported top-20 Stocks-in-Play ORB portfolio:
  - More than 1,600% total net return.
  - Sharpe ratio 2.81.
  - Annualized alpha 36%.
- S&P 500 passive comparison around 198% total return for the same period.

Interpretation for our lab:

- ORB is worth keeping, but **not as a generic every-ticker breakout detector**.
- The edge likely depends heavily on relative volume/catalyst filters.
- Our current fixed watchlist is acceptable for smoke testing, but not enough for real evaluation.

Implementation implication:

- Add a Stocks-in-Play candidate universe:
  - high relative volume,
  - opening gap,
  - abnormal premarket/open volume,
  - earnings/news later when data source exists,
  - price/liquidity filters compatible with a $200 account.

### 2. SPY intraday momentum with dynamic trailing stops

Source: Concretum Group summary of Zarattini, Aziz, Barbon, "Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)".

Key facts from the source:

- Applies systematic intraday momentum to SPY from 2007 to early 2024.
- Detects abnormal demand/supply imbalances during the trading day.
- Uses dynamic trailing stops.
- Reported results net of costs:
  - 1,985% total return,
  - 19.6% annualized return,
  - Sharpe ratio 1.33.
- Includes commissions/slippage.
- Examines volatility regimes and dealer gamma imbalance effects.

Interpretation for our lab:

- This is highly implementable because it can run on SPY/QQQ only.
- Better fit for small account constraints than scanning thousands of stocks.
- Needs dynamic stop logic rather than fixed 2R only.

Implementation implication:

- Build a `spy_intraday_momentum` strategy:
  - trade SPY/QQQ only initially,
  - detect abnormal move from open / previous intraday volatility,
  - require volume confirmation,
  - trailing stop using VWAP or ATR-like intraday bands,
  - flat by end of day.

### 3. VWAP trend / imbalance strategy

Source: Concretum Group summary of Zarattini and Aziz, "Volume Weighted Average Price (VWAP) The Holy Grail for Day Trading Systems".

Key facts from the source:

- Tests VWAP-based day trading on QQQ and TQQQ from 2018-01-02 to 2023-09-28.
- Strategy enters long when price trades above VWAP and short when price moves below VWAP.
- QQQ reported results:
  - $25,000 grew to $192,656,
  - 671% total return,
  - 9.4% max drawdown,
  - Sharpe 2.1.
- Passive QQQ comparison:
  - 126% return,
  - 37% max drawdown,
  - Sharpe 0.7.
- TQQQ version reported much higher returns but uses leverage exposure.

Interpretation for our lab:

- VWAP is a serious candidate and directly supported by current indicator code.
- We should avoid TQQQ at first because the user explicitly wants no leverage-style stupidity initially. TQQQ is not margin, but it is leveraged exposure, so defer it.
- QQQ/SPY VWAP trend is a cleaner small-account test.

Implementation implication:

- Build `vwap-trend-imbalance` next:
  - QQQ/SPY first,
  - long if price/VWAP relationship, slope, volume, and trend filter agree,
  - short only after separate validation; long-only first is safer,
  - dynamic stop near VWAP or intraday volatility band,
  - simulated lifecycle and metrics.

### 4. Gap-and-go

Research status:

- Common retail/institutional momentum setup.
- Usually overlaps with Stocks-in-Play ORB and VWAP continuation.
- Standalone blog claims vary wildly and are less reliable than the ORB/VWAP/SPY momentum papers.

Interpretation for our lab:

- Do not implement as an isolated vibes strategy.
- Implement as a **filter or setup type** inside Stocks-in-Play ORB/VWAP:
  - significant gap,
  - high relative volume,
  - price holds above VWAP,
  - opening range break confirms.

### 5. Mean reversion after opening range

Research status:

- Some analyses suggest opening-range behavior changes by range size: very small or very large ranges can trend, mid-sized ranges may revert.
- This is regime-dependent and easy to overfit.

Interpretation for our lab:

- Do not build first.
- Keep as a later experiment after we have robust ORB/VWAP metrics.

## Strategy priority ranking

### Priority 1 — Improve ORB into Stocks-in-Play ORB

Why:

- Directly supported by the strongest stock-specific study.
- We already have a primitive ORB scanner.
- Biggest improvement is not code complexity; it is universe/catalyst filtering.

Needed upgrades:

1. Relative volume / abnormal volume filter.
2. Gap filter.
3. Liquidity and price filters for `$200` account:
   - no penny stocks,
   - no illiquid trash,
   - max notional guard already exists,
   - avoid absurd tight stops.
4. Strategy variants:
   - 5m ORB,
   - 15m ORB,
   - VWAP-confirmed ORB.
5. Backtest harness.

### Priority 2 — VWAP trend/imbalance on QQQ/SPY

Why:

- Strong reported QQQ performance.
- Uses already available 1-minute OHLCV.
- Better small-account fit than broad stock scanning.

Needed upgrades:

1. Intraday VWAP series per symbol.
2. VWAP slope / reclaim / rejection scanner.
3. Dynamic stop logic.
4. End-of-day flattening in paper lifecycle.
5. QQQ/SPY-only initial universe.

### Priority 3 — SPY/QQQ intraday momentum with dynamic trailing stop

Why:

- Strong long-term SPY evidence.
- Small account friendly.
- Lower universe/data complexity.

Needed upgrades:

1. Intraday deviation bands from recent historical intraday bars.
2. Dynamic trailing stop, likely VWAP or volatility-band based.
3. Regime filters: volume/volatility day, avoid dead chop.

### Priority 4 — Gap-and-go as a confluence filter

Why:

- Useful only when combined with volume/catalyst/VWAP/ORB confirmation.

### Priority 5 — Mean reversion regime tests

Why:

- Could be useful, but more likely to overfit early.

## Immediate implementation plan

### Step A — Keep current ORB watcher running

It is useful for plumbing verification:

- market data works,
- scheduler works,
- journal works,
- lifecycle simulation works,
- local model review works.

But do **not** conclude strategy quality from this fixed-watchlist version.

### Step B — Build VWAP trend/imbalance scanner next

Reason: it is research-backed and easiest to implement correctly with current data.

Minimum viable rules:

Long candidate:

- symbol in `QQQ, SPY` initially,
- price above VWAP,
- VWAP slope positive over recent window,
- close is meaningfully above VWAP, not one tick above,
- volume above recent intraday baseline,
- stop below VWAP or recent swing/volatility band,
- target or trailing stop expressed in R.

Short candidate later, not first:

- price below VWAP,
- VWAP slope negative,
- volume confirms,
- avoid shorting major uptrend days until tested.

### Step C — Improve ORB with Stocks-in-Play filters

After VWAP scanner:

- compute opening gap,
- compute relative open volume,
- replace fixed watchlist with filtered universe if Alpaca data allows enough symbols without API pain,
- otherwise maintain curated large-cap/high-volume list and add relative-volume ranking.

### Step D — Add backtest harness before broker paper orders

We need historical replay for:

- ORB 5/15/30/60 min,
- VWAP trend,
- SPY/QQQ momentum,
- fixed stop vs trailing stop,
- $200 account constraints.

Metrics:

- trade count,
- R expectancy,
- profit factor,
- max drawdown,
- win/loss distribution,
- rule adherence,
- average notional,
- rejected setups by reason.

## Recommendation

Do not jump to broker paper orders yet.

Next best engineering move:

1. Implement `vwap_trend_imbalance.py`.
2. Add tests.
3. Add scanner integration into the paper loop.
4. Log strategy ID separately from ORB.
5. Run both ORB and VWAP in proposal mode for a few sessions.
6. Build backtest harness.
7. Only then enable Alpaca paper orders.

The current watcher stays on as plumbing/telemetry. Strategy development now shifts from “ORB smoke test” to “research-backed scanner bench.”
