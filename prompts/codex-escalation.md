# Codex Escalation Brief

Use Codex when the local worker or deterministic code path hits implementation complexity, failing tests, or data-source weirdness.

## Rules

- Codex is an escalation lane, not the recurring trading brain.
- Do not connect broker live trading.
- Keep work under `~/trading-lab`.
- Preserve policy: proposal/paper mode only.
- Use TDD for deterministic modules.
- Run `python3 -m pytest tests -q` before returning.

## Current architecture

```text
scanner/backtest -> strategy evaluator -> PolicyGate -> LocalAIWorker + TrainingMemory -> JournalStore -> metrics/review
```

## Preferred task shape

```text
Implement [specific module] in /home/neal/trading-lab using TDD.
Write failing pytest(s) first, verify RED, implement minimal GREEN, run full tests.
Do not add broker execution. Do not read .env or secrets.
```

## Escalate for

- Scanner/backtest math ambiguity
- Alpaca paper adapter implementation
- Complex parser/data-cleaning issues
- Test failures local Qwen cannot repair cleanly
- Refactors touching multiple modules

## Do not escalate for

- Routine journal review
- Daily metrics summaries
- Private account-aware trade log analysis
- Repetitive proposal filtering
