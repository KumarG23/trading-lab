#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_evidence import load_rows  # noqa: E402
from trading_lab.evidence import build_readiness  # noqa: E402
from trading_lab.journal_store import JournalStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate fail-closed machine-readable promotion readiness.")
    parser.add_argument("--db", type=Path, default=ROOT / "journal" / "trading-lab.db")
    parser.add_argument("--evidence-root", type=Path, default=ROOT / "data" / "evidence" / "candidate-outcomes-v4")
    parser.add_argument("--dataset-manifest", type=Path, default=ROOT / "data" / "processed" / "evidence-manifest.json")
    parser.add_argument("--model-evaluation", type=Path, default=ROOT / "data" / "processed" / "model-evaluation.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "readiness.json")
    parser.add_argument("--minimum-candidates", type=int, default=10_000)
    args = parser.parse_args()
    dataset_manifest = json.loads(args.dataset_manifest.read_text()) if args.dataset_manifest.exists() else None
    model_evaluation = json.loads(args.model_evaluation.read_text()) if args.model_evaluation.exists() else None
    evidence_rows = load_rows(args.evidence_root) if args.evidence_root.exists() else None
    readiness = build_readiness(
        JournalStore(args.db), dataset_manifest=dataset_manifest,
        model_evaluation=model_evaluation, minimum_candidates=args.minimum_candidates,
        evidence_rows=evidence_rows,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(readiness, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(readiness, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
