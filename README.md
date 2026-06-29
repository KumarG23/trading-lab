# Agentic Trading Lab

Small-money, high-risk, fun day-trading research lab. Controlled market goblin science, not retirement planning.

## Mission

Use local Qwen/Qwen3.6 plus Codex to discover, test, journal, and improve risky short-term/day-trading strategies while minimizing paid API burn.

Jarvis is the orchestrator and risk governor. Codex builds scanners, backtests, journals, and analysis scripts. Local models handle private trade logs, pattern review, and account-aware analysis where possible.

## Current phase

Phase 1: research / paper / proposal mode only.

No Robinhood MCP connection. No live orders. No OAuth-enabled slot machine. The goblin remains in a terrarium.

## Initial folder structure

```text
~/trading-lab/
  README.md
  policy/
    risky-mode-policy.md
  strategies/
    opening-range-breakout.yaml
    vwap-reclaim-rejection.yaml
    momentum-pullback.yaml
  journal/
    journal-schema.json
    trades.csv
    proposals.csv
    daily-reviews/
    weekly-reviews/
  data/
    raw/
    processed/
    backtests/
  scanners/
  backtests/
  analysis/
  prompts/
    local-model-review.md
    codex-build-brief.md
  reports/
  scripts/
```

## Initial operating loop

1. Define a strategy as explicit rules in `strategies/*.yaml`.
2. Codex builds or updates scanner/backtest/journal scripts.
3. Generate paper/proposal trades only.
4. Log every proposal and outcome into `journal/trading-lab.db`.
5. Run deterministic metrics: R, expectancy, drawdown, profit factor, rule adherence.
6. Local Qwen/Qwen3.6 reviews compact journal summaries privately.
7. Jarvis summarizes evidence and promotes, revises, or kills strategies.

## Implemented local tooling

```text
trading_lab/
  indicators.py       # EMA, RSI, VWAP, volume profile
  journal_store.py    # SQLite proposal/paper/review/model-usage schema
  metrics.py          # R, expectancy, drawdown, profit factor, adherence
scripts/
  init_lab_db.py      # creates journal/trading-lab.db
analysis/
  journal_metrics.py  # prints metrics JSON from paper trades
tests/                # pytest coverage for the above
```

Initialize the local journal DB:

```bash
python3 scripts/init_lab_db.py
```

Print current paper-trading metrics:

```bash
python3 analysis/journal_metrics.py
```

## Metrics that matter

- R-multiple
- expectancy
- max drawdown
- profit factor
- win rate, but only as supporting context
- sample size
- average loss vs average win
- rule adherence
- mistake frequency

## Explicitly out of scope for now

- Options
- Crypto
- Margin abuse
- Penny stocks / microcaps
- Illiquid trash
- Fully autonomous live execution
- Robinhood MCP connection
