# Agentic Trading Lab

Small-money, high-risk day-trading research lab. This is controlled research, not retirement planning.

## Mission

Use deterministic scanners, historical replay, local analysis, and Codex-built tooling to discover, test, journal, and improve risky short-term/day-trading strategies while minimizing paid API burn.

Jarvis is the orchestrator and risk governor. Codex builds scanners, backtests, journals, and analysis scripts. Local models handle offline private trade-log review and postmortems where explicitly enabled; they do not place orders or promote strategies.

## Current phase

Phase 1: research / paper / proposal mode only.

No Robinhood MCP connection. No live orders. Broker orders remain disabled.

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
4. Log every proposal and outcome into `journal/trading-lab.db` as provenance.
5. Generate historical counterfactual evidence under `data/evidence/candidate-outcomes-v5/`.
6. Run deterministic metrics and session-ordered purged walk-forward evaluation with a final untouched holdout.
7. Jarvis reviews the model card/readiness artifacts and promotes, revises, or kills strategies only after explicit human approval.

## Implemented local tooling

```text
trading_lab/
  indicators.py       # EMA, RSI, VWAP, volume profile
  journal_store.py    # SQLite proposal/paper/review/model-usage schema
  metrics.py          # R, expectancy, drawdown, profit factor, adherence
scripts/
  init_lab_db.py      # creates journal/trading-lab.db
  evaluate_evidence.py
  weekly_evidence_review.py
analysis/
  journal_metrics.py  # prints metrics JSON from paper trades
tests/                # pytest coverage for the above
```

Initialize the local journal DB:

```bash
.venv/bin/python scripts/init_lab_db.py
```

Print current paper-trading metrics:

```bash
.venv/bin/python analysis/journal_metrics.py
```

Run bounded offline evidence diagnostics:

```bash
.venv/bin/python scripts/weekly_evidence_review.py --smoke
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

## Architecture and audits

- [`docs/target-architecture-and-profitability-roadmap.md`](docs/target-architecture-and-profitability-roadmap.md) — evidence-first target architecture and phased promotion gates
- [`reports/claude-fable5-architecture-audit-2026-07-23.md`](reports/claude-fable5-architecture-audit-2026-07-23.md) — independent adversarial architecture audit
- [`reports/claude-opus-audit-2026-07-23.md`](reports/claude-opus-audit-2026-07-23.md) — earlier implementation and readiness audit
