# AI and Algorithmic Trading Success Patterns — 2026-07-30

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

### AQR/Jensen–Kelly–Malamud–Pedersen: optimize what can actually be implemented

Sources:

- https://www.aqr.com/Insights/Research/Working-Paper/Machine-Learning-and-the-Implementable-Efficient-Frontier
- Published/replication references: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4187217 and https://github.com/theisij/ml-and-the-implementable-efficient-frontier

Core finding: cost-agnostic ML tends to chase fleeting signals and excessive turnover. Their framework optimizes portfolio decisions around net returns after transaction costs.

Transferable pattern:

- The objective must include fees, slippage, fill probability, turnover, and capacity.
- Prediction quality and trading quality are different things.
- Optimize portfolio/ranking decisions, not isolated row accuracy.

Trading Lab implication:

- Keep expected net R after modeled costs as the selection objective.
- Add a research-only cross-sectional ranking experiment: rank contemporaneous eligible candidates by predicted net utility, apply a fixed top-k/capacity rule, and compare with absolute-threshold selection using untouched chronological tests.
- Reject improvements that disappear under worse-but-plausible cost scenarios.

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

## Explicit non-lessons

- A profitable fund does not prove its exact edge is public or transferable.
- A strong backtest does not prove live profitability.
- Accuracy, AUC, or mid-price direction alone is not an economic objective.
- An LLM's market narrative is not a trade signal until it produces structured, timestamped features that add untouched out-of-sample net utility.
- Complexity is not progress unless it survives costs, chronology, regime shifts, and independent forward evidence.
