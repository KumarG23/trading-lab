"""Offline V3 forward dossiers from existing private ledgers; no network or order calls."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from trading_lab.catalyst_events import load_ledger
from trading_lab.v3_forward_dossiers import build_dossiers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("data/events/catalysts-v1.jsonl"))
    parser.add_argument("--snapshots", type=Path, default=Path("data/events/market-snapshots"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/v3-forward/dossiers.json"))
    args = parser.parse_args()
    events = load_ledger(args.ledger)
    snapshots = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(args.snapshots.glob("*.json"))]
    report = build_dossiers(events, snapshots)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(".tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(report, output, sort_keys=True, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temp, args.output)
    print(json.dumps({"mode": report["mode"], "events": len(events), "snapshots": len(snapshots),
                      "counts": report["counts"], "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
