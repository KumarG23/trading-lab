#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.model_evaluation import purged_walk_forward_evaluate  # noqa: E402


def load_rows(root: Path) -> list[dict]:
    rows = []
    for path in sorted(root.glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Run leakage-safe purged walk-forward evidence evaluation.")
    parser.add_argument("--evidence-root", type=Path, default=ROOT / "data" / "evidence" / "candidate-outcomes-v5")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "model-evaluation.json")
    parser.add_argument("--minimum-samples", type=int, default=1_000)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--embargo-sessions", type=int, default=1)
    parser.add_argument("--final-holdout-fraction", type=float, default=0.2)
    parser.add_argument("--minimum-selected", type=int, default=25)
    parser.add_argument("--minimum-sessions", type=int, default=20)
    args = parser.parse_args()
    rows = load_rows(args.evidence_root)
    result = purged_walk_forward_evaluate(
        rows, minimum_samples=args.minimum_samples, folds=args.folds,
        embargo_sessions=args.embargo_sessions,
        final_holdout_fraction=args.final_holdout_fraction,
        minimum_selected=args.minimum_selected,
        minimum_sessions=args.minimum_sessions,
    )
    result.update({"mode": "offline_research_no_orders", "broker_orders": 0})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(".tmp")
    temp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
