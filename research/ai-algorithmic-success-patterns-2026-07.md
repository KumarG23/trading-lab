# AI and Algorithmic Trading Success Patterns — 2026-08-15

Purpose: extract reproducible engineering and research patterns from credible algorithmic/ML trading work, then turn them into falsifiable Trading Lab experiments. This is not a scrapbook of return claims.

## Evidence ladder

Rank every external claim before using it:

1. **Live, net-of-cost, independently audited or institutionally diligenced evidence**
2. **Live manager-reported results with meaningful external capital/adoption**
3. **Peer-reviewed out-of-sample research with realistic costs and execution**
4. **Peer-reviewed prediction/backtest research with incomplete execution assumptions**
5. **Vendor/manager marketing, unpublished backtests, social posts, and anecdotes**

A lower-tier claim may generate a hypothesis. It cannot justify promotion, capital, or weakened gates.

## Credible cases and transferable patterns

### Numerai: many diverse models combined into a market-neutral ensemble

Sources:

- Numerai/JPMorgan capacity announcement: https://blog.numer.ai/jpmorgan-secures-500m-capacity/
- Independent industry coverage noting both the strong 2024 and a 2023 loss: https://www.hedgeweek.com/quant-hedge-fund-numerai-secures-500m-jpmorgan-allocation/

Reported evidence: Numerai says its fund returned 25.45% net in 2024 with a 2.75 Sharpe, after losing roughly 17% in 2023 according to industry coverage; JPMorgan committed substantial capacity. These figures are useful but remain manager/industry reports rather than our independently audited data.

Transferable pattern:

- Aggregate many weak, diverse signals instead of betting on one heroic model.
- Reward out-of-sample contribution and low correlation to the ensemble, not standalone leaderboard accuracy.
- Neutralize unwanted exposures and separate prediction from portfolio construction.

Trading Lab implication:

- Track incremental utility and prediction correlation for every strategy/model.
- Test strategy/model ensembles only after each component has chronological out-of-sample predictions.
- Prefer a diversified top-ranked candidate set over duplicated ORB candidates sharing one market move.

### Man AHL: ML is one component of a mature systematic stack

Sources:

- https://www.man.com/insights/the-rise-of-machine-learning
- https://www.man.com/insights/intro-machine-learning

Man AHL reports using ML-based systems in client portfolios since 2014. Its public material emphasizes alternative/real-time data, NLP, execution, smart order routing, and transaction-cost control—not an LLM making unconstrained trade decisions.

Transferable pattern:

- ML augments structured signals, execution, and research; it does not replace deterministic controls.
- Data and execution quality can matter more than model novelty.
- Multiple strategies and horizons reduce dependence on one fragile edge.

Trading Lab implication:

- Keep the local LLM in analysis/postmortem work.
- Invest first in catalyst/liquidity data, fill realism, drift detection, and strategy diversity.
- Treat execution/no-fill prediction as part of economics, not plumbing after the fact.

### Gu, Kelly, and Xiu: nonlinear structured models can add out-of-sample value

Sources:

- NBER working paper: https://www.nber.org/papers/w25398
- Review of Financial Studies article: https://academic.oup.com/rfs/article/33/5/2223/5758276

The research compares linear models, trees, neural networks, and other ML methods for cross-sectional expected-return prediction. Tree and neural methods captured nonlinear interactions and improved out-of-sample economic results in the studied setting.

Transferable pattern:

- Structured tabular predictors are the correct first modeling target.
- Nonlinear models earn adoption only by beating linear baselines out of sample.
- Feature interactions matter, but complexity without independent evidence is overfit cosplay.

Trading Lab implication:

- Continue comparing per-strategy logistic, combined logistic, gradient boosting, and expected-net-R regression.
- Add complexity only after stable chronological improvement over simple baselines.
- Evaluate economic utility after costs, not classification accuracy alone.

### Li–Rossi–Yan–Zheng: real-time feature construction matters more than model novelty

Sources:

- Journal of Financial Economics article: https://www.sciencedirect.com/science/article/abs/pii/S0304405X25001461
- Author PDF: https://www.lehigh.edu/~xuy219/research/JFE_2025.pdf
- Official replication package: https://data.mendeley.com/datasets/vsww29gb36/2
- Independent replication preprint: https://osf.io/preprints/socarxiv/3fh8x_v2

