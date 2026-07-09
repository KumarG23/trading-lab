# Local Model / Codex Workflow

## Roles

Jarvis:

- Owns orchestration and risk policy.
- Converts Neal's goals into tasks.
- Reviews outputs from Codex/local models before presenting decisions.
- Refuses strategy promotion when metrics are weak or logs are incomplete.

Codex:

- Builds scripts, scanners, backtests, validators, and reports.
- Turns strategy YAMLs into executable rules.
- Adds tests around financial calculations.
- Uses cheap/local paths first and avoids unnecessary paid API burn.

Local Qwen/Qwen3.6:

- Reviews private journal/account-aware context.
- Finds behavioral patterns and setup clusters.
- Produces daily/weekly postmortem drafts.
- Suggests rule refinements for Jarvis review.

## Daily paper/proposal loop

1. Pre-market / open:
   - run scanners when available
   - identify candidates matching strategy YAML rules
   - produce paper/proposal entries only

2. During session:
   - log proposed setups
   - mark skipped/invalidated/entered/exited paper trades
   - preserve reason-to-skip and rule checklist

3. After session:
   - run journal metrics
   - local model reviews mistakes and patterns
   - Jarvis writes concise daily review

4. Weekly:
   - aggregate metrics by strategy
   - inspect drawdown and adherence
   - decide: keep testing, revise rules, or kill strategy

## Promotion workflow

A strategy can move through:

```text
idea -> paper_only -> tiny_live_candidate -> human_approved_live -> scoped_autonomous_micro
```

Current state for all strategies: `paper_only`.

Promotion requires logged evidence and Neal's explicit approval. Prompt confidence does not count. The market does not care that the language model used bullet points.

## Data handling

- Private trade/account logs should stay local where possible.
- Use local Qwen/Qwen3.6 or the current local reviewer for private reviews.
- Use Codex for code and deterministic calculations.
- Avoid uploading raw private logs to paid/cloud models unless explicitly approved.
- The SQLite journal is canonical. `training/proposal_outcomes.jsonl` is a regenerated derived dataset for future evals/tuning.
- Capture compact proposal/outcome examples, not giant prompt transcripts: strategy, structured proposal, rule checklist, model thesis/objection, lifecycle outcome, R/PnL, adherence, and mistake category.
- Fine-tuning comes after enough clean labeled outcomes plus held-out evals. Thousands of trades can support LoRA/SFT, but only if labels are high-quality and representative; raw volume of mediocre setups is just overfit goblin feed.

## Future Robinhood MCP phase

Not active yet.

Before connecting:

1. Use isolated trading profile/context.
2. Inspect MCP tool schema and permissions.
3. Confirm read-only usage if available.
4. Build deterministic trade approval guardrails.
5. Require Neal approval for any move beyond read-only.
