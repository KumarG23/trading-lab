#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.training_export import export_training_examples  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export compact Trading Lab proposal/outcome examples for future evals and tuning.")
    parser.add_argument("--db", type=Path, default=ROOT / "journal" / "trading-lab.db")
    parser.add_argument("--output", type=Path, default=ROOT / "training" / "proposal_outcomes.jsonl")
    parser.add_argument("--closed-only", action="store_true", help="Only export proposals with closed trades")
    args = parser.parse_args()

    result = export_training_examples(args.db, args.output, include_unclosed=not args.closed_only)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