Evidence tier: tier 3—peer-reviewed out-of-sample research with an official replication package. A 2026 independent preprint replication supports the broad feature-engineering result, but this is cross-sectional fundamental-signal research rather than audited live intraday evidence.

The paper constructs real-time strategies from more than 18,000 signals available to investors. Out-of-sample results were economically meaningful but weaker than results based on ex-post curated signal sets; simple recursive ranking of signals by past performance outperformed standard ML approaches. The result is a warning against feeding a large raw feature pile to a clever model and assuming complexity will discover stable structure.

Transferable pattern:

- Prefer point-in-time, economically motivated transformations and relative/ranked features over unstable raw levels.
- Compare every complex learner with transparent recursive-rank and linear baselines.
- Treat feature-set curation as a registered hypothesis family so selection does not disappear into preprocessing.

Trading Lab implication:

- The current `dollar_volume_log` PSI of 0.795 is an investigation lead for a decision-time liquidity-relative feature, not permission to retrain or tune a gate.
- Any liquidity normalization requires a new versioned corpus because v5 is immutable; the raw feature and unchanged v5 baselines must remain available.
- Do not implement the feature until its point-in-time reference set and same-timestamp availability can be reproduced without cross-sectional hindsight.

### AQR/Jensen–Kelly–Malamud–Pedersen: optimize what can actually be implemented

Sources:

- Review of Financial Studies article (2026): https://academic.oup.com/rfs/advance-article/doi/10.1093/rfs/hhag022/8524346
- Harvard Dataverse replication package: https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/GKLU6G
- Public replication code: https://github.com/theisij/ml-and-the-implementable-efficient-frontier

Evidence tier: tier 3—peer-reviewed out-of-sample research with an official replication package. It is evidence for cost-aware portfolio design, not audited live intraday profitability.

Core finding: cost-agnostic ML tends to chase fleeting signals and excessive turnover. Their framework optimizes portfolio decisions around net returns after transaction costs. The 2026 Review of Financial Studies publication and linked replication materials strengthen the methodological evidence, but do not make its asset-pricing setting automatically transferable to this small-account intraday lab.

Transferable pattern:

- The objective must include fees, slippage, fill probability, turnover, and capacity.
- Prediction quality and trading quality are different things.
- Optimize portfolio/ranking decisions, not isolated row accuracy.

Trading Lab implication:

- Keep expected net R after modeled costs as the selection objective.
- Add a research-only cross-sectional ranking experiment: rank contemporaneous eligible candidates by predicted net utility, apply a fixed top-k/capacity rule, and compare with absolute-threshold selection using untouched chronological tests.
- Reject improvements that disappear under worse-but-plausible cost scenarios.
- Do not add another allocator now: the lab's 13 registered development variants are all negative after baseline costs, so the published mechanism supports the existing falsifiable ranking hypothesis but does not justify new implementation or a holdout peek.

### Wang–Gao–Harvey–Liu–Tao: train against the implementable portfolio objective

Sources:

- NBER Working Paper 34861 (February 2026): https://www.nber.org/papers/w34861
- Full paper: https://www.nber.org/system/files/working_papers/w34861/w34861.pdf

Evidence tier: provisional tier 4—primary working-paper research with out-of-sample portfolio tests and transaction-cost analysis, but not peer-reviewed or audited live results. The paper studies Chinese A-shares from 2010–2023 and reports that an end-to-end objective joining return prediction to Markowitz portfolio construction is more resilient to costs and constraints than a forecast-then-optimize mean-squared-error pipeline. No public replication repository was found in the 2026-08-01 search, so the claim remains unreplicated here.

Transferable pattern:

- Train and select models against the constrained net portfolio decision they will actually support, not generic prediction loss alone.
- Include transaction costs, risk preference, capacity, and portfolio constraints inside development selection.
- Keep forecast quality diagnostics, but require economic utility under the same execution assumptions used by the portfolio simulator.

Trading Lab implication:

- The nearest safe analogue is a research-only ranking policy trained on expected net R and evaluated through the constrained portfolio ledger.
- Do not add an end-to-end neural allocator while every registered development policy remains negative after costs; model complexity cannot resurrect missing gross edge.
- If revisited, compare it with unchanged always-admit, logistic, expected-net-R regression, and top-k baselines under identical chronology, costs, no-fill treatment, and capacity.

