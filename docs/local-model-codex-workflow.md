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

Local GPT-OSS/Qwen-style reviewer:

- Is offline/shadow analysis only in the active proposal path.
- Reviews private journal/account-aware context when explicitly enabled.
- Produces daily/weekly postmortem drafts and rule-refinement suggestions for Jarvis review.
- Does not place orders, size trades, alter stops, or authorize promotion.

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
   - run the offline historical evidence evaluation and model card
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
- The SQLite journal is canonical. `training/proposal_outcomes.jsonl` is regenerated research provenance, not predictive-training evidence or an SFT-ready corpus.
- Live journal exports are provenance and audit material. They are not suitable for supervised fine-tuning or predictive admission training because they are sparse, policy-censored, and labeled by single realized outcomes.
- Historical counterfactual evidence under `data/evidence/candidate-outcomes-v5/` is the predictive training/evaluation source. It uses the shared `candidate-decision-features-v5` contract and session-ordered purged walk-forward evaluation with a final untouched holdout.
- Old Claude example exports are inactive in the default hot path. The active wrapper uses `--no-local-ai` for deterministic proposal capture unless explicitly run otherwise.
- GPT-OSS/local reviewers remain offline/shadow analysis tools. Their text is not a decision feature and must not become an order path.
- Capture compact proposal/outcome examples, not giant prompt transcripts: strategy, structured proposal, rule checklist, model thesis/objection, lifecycle outcome, R/PnL, adherence, and mistake category.
- Single-trade win/loss labels must never authorize predictive SFT. Trading models require counterfactually resolved candidates, realistic costs, point-in-time features, and held-out walk-forward evaluation; LLM tuning remains limited to formatting/postmortem tasks with separate evals.

## Future Robinhood MCP phase

Not active yet.

Before connecting:

1. Use isolated trading profile/context.
2. Inspect MCP tool schema and permissions.
3. Confirm read-only usage if available.
4. Build deterministic trade approval guardrails.
5. Require Neal approval for any move beyond read-only.
