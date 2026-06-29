#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.autonomous_runner import AutonomousRunner  # noqa: E402
from trading_lab.config import LabConfig  # noqa: E402
from trading_lab.journal_store import JournalStore  # noqa: E402
from trading_lab.local_worker import LocalAIWorker  # noqa: E402
from trading_lab.training_memory import TrainingMemory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one autonomous paper/proposal pass from candidate JSON.")
    parser.add_argument("candidates_json", type=Path, help="JSON array of candidate proposal objects")
    parser.add_argument("--db", type=Path, default=ROOT / "journal" / "trading-lab.db")
    parser.add_argument("--no-local-ai", action="store_true", help="Use deterministic fallback instead of local model review")
    args = parser.parse_args()

    cfg = LabConfig.from_env_file(ROOT / ".env")
    candidates = json.loads(args.candidates_json.read_text())
    store = JournalStore(args.db)
    training_path = ROOT / "training" / "claude_bot_sanitized_examples.jsonl"
    training_memory = TrainingMemory(training_path)
    worker = None if args.no_local_ai else LocalAIWorker(
        base_url=cfg.local_model_base_url,
        model=cfg.local_model,
        training_memory=training_memory,
    )
    runner = AutonomousRunner(store=store, worker=worker, account_equity=cfg.account_equity)
    ids = runner.process_candidates(candidates)
    print(json.dumps({"logged_proposal_ids": ids, "input_candidates": len(candidates)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
