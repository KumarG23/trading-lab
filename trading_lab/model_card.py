from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_model_card(
    *,
    evaluation: dict[str, Any] | None,
    readiness: dict[str, Any] | None,
    dataset_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    evaluation = evaluation or {}
    readiness = readiness or {}
    blockers = sorted(set((evaluation.get("blockers") or []) + (readiness.get("blockers") or [])))
    return {
        "model_card_version": "trading-lab-model-card-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "purpose": "Offline research evaluation for proposal admission. This artifact does not authorize trading.",
        "dataset": {
            "schema_version": (dataset_manifest or {}).get("schema_version"),
            "dataset_sha256": (dataset_manifest or {}).get("dataset_sha256"),
            "coverage": (dataset_manifest or {}).get("coverage") or {},
        },
        "feature_schema_version": evaluation.get("feature_schema_version"),
        "feature_coverage": evaluation.get("feature_coverage") or {},
        "quality": readiness.get("quality") or {},
        "strategy_samples": (readiness.get("counts") or {}).get("by_strategy") or {},
        "model_comparison": evaluation.get("model_comparison") or {},
        "no_fill_model": evaluation.get("no_fill_model") or {},
        "selected_model": evaluation.get("selected_model"),
        "final_holdout": evaluation.get("final_holdout") or {},
        "stability": evaluation.get("stability") or {},
        "blockers": blockers,
        "promotion_ready": False,
        "no_order_safety": {
            "mode": "paper_proposal_only_no_orders",
            "broker_orders_enabled": False,
            "live_trading_enabled": False,
        },
        "recommendations": _recommendations(blockers, evaluation, readiness),
    }


def render_model_card_markdown(card: dict[str, Any]) -> str:
    comparison = card.get("model_comparison") or {}
    lines = [
        "# Trading Lab Evidence Model Card",
        "",
        f"Generated: {card.get('generated_at')}",
        "",
        "## Summary",
        card.get("purpose") or "",
        f"Promotion ready: {str(card.get('promotion_ready')).lower()}",
        "",
        "## No-order safety",
        f"Mode: {(card.get('no_order_safety') or {}).get('mode')}",
        f"Broker orders enabled: {(card.get('no_order_safety') or {}).get('broker_orders_enabled')}",
        f"Live trading enabled: {(card.get('no_order_safety') or {}).get('live_trading_enabled')}",
        "",
        "## Dataset",
        f"Schema: {(card.get('dataset') or {}).get('schema_version')}",
        f"Dataset hash: {(card.get('dataset') or {}).get('dataset_sha256')}",
        "",
        "## Feature coverage",
        f"Feature schema: {card.get('feature_schema_version')}",
    ]
    required = ((card.get("feature_coverage") or {}).get("required") or {})
    if required:
        for name, item in sorted(required.items()):
            lines.append(f"- {name}: {item.get('coverage')} coverage ({item.get('present')} present)")
    else:
        lines.append("- No feature coverage diagnostics available.")
    lines.extend(["", "## Evidence quality"])
    quality = card.get("quality") or {}
    for label in ("warning_flags", "exclusion_flags", "fatal_flags"):
        lines.append(f"- {label}: {quality.get(label) or {}}")
    lines.extend(["", "## Strategy samples"])
    for strategy, count in sorted((card.get("strategy_samples") or {}).items()):
        lines.append(f"- {strategy}: {count}")
    lines.extend(["", "## Baseline and model comparison"])
    if comparison:
        for name, metrics in sorted(comparison.items()):
            lines.append(
                f"- {name}: selected {metrics.get('selected')}, "
                f"sessions {metrics.get('selected_sessions')}, "
                f"expectancy R {metrics.get('expectancy_r')}, "
                f"expectancy $ {metrics.get('expectancy_dollars')}"
            )
    else:
        lines.append("- No model comparison available.")
    no_fill = card.get("no_fill_model") or {}
    lines.extend([
        "",
        "## No-fill risk model",
        f"- Status: {no_fill.get('status') or 'unavailable'}",
        f"- Target: {no_fill.get('target') or 'probability_of_no_fill'}",
        f"- Samples: {no_fill.get('samples') or 0}",
        f"- ROC AUC: {no_fill.get('roc_auc')}",
    ])
    lines.extend(["", "## Blockers"])
    blockers = card.get("blockers") or []
    lines.extend([f"- {blocker}" for blocker in blockers] or ["- none"])
    lines.extend(["", "## Recommendations"])
    lines.extend([f"- {item}" for item in (card.get("recommendations") or [])])
    return "\n".join(lines) + "\n"


def _recommendations(blockers: list[str], evaluation: dict[str, Any], readiness: dict[str, Any]) -> list[str]:
    recommendations = []
    if any("feature_coverage" in blocker for blocker in blockers):
        recommendations.append("Regenerate or enrich evidence with the v5 decision feature contract before promotion review.")
    if any("fatal_quality" in blocker for blocker in blockers):
        recommendations.append("Repair or exclude rows with fatal provenance, chronology, stale-data, or impossible OHLC defects.")
    if "human_promotion_not_granted" in blockers:
        recommendations.append("Keep promotion disabled until Jarvis completes an explicit human review.")
    if not evaluation or evaluation.get("status") != "evaluated":
        recommendations.append("Run the bounded evaluation smoke first, then the full historical evaluation when practical.")
    if not recommendations:
        recommendations.append("Keep paper-only shadow evaluation running and review stability before any promotion decision.")
    return recommendations
