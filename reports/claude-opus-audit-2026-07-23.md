I have enough evidence from the code, diff, and passing tests. Writing the audit now.

# Trading-Lab Adversarial Audit — 2026-07-23

All findings labelled **[verified]** were confirmed by reading the referenced source; **[hypothesis]** items are plausible risks I did not exhaustively prove. Line numbers refer to files at HEAD + uncommitted diff. Full test suite passes (75 passed).

---

## 1. Dual research/portfolio design — correctness review

The design intent is: every gate-approved, non-duplicate candidate becomes a research paper position; only up to `max_active_positions` become "portfolio_admitted"; portfolio-lane risk breakers are computed only from portfolio-admitted trades; research keeps flowing after portfolio-lane loss caps trip.

### What is implemented correctly [verified]
- Two independent risk-state computations in `autonomous_runner.py:74-75`, driven by a new `portfolio_only` filter in `_risk_state` (lines 166-190).
- `portfolio_admitted` flag persisted on the proposal `rule_checklist` (line 121).
- Portfolio slot accounting only counts `portfolio_admitted` active positions (`_active_portfolio_count`, lines 156-164).
- Slot decrement guarded by `portfolio_admitted` (line 151).
- Research capture continues after a large portfolio-lane loss — proven by the new test `test_autonomous_runner_keeps_research_capture_running_after_portfolio_loss_breaker`.

### Concrete bugs and misleading semantics

**P0-A [verified] — Dashboard and daily summary conflate research + portfolio into one fantasy equity curve.**
`dashboard_data.py:36` (`metrics = summarize_trades(attributed_trades)`) pools every closed paper_trade regardless of `portfolio_admitted`. `trading_lab_progress_report.py:66-68` computes `total_r` / `total_pnl` over *all* `closed_today` positions. The reported PnL and drawdown therefore claim you traded 50 correlated ORB longs on the same day even though only two were meant to be tradeable. This directly contradicts the stated goal of avoiding "fantasy portfolio metrics" and is the single most important reporting bug this diff introduces.

**P0-B [verified] — The "50 trades/day" cap is not what its name promises.**
`_risk_state` counts entries in `paper_trades`, and rows are only inserted at *close* (`journal_store.close_position:334`) or on manual logging. So `trades_today` is closes-today, not proposals-today. On a fast day where ORB candidates enter and exit within minutes, this cap can silently allow far more than 50 new *proposals*. If the intent is a proposal runaway cap, count against `proposals` created today; if the intent is a close cap, rename it.

