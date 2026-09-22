# V3 event + market-context alpha — research contract (2026-09-22)

Status: **intake-only prototype, no trained V3 model, no trades, no scheduled collector.** V1 and ETF V0 remain rejected controls. This is a new information mechanism, not another filter over their losing proposal labels.

## Hypothesis and fixed first cohort

Earnings/guidance filings from liquid US common stocks may provide decision-time information that improves *after-cost executable* expected utility when combined with market/sector, liquidity, and post-publication price response. Limit first research cohort to official issuer/SEC 8-K Item 2.02 and exhibit releases; this does **not** imply the SEC filing was the first public release. If the market already reacted to an earlier wire, measure only the remaining opportunity. Do not infer this cohort from today's winning stocks. Record the universe and candidate rule before outcome inspection.

Primary comparison: same chronologically trained logistic/ranker **with vs without** text features on identical candidates, fills, and costs. Also compare no-trade, always-admit, and a fixed earnings-only rule. Admit a single nonlinear ranker only after simple baselines and data are valid. Multiple experimental variants count toward the same experiment ledger; do not optimize on the final holdout.

## Intake and availability

`scripts/import_catalyst_events.py` accepts JSONL fields `provider,url,symbol,kind,published_at,text` with `kind=earnings|guidance`. It assigns the actual local `first_seen_at` and `available_at` at import, canonical UTC, never accepting a caller-provided earlier observation. SHA-256 binds text and source-key identity; duplicate imports skip, changed content for the same identity fails, tampering fails on read. The input `text` may be an excerpt; the `provider` must state that honestly. The ignored ledger is `data/events/catalysts-v1.jsonl`. An imported historical release is **not** historical backtest evidence: earlier quote availability, text-vintage, and source distribution cannot be reconstructed by setting its filing timestamp. The AZO SEC exhibit headline imported as a smoke test has publication time set to the EDGAR *acceptance time*, not an assertion that this was the first public announcement; its actual available_at is the import timestamp.

No collector or source rights beyond public SEC pages have been established. The next acquisition step must verify SEC access terms and an appropriate identifying User-Agent, avoid polling/bulk scraping until configured, dedupe accession revisions, and capture full source plus ingestion failures. SEC timestamps, newswire timestamps, and our observation are distinct. News sentiment and LLM features are forward-only unless the model's training cutoff is provably before each historical decision. Model outputs must quote the source spans used and carry model/version, prompt/schema, input hash, and inference time. Text is untrusted data, never instructions.

## Model/compute decision

Hermes VM: event ledger, future feature/label pipeline, calibrated logistic and expected-net-return baseline, evaluation; later one CPU CatBoost challenger **if** independent samples justify it. FinBERT is a CPU-class sentiment control after license verification. `big-ai` GPT-OSS-120B stays parked and demand-only for bounded structured extraction and offline review, not real-time pre-trade authority or LoRA training. R16 and ai-box keep their current workloads. No additional GPU purchase or recurring inference deployment is authorized by this research contract. Time-series models and direct LLM trade actions are out of the first cohort.

## Evidence gate before learner/forward loop

Require point-in-time event identity, release/first-seen/decision cutoffs, matched completed market/sector/stock bars and conservative spreads, fixed entry window after actual observation, no-fill/gap/fees/slippage outcome engine, and all eligible candidates *including abstentions*. If required fields or event-time price cannot be obtained, fail closed rather than impute hindsight. Use session-grouped chronological train/calibration/development folds with purge based on outcome horizon and an untouched final holdout; never feed present-day LLM historical output into an apparent pre-2026 decision. Evaluation is net utility, exposure, turnover, drawdown, calibration and independent event/session counts, including adverse regimes. Positive development result alone does not authorize broker-paper or live trading. Explicit Neal approval remains required for execution and capital changes.

Family finances are not the test bankroll. There is no evidence yet that this V3 idea earns money.
