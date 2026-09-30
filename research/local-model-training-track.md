# V3 local-model training track — 2026-09-30

Goal: learn to train and evaluate models while building a research-grade trading agent. **A pretrained finance-language model is not a pretrained profitable trader.** Text classification, price-outcome prediction, and trade execution are three different jobs.

## Immediate hands-on exercise

Run `.venv/bin/python -m scripts.train_toy_event_classifier`. It builds 600 **synthetic** rows with three invented decision-time features and binary labels, fits a standardized scikit-learn logistic regression on the earlier 400, and compares log loss/Brier score against a constant-prior baseline on the later 200. Re-run it, then change the feature coefficients or inject a regime shift and see what breaks. The result is an educational supervised-learning demonstration only: no market data, return, P&L, model artifact, or broker call. The toy labels intentionally come from a known function; this proves the training loop works, not that a trading signal exists.

## Real training gate

The frozen V3 next-session lane writes actual prospective events, decisions, abstentions, completed IEX bars, and conservative after-cost outcomes. A training set must keep only features genuinely available at each decision; group correlated filings by issuer/session, purge overlapping outcome periods, split chronologically into train/calibration/development and untouched future holdout. Missing IEX minutes remain missing, not wins/losses. Do not train a predictive model on today's 5 ledger rows: historical/smoke records and zero eligible v1 outcomes give it nothing legitimate to learn. Need enough independent complete cases across sessions/regimes to evaluate against no-trade and fixed-rule always-admit baselines after costs. If coverage stays sparse, fix the research design *prospectively*, not by selecting winners from hindsight.

Start with regularized logistic regression and calibrated probabilities on structured context (gap, opening reaction, spread/volume, market regime) using Hermes CPU. Only add a nonlinear tabular challenger if the simple baseline has legitimate signal and enough sample. Train an optional text feature model for sentiment/structured extraction separately and compare the same candidates **with vs without text**. A sentiment label alone is not a buy order or proof of price prediction.

## Local language-model lane

The existing big-ai GPT-OSS server is currently parked/unreachable; do not turn it into an always-on trading hot path just to look more agentic. It could later perform bounded, source-grounded after-hours extraction/critique on demand, shadow-only, with citation and schema checks. ProsusAI/finbert is a well-known finance sentiment classifier, but its Hugging Face model metadata currently has no explicit license; verify model *and underlying training data* rights before installing/using it. An Apache-2.0 tag on a derivative checkpoint does not settle rights to its source corpus. Evaluate any candidate on local, timestamped, human-checkable issuer text before treating it as a useful feature. No LLM may execute orders or select unlabeled training examples by outcome.

A later hands-on fine-tuning lesson could adapt a small licensed text model with LoRA on human-labeled **extraction or thesis-quality** examples; keep chronological holdout and compare with the untuned model. Do not fine-tune an LLM on a handful of profitable trades and call it a trader. Training from scratch is unnecessary here; transfer learning and supervised tabular modeling are the skills worth practicing first.

Model reference: https://huggingface.co/ProsusAI/finbert (metadata/license check via Hugging Face API 2026-09-30). Training API: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html .
