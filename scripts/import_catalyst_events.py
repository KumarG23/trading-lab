"""Import externally obtained catalyst text into the forward-only V3 ledger.

Input is JSONL with provider,url,symbol,kind,published_at,text. No network,
broker, model, or order access. First-seen time is assigned locally at import.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from trading_lab.catalyst_events import import_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=Path("data/events/catalysts-v1.jsonl"))
    args = parser.parse_args()
    print(json.dumps(import_jsonl(args.input, args.ledger), sort_keys=True))


if __name__ == "__main__":
    main()
