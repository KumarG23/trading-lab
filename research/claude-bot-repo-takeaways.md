# Claude_Bot Repo Takeaways

Source inspected: `sharm@r16.tailc88c35.ts.net:C:\code\Claude_Bot`

Date: 2026-06-29

## Executive summary

The old bot is useful, but not as a template for live agentic trading. It is a good fossil record of what worked and what burned money: it used Claude as the primary decision loop, called it constantly, logged a lot, and gradually accreted safety patches after real failure modes appeared.

For the new Agentic Trading Lab, steal the scaffolding, not the architecture.

Use deterministic scanners/backtests/journals first. Use local Qwen/Qwen3.6 for private journal review. Use Codex for tooling. Use frontier/cloud models only for occasional review, not every symbol tick.

## Repo shape

Python app using:

- Alpaca for paper/live trading and market data
- Anthropic Claude as the decision brain
- SQLite for decision/trade/fill/evaluation memory
- APScheduler for stock/crypto cycles
- Telegram alerts
- strategy modules for momentum, VWAP, panic dip, Minervini, Wyckoff, short momentum, defense mode

Important files:

- `main.py` — scheduler, cycle orchestration, kill switch, symbol routing
- `brain/decision_engine.py` — Anthropic calls, retries, JSON retry, prompt/response capture
- `brain/output_parser.py` — JSON extraction and validation
- `brain/prompts.py` — large standing system prompt
- `data/context_builder.py` — per-call prompt context assembly
- `data/scanner.py` — Alpaca open scanner and candidate filters
- `memory/trade_log.py` — SQLite schema and decision/trade/fill/evaluation tables
- `memory/performance.py` — win rate, profit factor, avg win/loss, symbol/setup breakdowns
- `memory/evaluator.py` — end-of-day self-evaluation call
- `execution/order_manager.py` — Alpaca order placement/fill handling/fallbacks
- `config/risk_rules.py` — hard-coded risk limits

## Empirical burn evidence

Sanitized DB aggregate from `data/trades.db`:

- `decisions`: 3,670
- `fills`: 84
- `trades`: 17
- `daily_stats`: 13 days
- logged Claude calls in `daily_stats`: 2,742
- estimated tracked cost: about `$17.71`, but earlier days had cost set to `$0.00`, so the real total was undercounted
- prompt average: 10,381 characters
- prompt p90: 11,939 characters
- prompt max: 16,982 characters
- response average: 1,807 characters

Decision distribution:

- crypto holds: 2,657
- stock holds: 947
- crypto sells: 31
- stock sells: 25
- crypto buys: 5
- stock buys: 5

That is the smoking crater: thousands of full Claude calls, mostly to say `hold`.

## What worked and should be reused

### 1. Journal-first architecture

The SQLite ledger is the best part:

- `decisions` records every model decision, including holds
- `fills` records execution results separately
- `trades` records round-trips
- `daily_evaluations` stores end-of-day review
- `daily_stats` tracks model calls/cost
- `daily_watchlist` stores watchlist selection context

For the new lab, we should keep the separation between:

```text
proposal/decision -> execution/fill -> trade/outcome -> review/evaluation
```

But we should adapt the schema to paper/proposal mode and R-multiple metrics instead of live Alpaca-first execution.

### 2. Deterministic risk enforcement after model output

`brain/output_parser.py` parses model JSON and rejects invalid/risky decisions. That is correct. The model proposes; code disposes.

New lab rule: no model output should be directly actionable until deterministic gates verify:

- allowed asset universe
- entry/stop/target present
- stop distance valid
- risk per trade within policy
- daily/weekly drawdown gates
- liquidity/spread checks
- strategy ID exists and matches rules
- no banned instruments

### 3. Strategy modules as explicit lenses

The old bot had modules for:

- momentum
- VWAP bounce
- panic dip
- short momentum
- Minervini
- Wyckoff
- defense mode

The useful pattern is not the exact strategies. The useful pattern is: each strategy returns structured evidence, stop guide, target guide, time window, and notes.

For `~/trading-lab`, this should become strategy YAML + deterministic Python evaluator modules.

### 4. Scanners before reasoning

The old scanner did something right: narrow the universe before expensive analysis.

Reuse the concept:

1. deterministic scanner finds candidates
2. deterministic strategy evaluator scores rules
3. only then model reviews a compact proposal, if needed

Never ask a model to think deeply about every symbol every minute. That is how you build a furnace with invoices.

### 5. EOD/weekly review loop

`memory/evaluator.py` and `memory/summarizer.py` are conceptually useful:

- daily review
- lessons learned
- tomorrow plan
- repeated mistake detection
- recent self-evaluation injected into future context

