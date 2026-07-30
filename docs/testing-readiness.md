# Autonomous Testing Readiness

Updated: 2026-07-30

## Current verdict

Ready for deterministic local proposal capture, counterfactual paper simulation, historical evidence generation, and offline model evaluation.

Not ready for broker-submitted paper orders or live capital. Broker order placement remains outside the weekly review and model-training paths.

## Safety topology

- The active minute loop uses `--no-local-ai`; candidate generation, policy checks, and outcome simulation are deterministic.
- Every qualified nonduplicate signal enters the research lane. Portfolio-admitted proposals remain a separately constrained subset.
- Research and portfolio metrics are reported separately.
- Research runaway cap: 50 proposals per day.
- Duplicate suppression: 30 minutes.
- New entries stop at 14:30 ET; simulated positions flatten at 15:45 ET.
- Historical replay and weekly evidence review refuse live-enabled configuration and place zero broker orders.
- Strategy or model promotion always retains a human-approval blocker.

## Evidence and evaluation

The v5 contract uses normalized decision-time features shared by live capture and historical replay. Post-entry outcome fields are labels or diagnostics, never model features.

Offline evaluation includes:

- Per-strategy logistic baselines.
- Combined logistic baseline.
- Gradient-boosted classifier.
- Direct expected-net-R regressor.
- Separate class-weighted no-fill-risk model.
- Cost-adjusted calibration thresholds chosen from calibration sessions only.
- Session-ordered purged walk-forward folds.
- A separately embargoed final holdout.
- Candidate and independent-session sample gates.
- Profit-factor, expectancy, drawdown, strategy/regime/time-bucket, feature-coverage, and data-quality diagnostics.
- Warning, exclusion, and fatal quality severities. Ambiguous/fatal rows cannot enter model fitting.
- Cryptographic verification of immutable compressed evidence artifacts and exact feature/schema manifests.

Live `training/proposal_outcomes.jsonl` remains provenance/audit material. Historical `data/evidence/candidate-outcomes-v5/` is the predictive evaluation corpus. Old Claude_Bot examples remain sanitized prior art for optional offline language-model analysis; they are not predictive labels and are not used in the hot path.

## Verification commands

```bash
.venv/bin/python -m pytest tests -q
.venv/bin/python -m compileall -q trading_lab scripts tests
git diff --check
.venv/bin/python scripts/replay_evidence_dataset.py
.venv/bin/python scripts/weekly_evidence_review.py
```

Latest code-suite verification before v5 regeneration:

```text
148 passed
compileall passed
git diff --check passed
```

## Remaining promotion blockers

- Regenerate immutable v5 evidence from the clean committed feature/evaluation code.
- Verify the v5 manifest and artifact hashes.
- Run the full weekly evaluator and inspect the untouched holdout.
- Require positive cost-adjusted expectancy and profit factor above 1.2 in both walk-forward and final holdout evidence.
- Require enough independently selected sessions, not merely correlated proposal rows.
- Require the no-fill model to outperform a base-rate predictor out of sample.
- Verify broker order lifecycle, reconciliation, duplicate-order locks, recovery, and kill switches before broker paper execution.
- Require explicit human approval before any promotion.

The default interpretation of a failed gate is “the strategy/model is not ready,” not “loosen the gate until the chart turns green.”
