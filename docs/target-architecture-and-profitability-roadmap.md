# Agentic Trading Lab Target Architecture and Profitability Roadmap

**Date:** 2026-07-23  
**Baseline commit audited:** `1bba66a9a44307da38669b0d0934e3920382db02`  
**Independent audit:** `reports/claude-fable5-architecture-audit-2026-07-23.md`

## Decision

The project should continue as a local, data-trained trading system supervised by Codex and Claude, but not by fine-tuning an LLM on winning proposal prose. The local trading model should first be a calibrated tabular model that ranks deterministic candidates by expected net value using decision-time market features. LLMs belong in research, review, diagnostics, and engineering supervision until they prove incremental predictive value out of sample.

Profitability is a hypothesis to test, not an architecture property. The system remains paper-only until its edge survives realistic costs, walk-forward evaluation, regime slices, shadow deployment, and broker-paper reconciliation.

## Target architecture

```text
historical/live market data
        |
        v
point-in-time universe + feature pipeline
        |
        v
deterministic strategy generators
        |
        +--> candidate ledger (every candidate, no censorship)
                  |
                  +--> deterministic policy/risk validation
                  +--> local model shadow score
                  +--> local LLM shadow review
                  +--> portfolio-admission decision
                  |
                  v
        counterfactual outcome resolver
        realistic entry/exit/slippage/fees/ambiguity
                  |
                  v
        versioned feature/outcome dataset
                  |
          purged walk-forward splits
                  |
                  v
 logistic baseline -> gradient-boosted trainee -> calibrated probabilities
                  |
                  v
 expected-net-R ranking + deterministic sizing/risk/execution gates
                  |
          shadow -> broker paper -> tiny live

Codex: implementation and tests
Claude: independent commit-pinned audit
Jarvis: orchestration, verification, synthesis
Neal: sole promotion authority
```

## Model contract

The first production-shaped trainee predicts values such as:

- `P(target_before_stop | decision-time features)`;
- expected net R after slippage and fees;
- probability of no fill;
- optional adverse/favorable excursion estimates.

It does not generate orders, alter stops, size positions, or bypass policy. Deterministic code retains those powers.

Start with logistic regression as the sanity baseline, then compare LightGBM/XGBoost-style gradient boosting. Neural sequence models and LLM fine-tuning are later experiments only if simpler models plateau and the dataset justifies their complexity.

## Non-negotiable evidence rules

1. Store every generated candidate, including rejected, duplicate, slot-blocked, and model-rejected candidates.
2. Resolve candidates counterfactually from subsequent bars so reviewer skill and skip decisions are measurable.
3. Persist only features available at the decision timestamp.
4. Model realistic fills, gaps, slippage, fees, and same-bar ambiguity.
5. Split by session in time order; purge overlapping labels and embargo fold boundaries.
6. Keep final evaluation windows frozen. Never tune on them.
7. Report strategy, symbol, volatility, regime, and time-of-day slices—not only aggregate P&L.
8. Compare against deterministic always-admit and rule-only baselines.
9. Keep live trading disabled until explicit promotion gates are computed artifacts rather than prose.

## Phase 0 — Freeze the wrong learning loop

### Build

- Mark `training/proposal_outcomes.jsonl` as research provenance, not an SFT-ready decision corpus.
- Move the local LLM review from blocking approval to shadow annotation.
- Preserve deterministic policy rejection separately from model opinion.
- Amend documentation so `usable_for_sft` cannot be mistaken for predictive fitness.

### Exit criteria

- Model outages cannot suppress candidate capture or outcome resolution.
- Every rule-valid candidate receives a stable ID and later outcome.
- No model output can place an order or decide whether evidence is recorded.

## Phase 1 — Counterfactual labeling and realistic simulation

### Build

- Create an immutable candidate-event schema containing strategy/version, signal timestamp, symbol, direction, decision-time features, deterministic-gate result, local-model score, local-LLM verdict, and lane disposition.
- Resolve all rule-valid candidates through one shared fill engine used by historical replay and live paper simulation.
- Add conservative gap-through handling, configurable slippage, fees, no-fill outcomes, and explicit same-bar ambiguity policy.
- Record MFE, MAE, time-to-entry, time-to-stop/target, realized net R, and outcome quality flags.
- Persist regime, scanner score, relative volume, spread/liquidity proxy, volatility, distance from VWAP, market context, and time-of-day.
- Reconcile strategy YAML specifications with executable rules and version both together.

### Exit criteria

- Given identical bars and configuration, replay and paper simulation produce identical decisions and outcomes.
- Tests cover gap-through entries/exits, no fills, missing bars, half-days, same-bar stop/target, and fee/slippage math.
- Candidate capture completeness is 100% for rule-valid candidates.
- Outcome rows are reproducible from source bars and version metadata.

## Phase 2 — Historical replay data engine

### Build

- Acquire and validate at least 12–24 months of minute bars for the initial liquid universe.
- Use a point-in-time universe or begin with stable liquid ETFs/mega-caps to minimize survivorship distortion.
- Replay scanner and strategy code session by session; never use the current watchlist to select historical winners.
- Generate the same candidate/outcome schema as the live loop.
- Add dataset manifests with source hashes, date ranges, symbol coverage, code commit, strategy versions, and feature schema.
- Add data-quality gates for missing sessions, duplicated bars, split adjustments, timestamp ordering, and implausible prices/volume.

