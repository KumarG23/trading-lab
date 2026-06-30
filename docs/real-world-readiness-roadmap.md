# Agentic Trading Lab — Real-World Readiness Roadmap

This roadmap is the build contract for turning the current proposal-mode bot into a real-world-capable trading lab without handing an LLM a brokerage flamethrower.

## Current phase

**Phase 1: proposal-mode systematic research**

- Alpaca market data only.
- Deterministic strategy scanners produce proposals.
- Local/paper lifecycle simulates entries/exits.
- No broker orders.
- No live trading.
- Active strategies: `opening-range-breakout`, `vwap-trend-imbalance`.

## Target architecture

```text
market data -> strategy suite -> risk gate -> paper lifecycle/backtest -> journal -> metrics/dashboard -> AI review
                                                  |
                                           broker-paper adapter later
                                                  |
                                      human-approved tiny live trades later
```

AI is research/review/control-plane support. Deterministic code owns signal generation, position sizing, risk gates, execution permissions, and audit logs.

## Readiness gates

### Gate A — research-grade proposal bot

Required:

- Historical replay/backtest harness using the same strategy code as live proposal mode.
- EOD flattening and no-new-trade cutoff rules.
- Slippage/spread assumptions in backtests.
- Strategy-level metrics: expectancy R, profit factor, drawdown, trade count, rule adherence.
- Dashboard/API showing bot status, proposals, positions, metrics, scanner watchlist, and readiness.

### Gate B — broker-paper execution

Required after Gate A:

- Alpaca paper order adapter.
- Order lifecycle table: proposed -> approved -> submitted -> accepted/rejected -> filled/partial -> closed/cancelled.
- Broker reconciliation: local positions/orders must match broker state.
- Duplicate order lock.
- Limit-order-only default.
- Kill switch if reconciliation fails.

### Gate C — human-approved live micro trades

Required after broker-paper execution behaves:

- Explicit Neal approval per trade: ticker, side, order type, quantity/notional, limit price if any, and thesis.
- Tiny max trade notional.
- Max two trades/day.
- Allowed symbols only.
- No options, crypto, margin, penny stocks, or illiquid securities.

### Gate D — constrained autonomous live

Only after statistically meaningful logged performance:

- One pre-approved strategy at a time.
- Smallest practical sizing.
- Strategy kill switches.
- Global kill switch.
- Daily review and weekly promotion/demotion.

## Strategy roadmap

1. ORB -> stocks-in-play ORB
   - Add gap, relative-volume, liquidity, and VWAP-confirmation filters.
   - Test 5/15/30 minute variants.

2. VWAP trend/imbalance
   - Keep long-only SPY/QQQ first.
   - Add dynamic stop/trailing stop experiments.
   - Consider short variant only after backtest proof.

3. SPY/QQQ intraday momentum
   - Add intraday volatility/deviation bands.
   - Require volume/regime confirmation.
   - End flat by EOD.

4. Gap-and-go/fade
   - Only as confluence inside stocks-in-play workflows.

5. Mean reversion
   - Later, regime-gated, overfit-prone.

## Dashboard goals

The dashboard should be visual-first and boringly truthful:

- Today's dynamic scanner watchlist.
- Top scanner matches and reasons.
- Bot mode and safety state.
- Active simulated positions.
- Today’s proposals by strategy.
- Closed paper trades and R/PnL.
- Strategy metrics.
- Readiness checklist.
- Latest proposals/trades.
- No broker orders until explicitly enabled.

## Non-negotiables

- No live trading without explicit trade-level approval.
- No prompt-only risk controls.
- No strategy promotion without logs and metrics.
- No AI in the inner execution loop.
- Every proposal/trade/rejection must be journaled.
