from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TrainingMemory:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.examples = self._load()

    def relevant_examples(self, *, symbol: str, strategy_id: str, limit: int = 5) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        symbol = symbol.upper()
        strategy_id = strategy_id.lower()
        scored: list[tuple[int, dict[str, Any]]] = []
        for example in self.examples:
            score = 0
            if str(example.get("symbol") or "").upper() == symbol:
                score += 3
            if strategy_id in str(example.get("strategy_used") or "").lower():
                score += 2
            if example.get("lesson_label") == "candidate_setup":
                score += 1
            if score:
                scored.append((score, example))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [_compact(example) for _, example in scored[:limit]]

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
        return rows


def _compact(example: dict[str, Any]) -> dict[str, Any]:
    keys = ["symbol", "asset_class", "action", "confidence", "strategy_used", "lesson_label", "outcome", "pnl_pct", "reasoning_summary"]
    compacted = {k: example.get(k) for k in keys if k in example}
    if compacted.get("reasoning_summary"):
        compacted["reasoning_summary"] = str(compacted["reasoning_summary"])[:320]
    return compacted