### DeepLOB: deep models can predict order-book movement, but execution assumptions dominate

Sources:

- Original paper: https://arxiv.org/abs/1808.03668
- Later microstructure benchmark/caution: https://arxiv.org/abs/2403.09267

DeepLOB reported improved out-of-sample limit-order-book prediction and positive gross simulations under assumptions including liquid instruments and mid-price execution. Later work emphasizes that standard ML metrics do not necessarily translate into executable trades.

Transferable pattern:

- High-frequency prediction requires full depth/order-book data and a matching execution simulator.
- Mid-price accuracy is not net profitability.

Trading Lab implication:

- Do not imitate DeepLOB with one-minute OHLCV and call it equivalent.
- Defer order-book deep learning until the lab has point-in-time L2 data, queue/fill modeling, latency measurements, and a separate microstructure simulator.

### Bailey et al.: most apparent success can be selection bias

Sources:

- Probability of Backtest Overfitting: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- Deflated Sharpe Ratio: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551

Transferable pattern:

- Trying many variants and reporting the winner silently consumes statistical validity.
- Multiple-testing corrections and untouched data matter more as the hypothesis count grows.

Trading Lab implication:

- Maintain a hypothesis ledger including rejected/failed variants.
- Count model/feature/strategy trials.
- Add deflated-Sharpe/PBO-style diagnostics only when the strategy-trial history is complete enough to make them meaningful.
- Never recycle the final holdout after a disappointing result; create a later forward period.

## Hypothesis registry contract

Every research hypothesis must record:

- Stable ID and date
- Source and evidence tier
- Claimed mechanism
- Why it might transfer to this small-account intraday setting
- Required decision-time data
- Strategy/model version
- Primary metric and cost assumptions
- Chronological train/calibration/test/holdout plan
- Correlation/effective-sample treatment
- Failure criteria
- Result, including negative/no-op outcomes
- Whether it remains research-only, is rejected, or is eligible for forward paper testing

## Initial prioritized experiments

1. **Liquidity-universe drift investigation**
   - Current `dollar_volume_log` PSI is approximately 0.795 between early and recent windows.
   - Determine whether this is universe/scanner drift, market regime, split/price effects, or a real liquidity shift before retraining anything.

2. **Cost-aware contemporaneous ranking**
   - Compare absolute utility thresholds with top-k ranking among candidates observable at the same decision time.
   - Include fill probability, fees, slippage, turnover, duplicate/correlation controls, and portfolio capacity.
   - Keep this research-only and preserve the untouched holdout.

3. **Stocks-in-play/catalyst data**
   - Evaluate whether point-in-time gap, abnormal relative volume, earnings/news timing, and premarket activity improve ORB/momentum performance.
   - No scraped hindsight labels; source timestamps must prove availability before the signal.

4. **Ensemble diversity audit**
   - Measure prediction and outcome correlation among ORB, VWAP trend, VWAP reclaim, and momentum pullback.
   - Test whether any ensemble improves net utility across independent sessions rather than merely multiplying the same market move.

## Hypothesis ledger

### ATL-H-2026-08-01-01 — constrained end-to-end net-utility ranking

- **Source / evidence tier:** Wang, Gao, Harvey, Liu, and Tao, NBER Working Paper 34861; provisional tier 4 primary working-paper evidence with out-of-sample tests and costs, not peer-reviewed or audited live evidence.
- **Mechanism:** jointly select a candidate-ranking function and constrained portfolio action for expected net utility instead of minimizing prediction error and applying portfolio rules afterward.
- **Transfer rationale:** the lab already observes multiple contemporaneous candidates, explicit fill costs, and capacity constraints, so ranking utility is closer to the actual decision than row-level classification accuracy.
- **Required decision-time data:** v5 features and timestamps, calibrated fill probability, contemporaneous candidate groups, portfolio cash/notional/slot state, and immutable realized net R. Point-in-time catalyst/gap features remain unavailable and must not be reconstructed from hindsight.
- **Costs / fills:** preserve the v5 gap-aware path; primary costs remain 5 bps entry, 10 bps exit, and $0.005/share/side, with zero-explicit-fee, recorded-slippage-free diagnostic upper bound, and double-slippage sensitivity. The upper bound is not an execution forecast.
- **Validation:** fit only on purged chronological development folds; calibrate without overlap; compare unchanged baselines under the same top-k/capacity policy; aggregate returns by independent session; register every objective/architecture trial; score the untouched holdout once only if development expectancy is positive and sample/session gates pass.
- **Failure criteria:** reject if development expectancy is non-positive after baseline costs, profit factor is undefined or <=1.2, fewer than 25 selections or 20 independent sessions are produced, any fold is non-positive, gains disappear under plausible costs, or improvement is concentrated in one strategy/symbol/regime.
- **Status / 2026-08-01 result:** hypothesis recorded, implementation deferred. The existing closest proxies are already negative: cost-aware positive-utility ranking is -0.105393R over 7 selections/5 sessions, top-1-per-session is -0.459753R over 195 sessions, and all 13 registered development variants are negative. The untouched holdout remains unqueried for these variants. No additional model is justified until a simpler version demonstrates positive development utility.

