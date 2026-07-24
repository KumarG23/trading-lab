# Evidence verification and recovery report — 2026-07-24

Generated at `2026-07-24T09:30:51-04:00` from clean implementation HEAD `54965ef52c479846171ba17c7a1e659f5a26bcbc`.

## Safety disposition

- Promotion ready: **no**
- Runtime mode: `paper_proposal_only_no_orders`
- Broker orders enabled: `false`
- Live trading enabled: `false`
- No broker-order endpoint was added or exercised.

## Hermetic verification

- Bounded unit suite: `python3 -m pytest tests -q --durations=10`
- Result: **135 passed in 4.45s**
- Slowest test: 0.41s
- Production artifact snapshot before/after: **unchanged** (`342` files under `data/raw` and `data/evidence` both before and after)
- Static checks: `ruff check trading_lab scripts tests --ignore F401` passed; `python3 -m pip check` reported no broken requirements; `python3 -m compileall -q trading_lab scripts tests` passed.
- Python line coverage was not measured because the environment does not have the `coverage` module installed. This report does not invent a percentage.

## Licensed Alpaca raw cache

The raw manifest identifies `alpaca-iex`, `1Min`, requested `[2024-07-24, 2026-07-24)`, ten symbols. Independent verification decompressed every manifest chunk, checked each SHA-256, row count, symbol, start/end, and aggregate coverage.

- Manifest chunks: **250**, all nonempty and verified
- Raw files under `data/raw`: **251** including the unrelated legacy SQLite file
- Bars: **1,912,323**
- Exact raw timestamp coverage: `2024-07-24T12:13:00Z` through `2026-07-23T20:52:00Z`
- Symbols: `AAPL, AMD, AMZN, GOOGL, META, MSFT, NVDA, QQQ, SPY, TSLA`
- Provider errors: none recorded
- Raw-cache checksum/coverage verification: **passed**

## Counterfactual evidence v4

Independent verification checked all partition hashes and decompressed row counts.

- Partitions: **25** monthly gzip files (`2024-07` through `2026-07`)
- Candidates: **11,680** across **500** sessions
- Dispositions: **7,491** policy-approved; **4,189** policy-rejected
- Fill outcomes: **11,466** filled; **214** no-fill
- Strategies: momentum pullback **4,035**; ORB **3,821**; VWAP reclaim **2,931**; VWAP trend/imbalance **893**
- Partition SHA-256 and row-count verification: **passed**
- Outcome quality flags: `entry_bar_path_unknown` **11,466**; `same_bar_stop_target` **159**

The stored v4 manifest is not promotable provenance:

1. Its code identity is `a92b4137d3514b73c1879c307dd714db15053fc8-dirty`, not a clean reproducible commit.
2. Its legacy dataset digest is `39a429d56c8f3aba8f2d96f2472e8f317c33e3a3657c59ea92c1576a8dac625`; the new host-path-independent digest over the same verified artifacts is `bd0dd1da2c33988bdc386e11890a5964176a3299051325f3e9d90ab8098faa8f`.
3. All filled outcomes carry OHLC entry-path uncertainty, so readiness correctly treats them as quality-flagged rather than promotion-grade evidence.

The v4 files were preserved and not rewritten. A future full integration replay must write a new immutable evidence version from a clean commit rather than laundering the old manifest.

## Leakage-safe model evaluation

A fresh offline evaluation was run against the verified v4 rows using five ordered purged walk-forward folds, a one-session embargo, fold-local training/calibration, and an explicit decision-time feature allowlist. This is research evidence only because the underlying v4 provenance/quality gates above fail.

- Usable filled outcomes: **11,466**
- Sessions: **500**
- Out-of-sample test observations: **5,717**
- Aggregate Brier score: **0.233359**
- Aggregate log loss: **0.659513**
- Always-admit expectancy: **-$0.533545 / -1.624789R per candidate**
- Model-selected candidates: **0**
- Model-selected expectancy: **$0.000000 / 0.000000R**
- Promotion gates failed: `selected_candidates`, `positive_model_expectancy`, `positive_every_fold`

Fold ROC AUC values were `0.519841`, `0.486913`, `0.493717`, `0.509990`, and `0.490663`. That is noise wearing a lab coat, not edge.

## Readiness blockers

Fresh fail-closed readiness output:

- `dataset_code_sha_not_clean:a92b4137d3514b73c1879c307dd714db15053fc8-dirty`
- `model_evaluation_gates_failed`
- `candidate_outcome_quality_flags:11466`
- `human_promotion_not_granted`

Promotion remains false by construction.

## Database and dashboard safety

- Pre-migration backup: `journal/backups/trading-lab-before-candidate-outcomes-20260724-080539.db`
- Main DB `PRAGMA integrity_check`: `ok`
- Foreign-key check: no violations
- Candidate event/outcome counts in the live journal at verification: `0 / 0`
- Existing proposals / paper positions / paper trades: `187 / 184 / 70`
- Dashboard service: active
- `/health`: `{"ok": true}`
- `/api/snapshot`: `paper_proposal_only_no_orders`, live `false`, broker orders `false`
