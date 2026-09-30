"""Educational model-training exercise on SYNTHETIC rows. Not V3 evidence or a trader.

Run: .venv/bin/python -m scripts.train_toy_event_classifier
Nothing is saved or connected to the trading pipeline. The labels are fabricated
by a known function solely to demonstrate fitting, chronological evaluation,
and comparison with a no-skill baseline.
"""
from __future__ import annotations

import json
import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def train_demo(seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    n = 600
    # These are invented decision-time numeric inputs, NOT market observations.
    features = rng.normal(size=(n, 3))
    latent = 0.8 * features[:, 0] - 0.5 * features[:, 1] + 0.2 * features[:, 2]
    probability = 1 / (1 + np.exp(-latent))
    labels = (rng.random(n) < probability).astype(int)
    # Earlier rows fit, later rows test. Never shuffle outcomes back into inputs.
    x_train, x_test = features[:400], features[400:]
    y_train, y_test = labels[:400], labels[400:]
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=seed))
    model.fit(x_train, y_train)
    baseline = DummyClassifier(strategy="prior")
    baseline.fit(x_train, y_train)
    def score(estimator) -> dict:
        p = estimator.predict_proba(x_test)[:, 1]
        return {"log_loss": round(float(log_loss(y_test, p)), 4),
                "brier": round(float(brier_score_loss(y_test, p)), 4)}
    return {"mode": "educational_synthetic_only_not_trading_evidence",
            "rows": n, "train_rows": len(y_train), "chronological_test_rows": len(y_test),
            "model": score(model), "constant_baseline": score(baseline),
            "broker_orders": 0, "trading_edge_claim": False}


if __name__ == "__main__":
    print(json.dumps(train_demo(), sort_keys=True))
