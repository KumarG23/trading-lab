# Trading Lab Build Notes

## What was harvested from `Claude_Bot`

Useful pattern:

```text
proposal/decision -> paper/live execution -> trade outcome -> review -> strategy refinement
```

The new lab keeps that separation but starts with proposal/paper mode only.

## Current implemented local tooling

```text
trading_lab/
  indicators.py       # EMA, RSI, VWAP, volume profile
  journal_store.py    # SQLite proposal/paper/review/model-usage schema
  metrics.py          # R, expectancy, drawdown, profit factor, adherence
scripts/
  init_lab_db.py      # creates journal/trading-lab.db
analysis/
  journal_metrics.py  # prints metrics JSON from paper trades
```

## Why this direction

The old bot's main failure was using Claude as the recurring inner loop. The new lab makes code do the repetitive work and saves models for event-driven review.

Default flow:

1. scanner/backtest code finds candidates
2. deterministic strategy evaluator creates proposal object
3. proposal is logged locally
4. paper outcome is logged
5. metrics script judges evidence
6. local Qwen/Qwen3.6 reviews compact summaries
7. Jarvis promotes/revises/kills strategies

## Implemented since prior-art inspection

- Proposal validator / risk gate: `trading_lab/policy_gate.py`
- Autonomous proposal runner: `trading_lab/autonomous_runner.py`
- Local OpenAI-compatible Qwen worker: `trading_lab/local_worker.py`
- Sanitized prior-art exporter: `trading_lab/training_data.py`
- Training-memory retrieval: `trading_lab/training_memory.py`
- Runtime config: `trading_lab/config.py`
- CLI smoke loop: `scripts/autonomous_paper_loop.py`
- Sanitized examples exported from old `Claude_Bot`: `training/claude_bot_sanitized_examples.jsonl` (ignored by git)

## Next implementation targets

1. Opening range breakout backtest/proposal harness using local OHLCV CSV input.
2. Strategy evaluator modules generated from `strategies/*.yaml`.
3. Alpaca paper market-data adapter once paper credentials are present.
4. EOD local-Qwen review runner that summarizes proposals/trades and appends `reviews` rows.
5. Codex escalation brief for test failures, scanner bugs, or strategy-harness implementation work.
