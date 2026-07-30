#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_evidence import load_rows  # noqa: E402
from trading_lab.evidence import build_readiness, verify_replay_evidence_manifest  # noqa: E402
from trading_lab.journal_store import JournalStore  # noqa: E402
from trading_lab.model_card import build_model_card, render_model_card_markdown  # noqa: E402
from trading_lab.model_evaluation import purged_walk_forward_evaluate  # noqa: E402

SOL_COMMANDS = [
    ".venv/bin/python -m pytest tests -q",
    ".venv/bin/python -m compileall trading_lab scripts tests",
    "git diff --check",
    ".venv/bin/python scripts/weekly_evidence_review.py --smoke",
]


def collect_weekly_review(
    *,
    evidence_root: Path,
    output_dir: Path,
    db_path: Path | None = None,
    dataset_manifest_path: Path | None = None,
    minimum_samples: int = 1_000,
    folds: int = 5,
    embargo_sessions: int = 1,
    minimum_selected: int = 25,
    minimum_sessions: int = 20,
) -> dict[str, Any]:
    dataset_manifest = _read_json(dataset_manifest_path) if dataset_manifest_path and dataset_manifest_path.exists() else None
    if dataset_manifest is None:
        raise RuntimeError("dataset manifest is required for weekly evidence review")
    integrity = verify_replay_evidence_manifest(dataset_manifest, evidence_root)
    if not integrity["verified"]:
        raise RuntimeError(f"evidence integrity verification failed: {integrity['errors']}")
    rows = load_rows(evidence_root)
    if not rows:
        raise RuntimeError(f"no evidence rows found under {evidence_root}")
    evaluation = purged_walk_forward_evaluate(
        rows,
        minimum_samples=minimum_samples,
        folds=folds,
        embargo_sessions=embargo_sessions,
        minimum_selected=minimum_selected,
        minimum_sessions=minimum_sessions,
    )
    store = JournalStore(db_path or output_dir / "weekly-review-empty.db")
    readiness = build_readiness(
        store,
        dataset_manifest=dataset_manifest,
        model_evaluation=evaluation,
        minimum_candidates=minimum_samples,
        evidence_rows=rows,
    )
    card = build_model_card(evaluation=evaluation, readiness=readiness, dataset_manifest=dataset_manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "model_evaluation": output_dir / "model-evaluation.json",
        "readiness": output_dir / "readiness.json",
        "model_card_json": output_dir / "model-card.json",
        "model_card_markdown": output_dir / "model-card.md",
        "weekly_review": output_dir / "weekly-review.json",
    }
    _atomic_write_json(artifacts["model_evaluation"], evaluation)
    _atomic_write_json(artifacts["readiness"], readiness)
    _atomic_write_json(artifacts["model_card_json"], card)
    _atomic_write_text(artifacts["model_card_markdown"], render_model_card_markdown(card))
    selected_model = str(evaluation.get("selected_model") or "")
    selected_metrics = (evaluation.get("model_comparison") or {}).get(selected_model) or {}
    holdout_metrics = evaluation.get("final_holdout") or {}
    review = {
        "ok": True,
        "mode": "offline_weekly_review_no_orders",
        "broker_orders": 0,
        "live_trading_enabled": False,
        "paper_proposal_only_no_orders": True,
        "rows": len(rows),
        "evaluation_status": evaluation.get("status"),
        "selected_model": selected_model or None,
        "walk_forward_expectancy_r": selected_metrics.get("expectancy_r"),
        "walk_forward_profit_factor": selected_metrics.get("profit_factor"),
        "holdout_expectancy_r": holdout_metrics.get("expectancy_r"),
        "holdout_profit_factor": holdout_metrics.get("profit_factor"),
        "blockers": list(evaluation.get("blockers") or []),
        "promotion_ready": False,
        "evidence_integrity": integrity,
        "artifacts": {key: str(path) for key, path in artifacts.items()},
        "sol_commands": SOL_COMMANDS,
    }
    _atomic_write_json(artifacts["weekly_review"], review)
    return review


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect deterministic weekly evidence artifacts. Places no orders.")
    parser.add_argument("--evidence-root", type=Path, default=ROOT / "data" / "evidence" / "candidate-outcomes-v5")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "processed" / "weekly-review")
    parser.add_argument("--db", type=Path, default=ROOT / "journal" / "trading-lab.db")
    parser.add_argument("--dataset-manifest", type=Path, default=ROOT / "data" / "processed" / "evidence-manifest-v5.json")
    parser.add_argument("--minimum-samples", type=int, default=1_000)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--embargo-sessions", type=int, default=1)
    parser.add_argument("--minimum-selected", type=int, default=25)
    parser.add_argument("--minimum-sessions", type=int, default=20)
    parser.add_argument("--smoke", action="store_true", help="Use bounded smoke thresholds for local fixture checks.")
    args = parser.parse_args()
    if args.smoke:
        args.minimum_samples = min(args.minimum_samples, 40)
        args.minimum_selected = min(args.minimum_selected, 2)
        args.minimum_sessions = min(args.minimum_sessions, 10)
    try:
        review = collect_weekly_review(
            evidence_root=args.evidence_root,
            output_dir=args.output_dir,
            db_path=args.db,
            dataset_manifest_path=args.dataset_manifest,
            minimum_samples=args.minimum_samples,
            folds=args.folds,
            embargo_sessions=args.embargo_sessions,
            minimum_selected=args.minimum_selected,
            minimum_sessions=args.minimum_sessions,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}", "broker_orders": 0}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(review, indent=2, sort_keys=True))
    return 0


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _atomic_write_text(path: Path, content: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
