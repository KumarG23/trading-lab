#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.backtest import run_strategy_backtest  # noqa: E402
from trading_lab.config import LabConfig  # noqa: E402
from trading_lab.evidence import CANDIDATE_OUTCOME_SCHEMA_VERSION, dataset_artifact_digest  # noqa: E402
from trading_lab.decision_features import FEATURE_SCHEMA_SHA256, FEATURE_SCHEMA_VERSION  # noqa: E402

from trading_lab.provenance import repository_code_sha  # noqa: E402
from trading_lab.raw_cache import read_bar_chunk, verify_raw_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay immutable Alpaca chunks into counterfactual evidence rows.")
    parser.add_argument("--raw-manifest", type=Path, default=ROOT / "data" / "processed" / "alpaca-raw-manifest.json")
    parser.add_argument("--output-root", type=Path, default=ROOT / "data" / "evidence" / "candidate-outcomes-v5")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "processed" / "evidence-manifest-v5.json")
    parser.add_argument("--strategies", default="orb,vwap,reclaim,momentum")
    parser.add_argument("--entry-slippage-bps", type=float, default=5.0)
    parser.add_argument("--exit-slippage-bps", type=float, default=10.0)
    parser.add_argument("--fee-per-share", type=float, default=0.005)
    args = parser.parse_args()
    cfg = LabConfig.from_env_file(ROOT / ".env")
    if cfg.live_trading_enabled:
        raise RuntimeError("historical replay refuses live-enabled configuration")
    raw_manifest = json.loads(args.raw_manifest.read_text(encoding="utf-8"))
    verify_raw_manifest(raw_manifest)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for chunk in raw_manifest.get("chunks", []):
        grouped[str(chunk["period"])].append(chunk)
    strategies = [item.strip() for item in args.strategies.split(",") if item.strip()]
    artifacts = []
    session_dates: set[str] = set()

    jobs = [
        (
            period, grouped[period], str(args.output_root), strategies, cfg.account_equity,
            args.entry_slippage_bps, args.exit_slippage_bps, args.fee_per_share,
        )
        for period in sorted(grouped)
    ]
    with ProcessPoolExecutor(max_workers=4) as executor:
        for artifact, dates in executor.map(_replay_period, jobs):
            artifacts.append(artifact)
            session_dates.update(dates)
    artifacts.sort(key=lambda item: item["period"])
    code_sha = repository_code_sha(ROOT)
    dataset_sha = dataset_artifact_digest(artifacts)
    raw_coverage = raw_manifest.get("coverage") or {}
    manifest = {
        "manifest_version": "trading-lab-dataset-manifest-v1",
        "source": "alpaca-iex",
        "code_sha": code_sha,
        "schema_version": CANDIDATE_OUTCOME_SCHEMA_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_schema_sha256": FEATURE_SCHEMA_SHA256,
        "dataset_sha256": dataset_sha,
        "coverage": {
            "bar_count": int(raw_coverage.get("bar_count") or 0),
            "candidate_count": sum(int(item["candidate_count"]) for item in artifacts),
            "start": raw_coverage.get("start"),
            "end": raw_coverage.get("end"),
            "sessions": len(session_dates),
            "symbols": raw_coverage.get("symbols_with_data") or [],
        },
        "mode": "historical_replay_no_orders",
        "broker_orders": 0,
        "strategies": strategies,
        "costs": {
            "entry_slippage_bps": args.entry_slippage_bps,
            "exit_slippage_bps": args.exit_slippage_bps,
            "fee_per_share": args.fee_per_share,
        },
        "artifacts": artifacts,
        "provider_limitations": raw_manifest.get("errors", []),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    temp = args.manifest.with_suffix(".tmp")
    temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(args.manifest)
    print(json.dumps({"ok": True, "coverage": manifest["coverage"], "artifacts": len(artifacts)}, indent=2))
    return 0


def _write_immutable_rows(path: Path, rows: list[dict]) -> dict:
    raw = ("".join(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n" for row in rows)).encode("utf-8")
    compressed = gzip.compress(raw, mtime=0)
    digest = hashlib.sha256(compressed).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"immutable evidence conflict: {path}")
    if not path.exists():
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_bytes(compressed)
        temp.replace(path)
    return {"path": path.name, "sha256": digest, "candidate_count": len(rows)}


def _replay_period(job):
    period, chunks, output_root, strategies, account_equity, entry_bps, exit_bps, fee_per_share = job
    bars = []
    for chunk in chunks:
        bars.extend(read_bar_chunk(chunk["path"], expected_sha256=chunk["sha256"]))
    symbols = sorted({str(bar["symbol"]).upper() for bar in bars})
    result = run_strategy_backtest(
        bars, symbols=symbols, enabled_strategies=strategies,
        account_equity=account_equity, risk_dollars=round(account_equity * 0.01, 2),
        entry_slippage_bps=entry_bps, exit_slippage_bps=exit_bps,
        fee_per_share=fee_per_share, require_bullish_market_regime=True,
    )
    artifact = _write_immutable_rows(Path(output_root) / f"{period}.jsonl.gz", result["candidate_rows"])
    artifact.update({"period": period, "bars": len(bars), "data_quality": result["data_quality"]})
    return artifact, sorted({str(bar["timestamp"])[:10] for bar in bars})


if __name__ == "__main__":
    raise SystemExit(main())
