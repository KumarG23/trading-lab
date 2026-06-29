#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.training_data import export_claude_bot_examples  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export sanitized Claude_Bot prior-art training examples.")
    parser.add_argument("source_db", type=Path)
    parser.add_argument("output_jsonl", type=Path)
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()
    count = export_claude_bot_examples(args.source_db, args.output_jsonl, limit=args.limit)
    print(f"exported {count} sanitized examples to {args.output_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