For the new lab: local Qwen/Qwen3.6 should own this. Private logs stay local; cloud model only sees sanitized summaries if we explicitly choose.

### 6. Capturing prompts/responses for training data

`trade_log.py:get_training_pairs()` stores full prompt/response pairs. Good instinct.

For the new lab, capture compact structured examples instead:

```json
{
  "strategy_id": "opening-range-breakout",
  "features": {...},
  "proposal": {...},
  "outcome": {...},
  "rule_adherent": true,
  "mistake_category": null
}
```

Better training/eval data, less prompt sludge.

## What not to reuse

### 1. Claude as the inner loop

The old bot used Claude for recurring per-symbol decisions. DB evidence says most calls produced holds. That is expensive and not especially informative.

New rule: models do not run on a fixed tick. Models run on events:

- scanner hit
- strategy rule match
- position risk event
- post-trade review
- EOD/weekly analysis

### 2. Giant repeated context blocks

`context_builder.py` assembled 8–12 sections every call: portfolio, indicators, news, fees, risk, settlement, PDT, memory, macro regime, strategy, symbol history, self-evals, repeated rule violations.

That explains the 10k+ character average prompt. The prompt was doing the job of a state machine.

New design: keep state in code/data. Send models compact feature objects and concise summaries, not the whole catechism every time.

### 3. Prompt-only discipline

The old prompt repeatedly tells Claude not to average down, not to violate PDT, not to hold losers, etc. The fact that later code added hard stops, cooldowns, trim tracking, stale-loser warnings, and PDT gates tells us the lesson: prompt instructions are advisory. Deterministic gates are real.

### 4. Crypto/options-like chaos in phase one

Old bot mixed stocks and crypto and spent many calls on 24/7 crypto watchlists. Our current policy explicitly bans crypto at first. Keep it that way. Otherwise the lab becomes a casino that never sleeps.

### 5. Live execution architecture as phase-one default

The order manager is useful historical reference, but too execution-forward for current phase. Current lab is proposal/paper mode only.

## Specific components to port/adapt

### Port soon

1. `memory/performance.py` concepts
   - profit factor
   - avg win/loss
   - by-symbol breakdown
   - by-setup breakdown
   - streaks

2. `memory/trade_log.py` schema ideas
   - separate proposal/decision/fill/trade/review tables
   - daily model call/cost stats
   - prompt/response capture, but compacted

3. `data/indicators.py`
   - EMA
   - RSI
   - MACD
   - VWAP
   - volume profile

4. `data/scanner.py` ideas
   - open scanner
   - mover filters
   - derivative/warrant filters
   - fallback universe

5. `brain/output_parser.py` pattern
   - tolerant JSON extraction
   - strict validation
   - hard rejection path

### Port later / maybe

- `execution/pdt_tracker.py` — PDT rules changed and Robinhood-specific handling will differ
- `execution/settlement_tracker.py` — useful if cash-account live trading happens later
- `execution/order_manager.py` — only after Robinhood MCP read-only and approval guards exist
- `memory/evaluator.py` — rewrite for local Qwen, R-multiples, and rule adherence

### Do not port directly

- Anthropic `DecisionEngine` as the main decision loop
- crypto watchlist/24-7 cycle
- giant per-symbol Claude prompts
- live Alpaca execution path
- old risk constants as-is

## New lab design implication

Recommended architecture:

```text
market data / imported bars
  -> deterministic scanners
  -> strategy rule evaluators
  -> proposal objects
  -> journal
  -> metrics scripts
  -> local Qwen review
  -> Jarvis risk summary
```

Cloud/paid model use should be reserved for:

- strategy design review
- code review
- suspicious result investigation
- occasional second opinion

It should not be in the scan loop.

## Immediate next builds for ~/trading-lab

1. Create SQLite schema mirroring the useful parts of `Claude_Bot`, adapted for proposal/paper mode.
2. Build `analysis/journal_metrics.py` for expectancy, R-multiple, drawdown, profit factor, and adherence.
3. Port indicator functions into `scripts/indicators.py` or `analysis/indicators.py`.
4. Build a scanner/backtest harness for opening range breakout first.
5. Build a local-model review script that sends only compact journal summaries to Qwen/Qwen3.6.
6. Add model-call accounting from day one, even for local/cloud split.

## Core lesson

The old bot was impressive, but it asked Claude to be trader, scanner, risk manager, journal analyst, and adult supervision. That is too much expensive priesthood.

The new lab should make code the machine, local models the analyst, Codex the builder, and Jarvis the risk governor.

The goblin may trade later. First, it learns to keep books.