### Exit criteria

- At least 10,000 resolved candidate rows across multiple regimes, subject to strategy opportunity rate.
- No train/evaluation overlap by session or label horizon.
- Dataset reproduction from a manifest is deterministic.
- Coverage and missingness reports pass defined thresholds.

## Phase 3 — Baselines, walk-forward evaluation, and calibration

### Build

- Implement deterministic baselines: admit all rule-valid candidates, existing portfolio rules, and simple threshold filters.
- Train logistic regression first; then a gradient-boosted model using the same folds and features.
- Use nested, purged walk-forward evaluation with embargo between folds.
- Calibrate probabilities using training/validation data only.
- Evaluate AUC/PR-AUC and Brier/calibration, but promote on trading utility: net expectancy, drawdown, profit factor, turnover, exposure, and stability after costs.
- Bootstrap confidence intervals by trading session—not by individual correlated trade.
- Correct for repeated strategy/model trials; preserve a final untouched holdout.

### Exit criteria

- The trainee beats rule-only and always-admit baselines on multiple untouched walk-forward folds after costs.
- Positive net expectancy has a predeclared confidence threshold and is not dependent on one symbol, month, or regime.
- Calibration is acceptable enough for thresholding and sizing research.
- A machine-generated `readiness.json` records fold metrics, sample counts, cost assumptions, failure slices, and blockers.

## Phase 4 — Shadow deployment and drift monitoring

### Build

- Score every live candidate without changing admission.
- Compare prediction distributions and realized outcomes with the training population.
- Track calibration drift, feature drift, regime drift, latency, missing features, and model availability.
- Version model, feature schema, thresholds, and code commit in every decision record.
- Establish automatic rollback to the deterministic baseline.

### Exit criteria

- At least 60 trading sessions of shadow evidence.
- Shadow performance remains above the deterministic baseline after realistic costs.
- No unexplained train/live feature skew.
- Drift and data-quality failures fail closed to the baseline.

## Phase 5 — Broker paper execution

### Build

- Implement idempotent order submission, duplicate locks, order/fill reconciliation, partial fills, stale-order cancellation, and restart recovery.
- Add aggregate notional and correlated-exposure caps, heartbeat, kill switch, exchange calendar, half-day handling, and end-of-day flatten verification.
- Compare modeled fills with actual broker-paper fills and recalibrate cost assumptions.

### Exit criteria

- At least 60 additional sessions without reconciliation errors or unintended overnight exposure.
- Modeled versus broker-paper slippage is measured and reflected in evaluation.
- Every failure path is tested and produces an actionable alert.
- `readiness.json` reports all execution gates green.

## Phase 6 — Tiny live experiment

Live use is optional and requires Neal's explicit promotion. Begin only with capital whose complete loss is acceptable, one strategy/model version, and fixed limits that cannot be altered by a model.

### Initial constraints

- One liquid instrument family or a very small liquid universe.
- Fixed fractional risk below the paper-research level.
- Hard daily, weekly, aggregate-notional, turnover, and consecutive-loss limits.
- Automatic fallback/disable on drift, reconciliation failure, stale data, or model mismatch.
- No online self-training and no model-driven code/config changes.

### Exit criteria for scaling

Scale only after enough independent live sessions to validate implementation and cost assumptions. Increase one dimension at a time; never increase model complexity, universe, leverage, and capital simultaneously.

## Codex and Claude supervision protocol

### Codex — builder

- Works from bite-sized TDD plans.
- Implements data, evaluation, execution, and observability changes.
- Cannot approve its own promotion gate.
- Produces tests, reproducible commands, and commit-linked artifacts.

### Claude — independent auditor

- Receives sanitized git-tracked code, manifests, and machine-readable metrics—not credentials or private trade/account details.
- Audits a named commit and writes a separate immutable report.
- Challenges leakage, selection bias, cost assumptions, statistical claims, and implementation drift.
- Does not modify the evidence it audits.

### Jarvis — orchestrator and verifier

- Defines tasks, runs Codex, requests Claude review, verifies tests and artifacts, and reconciles disagreements.
- Keeps the local model and LLM opinions out of deterministic safety paths.
- Reports blockers instead of converting confidence into evidence.

### Neal — sole promoter

Only Neal can promote a strategy, model, execution lane, or capital allocation. Required inputs are the current `readiness.json`, model card, Codex verification record, Claude audit, and explicit risk limits.

## Promotion scorecard

A model stays in shadow unless all applicable gates pass:

- data completeness and point-in-time integrity;
- reproducible dataset and model artifacts;
- purged walk-forward superiority over baselines;
- positive expectancy after realistic costs;
- acceptable drawdown and concentration;
- stable regime/symbol/time slices;
- calibrated probabilities;
- shadow and broker-paper agreement;
- no unresolved critical audit findings;
- explicit human approval.

## Immediate implementation order

1. Shadow-only local reviewer and complete candidate ledger.
2. Shared realistic counterfactual outcome engine.
3. Decision-time feature schema and strategy-version parity.
4. Historical point-in-time replay and dataset manifests.
5. Logistic baseline, gradient boosting, purged walk-forward harness, and `readiness.json`.
6. Shadow deployment and drift telemetry.
7. Broker-paper execution hardening.
8. Tiny-live consideration only after every prior gate passes.

The first four items create valid evidence. Everything after them depends on that evidence. Building a larger model before them would merely give the goblin a better vocabulary.