### ATL-H-2026-08-08-01 — point-in-time liquidity-relative feature

- **Source / evidence tier:** Li, Rossi, Yan, and Zheng, Journal of Financial Economics 172 (2025), official replication code available; tier 3 peer-reviewed out-of-sample evidence. The setting is cross-sectional fundamental signals, so transfer to one-minute intraday candidates is unproven.
- **Mechanism:** replace reliance on an unstable raw dollar-volume level with a decision-time relative-liquidity transform, such as a within-symbol rolling percentile and/or contemporaneous universe rank, while retaining the raw feature as a baseline.
- **Transfer rationale:** v5 shows `dollar_volume_log` PSI 0.795 between 98-session chronological windows even though the ten-symbol corpus composition is reported unchanged. A relative transform may separate meaningful liquidity surprise from secular price/volume scaling, but it cannot create gross edge by itself.
- **Required decision-time data:** completed-bar dollar volume, a strictly lagged within-symbol reference window, and—only for a cross-sectional rank—the exact universe and completed bars observable at that decision timestamp. Missing symbols and late bars require explicit sentinels; no end-of-day or full-session normalization is allowed.
- **Costs / fills:** unchanged v5 gap-aware fill path and the same four cost scenarios. A new feature requires a separately hashed v6 corpus/manifest; v5 remains immutable and is the unchanged comparator.
- **Validation:** first decompose PSI by symbol, price level, strategy, and calendar window without changing a model. If still justified, register one transformation before fitting, use purged chronological development folds, compare raw-only versus raw-plus-relative features with identical calibration and independent-session aggregation, and leave the untouched holdout unscored unless development gates pass.
- **Failure criteria:** reject if point-in-time universe reconstruction is incomplete, PSI remains >=0.25 without an understood cause, development expectancy is non-positive after costs, profit factor is undefined or <=1.2, fewer than 25 selections or 20 independent sessions result, any fold is non-positive, or improvement is concentrated in one symbol/strategy/regime.
- **Status / 2026-08-08 result:** hypothesis recorded; implementation deferred. Existing diagnostics show the drift across every strategy while ticker composition is unchanged, but they do not yet distinguish price scaling, within-symbol liquidity change, or timestamp/reference-set artifacts. No v6 corpus or model change is justified this week.

## Current champion/challenger state — 2026-08-18

Full trader/firm comparison and V2 operating design: `research/successful-traders-ai-and-v2-system-2026-08-18.md`.

- **Frozen champion/control:** V1 ORB, VWAP trend/imbalance, VWAP reclaim, and momentum suite. It remains a research control; new portfolio admission is disabled by default.
- **Active challenger:** `ATL-H-2026-08-18-01`, point-in-time stocks-in-play scanner context for ORB/momentum. Forward data collection only; no filtering or promotion until at least 100 independent observations across 20 sessions and preregistered net-expectancy/profit-factor/concentration/cost gates pass.
- **One active challenger at a time:** queued mechanisms remain unimplemented until the active challenger resolves or a documented data-quality blocker forces a no-op redesign.
- Continuous improvement means weekly evidence review and controlled challenger replacement—not weekly mutation of strategy rules.

## Explicit non-lessons

- A profitable fund does not prove its exact edge is public or transferable.
- A strong backtest does not prove live profitability.
- Accuracy, AUC, or mid-price direction alone is not an economic objective.
- An LLM's market narrative is not a trade signal until it produces structured, timestamped features that add untouched out-of-sample net utility.
- Complexity is not progress unless it survives costs, chronology, regime shifts, and independent forward evidence.