**P0-C [verified] — Portfolio breaker is decided per-tick from a stale snapshot.**
`portfolio_daily_loss` is computed once at the top of `process_candidates` (line 75). If a portfolio-admitted position closes mid-tick (it won't, but on future async loops it will), the second admission in the same tick won't see the fresh loss. Small issue today, latent bug once the loop is not strictly serial.

**P0-D [verified] — Dedupe window makes the 50/day cap almost irrelevant, but also destroys legitimate independent re-entries.**
`recent_duplicate_proposal` uses `within_minutes=390` (the whole session) and `_close_enough(tolerance=0.0025)`. Because ORB triggers at the range-high break at a specific close price, a follow-up break after a shakeout will usually be within 25 bps → suppressed. Same-day retest/re-break of ORB is a *different* independent event; this filter treats it as noise. Fix: shorten to ~30 minutes and/or make dedupe key strategy-aware (ORB dedupe already handled by `latest_only` semantics).

**P1-E [verified] — Portfolio lane bias toward under-sampled strategies.**
`process_candidates` sorts by `(strategy_count, strategy_id, ticker)` (lines 66-73). Because portfolio admission is first-come, portfolio positions are systematically taken from *whatever is currently rarest*, not from whatever is best. This is fine for research diversity but is misleading if you treat portfolio-lane returns as a proxy for a "real trader's" selection.

**P1-F [verified] — Research positions still write to the same `paper_positions` table with no lane flag on the position itself.**
The `portfolio_admitted` marker lives only on the proposal's rule_checklist JSON. Every consumer that wants portfolio-only data has to join proposals → positions → JSON-parse. `_active_portfolio_count` does this in-Python; downstream reports don't. Add a column (`paper_positions.lane TEXT NOT NULL DEFAULT 'research'`) or a normalized flag; JSON-only markers rot fast.

**P1-G [verified] — Reporting counts of "active positions" mix lanes.**
`daily_summary` `active_positions` (script line 107, dashboard line 51) counts pending_entry+open across both lanes. Snapshot cards under-count and over-count depending on which side you're reading. Split explicitly.

**P2-H [verified] — `_active_portfolio_count()` and `_risk_state(portfolio_only=True)` each call `store.list_proposals()` and re-index in Python.**
Two full-table scans per tick. Not urgent at journal sizes today, but on a busy month you'll pay a linear cost per candidate — the sort at line 66 also full-scans. Bounded, but replace with SQL when it starts to hurt.

**P2-I [verified] — Portfolio slot cannot be freed by expiring a stale pending_entry within the same tick.**
The lifecycle runs first (`run_orb_proposals.py:76`), so it drops expired positions before the runner samples `_active_portfolio_count`. Currently OK. Just document the ordering constraint — a subtle bug is one refactor away.

---

## 2. Is `max_active_positions=2` a good default for a future $200 account?

Distinguishing throughput from deployable exposure:

**Research throughput:** Uncap it. Every gate-passing, non-duplicate candidate should be resolved. `max_active_positions` should have no bearing on evidence collection — the diff already achieves this. Good direction.

**Deployable portfolio [verified concerns]:**
- With `max_position_notional_pct=2.0` in `policy_gate.py:47`, one position may take **2× account equity in notional**, i.e. $400 on $200 cash. Two concurrent positions = $800 notional on $200 cash. That is only possible with margin. For a cash account, `max_position_notional_pct` must be ≤ 1.0 and the sum across concurrent positions must be ≤ available cash. There is no aggregate-notional check anywhere.
- With `max_risk_pct=0.01` and $2 risk-per-trade, two concurrent slots means 2% peak risk, plausible.
- ORB and VWAP-reclaim on tech names are highly correlated intraday. Two "diversified" longs during a SPY rip are basically one bet at 2× size. Concurrent = correlated-doubled exposure.

Recommendation: for a real $200 deploy, `max_active_positions=1` and `max_position_notional_pct=1.0` (buy with cash you have). Only widen to 2 when you have positions from clearly uncorrelated strategies (e.g. one long trend + one mean-reversion short in a hedge-eligible product), which you don't yet.

---

## 3. Highest-leverage improvements to strategy discovery / evidence quality

Ranked by expected impact per unit engineering:

1. **Report metrics split by lane and by regime.** Today the aggregate expectancy is misleading. Split (research vs portfolio_admitted) × (bullish_regime vs everything). Also cluster trades by (strategy, day) and report per-day expectancy, not per-trade — this collapses the intra-day correlation that inflates confidence.
2. **Kill same-day, same-setup duplicate suppression at 390 minutes.** Move to a per-strategy window (ORB: use "one per session" via strategy semantics, not dedupe; VWAP-reclaim: 20 min; momentum-pullback: 15 min). Independence improves and sample throughput on trending days rises.
3. **Add slippage/spread assumptions to paper_lifecycle**, not just backtest. Right now proposal-mode simulations fill at *the exact stop or target price* with zero slippage, which is fantasy on 1-min data. At minimum: charge 3 bps entry + 3 bps exit + 1 bps commission-equivalent. The reported R will change materially.
4. **Cluster overlapping signals.** When ORB long AAPL + VWAP-reclaim long AAPL fire within N minutes, treat as one sample, not two. Otherwise "50 trades" is really "10 setups × 5 correlated views."
5. **Introduce walk-forward evaluation** by session (not shuffled trades): rolling 20-session train / 5-session test. The current `run_strategy_backtest` runs a single window with no OOS split.

---

## 4. Backtest audit

`trading_lab/backtest.py`:

**Look-ahead / time-travel [verified]:**
- `_generate_replay_candidates` iterates timestamps and passes `visible = bars with timestamp ≤ t`, then generates with `live_latest_only=True`. The strategy uses only the last bar's close — that value is known only at bar close. `_simulate_candidate` correctly begins iterating from `ts > signal_ts`. No look-ahead in signal generation. Good.
- **However:** the entry price is `planned_entry = close(signal_bar)`. On the next bar this may or may not be trade-able (limit-order semantics). Fills are simulated by `high >= planned_entry`. This is optimistic in one direction (assumes you get exactly close-of-signal price, not a worse next-bar open) and pessimistic in another (won't fill on next-bar gap-up above planned_entry). Real-world execution would be a stop-buy at range_high — different behavior.

**Fill realism [verified]:**
- Uses only bar high/low crossing, no volume, no book depth, no partial fills. Fine for a first sieve; not fine for promotion.
- Stop-vs-target within same bar: stop wins for both directions — conservative and correct.
- Slippage: parameter exists, default 0. Not applied in live proposal loop.

**Selection / survivorship [verified]:**
- `DEFAULT_WATCHLIST` and `DEFAULT_SCAN_UNIVERSE` are hand-picked current survivors (RIVN, PLTR, RKLB, etc.). Any historical backtest using these lists is survivorship-biased. Delisted, halted, or acquired names of the era are missing.
- No universe-as-of-date support.

**Overlapping / correlated signals [verified]:**
- Backtest treats each proposal independently. Ten longs on the same up day → 10 samples, but they're one bet. Metrics inflate confidence. No de-correlation of samples anywhere.

**Regime overfitting [verified]:**
- `require_bullish_market_regime` is a boolean toggle. Never scored against its counterfactual. Enables cherry-picking of good regimes with no OOS discipline.

**Per-strategy attribution [verified]:**
- `summarize_trades` produces `by_strategy` breakdown — good.
- Rule_adherence isn't strategy-scoped anywhere; all backtest trades emit `rule_adherent: True`, so the metric is uninformative in that context.

**Intraday state reset [verified]:**
- `test_backtest_resets_intraday_state_for_each_session` proves ORB opening-range resets per session. Good.

**Missing:**
- No commissions / regulatory fees (SEC/TAF are small but non-zero).
- No borrow/locate simulation (moot until shorts).
- No PDT-rule modeling (with $200, one round-trip a day can matter; PDT ≥ $25k so not applicable in cash account, but bear in mind).

---

## 5. Strategy rules and exits

**ORB (`opening_range_breakout.py`):**
- 5-min OR, 1.5× volume confirmation, close-based break. Reasonable.
- `latest_only=True` in live mode means only the *most recent* bar can emit a break; combined with 390-min dedupe, ORB effectively fires 0-1 times per symbol per day. This is a **tight noise filter but also a huge suppressor of second-chance entries.** With volume >1.5× requirement, my expectation is <1 signal/day for most watchlist symbols on quiet days.
- Target = 2R fixed. No trailing. Common truncation-of-winners pattern.

**VWAP trend/imbalance:** restricted to SPY/QQQ, requires rising VWAP + 1.5× volume + 10 bps above VWAP. Very tight; on a chop day, will emit little to nothing. Probably fine.

**VWAP reclaim:** requires previous close below VWAP, current close above VWAP *and* above open, 1.2× volume. Reasonable. Stop = min(prev.low, curr.low). This can be quite tight and lead to STOP_TOO_TIGHT / POSITION_TOO_LARGE gate rejections.

**Momentum pullback:** touches VWAP within 20 bps, holds VWAP on close, resumes above prior bar high, 1.2× volume, rising VWAP. Reasonable trend-continuation pattern.

**EOD/entry-cutoff interaction [verified concern]:**
- Diff extended `no_new_entries_after` from 11:30 → 15:30, but `flatten_at` stayed at 15:45. A position triggered at 15:29 has 16 minutes before forced EOD flatten. That trade is almost guaranteed to close on `eod_flatten` reason at an arbitrary price, not on stop/target. R is meaningless for these. **Expected effect: a large fraction of the new "extra" candidates the extension unlocks will resolve via EOD flatten and pollute R statistics.** Either shorten the cutoff (13:30–14:00) or lengthen flatten (16:00) and hold overnight-safe carve-outs.
- `eod_flatten` closes at `last_bar["close"]`, which may be minutes stale relative to `now`. Documented behavior; noteworthy.
- The `pending_entry` cutoff correctly expires; good.

**Filter suppression vs. noise admission:**
- ORB + reclaim + momentum-pullback all require volume confirmation → collectively low-noise but very sparse. Sample size will be small even with the new caps.
- Bullish-regime filter drops *all* longs when SPY is under a rising VWAP, which is nearly all longs today. Fine as a bias but recognize that this makes bearish/chop days silent — you get no data on how strategies would have done in adverse regimes.

---

## 6. Promotion gates (proposal → broker-paper → tiny real money)

Concrete gates I would enforce. Sample sizes assume clustered (per-session) counts, not per-trade.

**Gate A → Broker-paper (per strategy):**
- ≥ 60 independent trading sessions with at least one qualifying signal, spanning ≥ 2 distinct regime buckets (bullish/rising-VWAP vs. everything else).
- Per-strategy expectancy ≥ +0.15R after 3 bps entry / 3 bps exit slippage.
- Profit factor ≥ 1.25.
- Max session-clustered drawdown ≤ 6R.
- ≤ 20% of closes on `eod_flatten` reason (otherwise you don't know your exit distribution).
- Walk-forward: out-of-sample expectancy within 30% of in-sample.
- **Operational:** dashboard shows lane-split metrics; alerts on missed loop ticks; explicit "quarantine last N days" workflow exercised at least once.

**Gate B → Tiny real money (per strategy):**
- ≥ 30 broker-paper live trading sessions with the *same* code path used for real orders, order-lifecycle table populated end-to-end, reconciliation clean.
- Slippage measured, not assumed. Actual fills within 15% of modeled fills for ≥ 90% of trades.
- Duplicate-order lock proven under fault injection.
- Kill switch pulled and re-armed at least once in drill.
- Explicit human trade approval flow signed off.
- Real-money cap ≤ $50 notional per trade, ≤ 2 trades/day, ≤ 1 open position.

**Gate C → Autonomous small money:** requires 60 real-money trading days on Gate B with expectancy consistent within 40% of paper.

Do not go real-money on the current sample.

---

## 7. Missing tests and observability

**Missing tests:**
- Lane-split metrics: dashboard/daily summary must report portfolio-only PnL/R.
- Portfolio breaker while research is still flowing (partially added — extend to daily loss and weekly loss).
- Dedupe interaction with portfolio_admitted (dedupe should apply to both lanes; verify).
- EOD flatten timing and pricing correctness.
- Slippage applied in live proposal path (once added).
- Aggregate notional cap across concurrent portfolio positions.
- Backtest walk-forward split.
- Regime-filter counterfactual: same run with/without regime filter, per-strategy expectancy.

**Missing observability before broker-paper execution:**
- Per-lane counters: proposals, admits, entries, wins, losses, PnL, R.
- Loop-miss detection (last successful scan age).
- Signal-to-fill latency (already partially in `timings_ms`).
- Fill realism monitor (backtest-expected vs. simulated).
- Duplicate proposal suppression rate — how often is dedupe firing? Is it too tight?
- Rule-adherence rate stratified by strategy and exit_reason.
- `eod_flatten` fraction per strategy.
- Broker reconciliation (once broker path exists): stateful diff of local vs. Alpaca positions/orders.
- Kill-switch endpoint and last-heartbeat file.

---

## 8. Ranked action plan

### P0 — correctness
1. **Split reporting by lane.** Fix `dashboard_data.build_dashboard_snapshot` and `trading_lab_progress_report`/`daily_summary` to report portfolio-only metrics as primary and research-only as secondary. Stop publishing a pooled expectancy.
2. **Fix `max_trades_per_day` semantics.** Either rename to `max_closes_per_day` or count proposals-today. Current name is misleading and will silently allow proposal runaways.
3. **Add lane column to `paper_positions`** so downstream queries don't rely on JSON parsing.
4. **Cap aggregate portfolio notional at ≤ account cash** in `PolicyGate` for a cash account. Today two concurrent positions × `max_position_notional_pct=2.0` implies leverage that a $200 cash account cannot support.
5. **Shorten entry cutoff or lengthen EOD flatten** so extended-hours entries don't dominate closes via `eod_flatten`. The 15:30/15:45 combo is a fifteen-minute holding-period trap.

### P1 — evidence quality
6. **Session-clustered per-day metrics** replace naive per-trade averages.
7. **Add slippage/spread modeling to `paper_lifecycle`** (not just backtest).
8. **Tighten dedupe** to ~30 min and let strategies gate re-entries themselves; this raises independence without duplicating noise.
9. **Regime-split reporting** with the counterfactual (no-filter) run alongside.
10. **Walk-forward split in `run_strategy_backtest`** with rolling train/test.

### P2 — strategy improvements
11. Partial exits / trailing stops (take 50% at 1R, trail remainder).
12. Universe-as-of-date support so historical backtests are not survivorship-biased.
13. Correlation-aware admission: if two portfolio candidates are on correlated tickers/sectors within N minutes, admit one.
14. First-hour vs. midday vs. power-hour bucketing of ORB/reclaim to detect time-of-day edges.

### P3 — execution readiness
15. Order-lifecycle table, duplicate-order lock, and broker reconciliation adapter before any `broker_orders > 0`.
16. Kill switch and heartbeat monitor.
17. Fault-injection tests for network partitions and duplicate submissions.
18. Explicit per-trade approval flow with signed rationale.

**No live trading recommended.** Evidence base is thin, metrics are currently misleading (P0-A), fill realism is toy-grade, and exposure math for a $200 cash account is unsafe until aggregate notional is capped. Once P0 is closed and the walk-forward evidence base per Gate A is in place, revisit Gate B; only then consider tiny real-money.

---

## Post-fix verification

After Jarvis implemented the immediate corrections, Claude Opus 4.7 re-read the working tree and reported **NO_P0_BLOCKERS**. Verified corrections:

- The 50/day research guard now counts proposals and cannot be overshot within one tick.
- Dashboard and daily reports split research from portfolio-admitted metrics.
- Near-duplicate suppression is 30 minutes instead of a full session.
- New entries stop at 14:30 ET, with an explicit pre-runner cutoff guard.
- Full suite passed with 78 tests.

Deferred P1 work remains: aggregate cash/notional enforcement before broker orders, normalized lane storage, modeled proposal-mode slippage, session-clustered/regime metrics, walk-forward evaluation, correlation-aware admission, and execution/reconciliation infrastructure.