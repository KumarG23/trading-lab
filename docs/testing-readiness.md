# Autonomous Testing Readiness

Date: 2026-06-29

## Current readiness verdict

Ready for **local autonomous paper/proposal-loop smoke testing**.

Not ready for broker-connected paper trading until Neal provides or confirms broker paper credentials and chooses Alpaca vs Robinhood.

## What is ready

- Deterministic risk/policy gate rejects banned assets, missing stops, bad reward:risk, excess risk, and daily trade-limit violations.
- Local Qwen worker is wired as the default proposal reviewer.
- Old `Claude_Bot` data has been sanitized into compact JSONL examples and is injected into local model review prompts as relevant training memory.
- Codex escalation path is documented as the engineering fallback, not part of the tick loop.
- SQLite journal is initialized and stores proposals/paper trades/reviews/model usage.
- Metrics tooling reports R expectancy, profit factor, drawdown, and rule adherence.
- Tests are green.

## Smoke-tested commands

```bash
python3 scripts/init_lab_db.py
python3 scripts/export_claude_bot_training.py data/raw/claude_bot_trades.db training/claude_bot_sanitized_examples.jsonl --limit 5000
python3 scripts/autonomous_paper_loop.py data/sample_candidates.json --no-local-ai
python3 scripts/autonomous_paper_loop.py data/sample_candidates.json --db journal/local-ai-smoke.db
python3 analysis/journal_metrics.py
python3 -m pytest tests -q
```

Latest verification:

```text
51 passed
local model endpoint: http://100.117.167.61:8098/v1 reachable
legacy sanitized training examples exported: 3670
legacy training labels: hold_filter=3604, candidate_setup=61, avoid_or_repair=5
proposal/outcome training dataset: training/proposal_outcomes.jsonl regenerated from journal/trading-lab.db
current proposal/outcome examples: 33
```

## What the local model did in smoke testing

The local Qwen worker reviewed the sample AAPL ORB candidate and rejected it because the setup was under-specified / not strongly confirmed. That is acceptable behavior. Better a suspicious goblin than an eager one.

## What is blocked

Nothing is blocking local autonomous proposal testing.

Broker-connected paper trading is now confirmed for Alpaca **read-only account access** using `/home/neal/trading-lab/.env`, copied from the old R16 `C:\code\Claude_Bot\.env` after Neal confirmed it contains the credentials.

Verified safe Alpaca paper account check:

```text
status=ACTIVE
alpaca_paper=True
trading_blocked=False
account_blocked=False
trade_suspended_by_user=False
```

Still do **not** connect Robinhood live MCP yet.

## Next build step

Build the first real autonomous candidate generator:

```text
OHLCV source -> opening range breakout scanner -> policy gate -> local Qwen review -> proposal journal
```

Start with CSV/local historical bars so we can test without broker credentials. Then swap the data source to Alpaca paper market data once credentials exist.
