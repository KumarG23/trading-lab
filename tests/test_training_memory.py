import json

from trading_lab.training_memory import TrainingMemory


def test_training_memory_returns_compact_relevant_examples(tmp_path):
    path = tmp_path / "examples.jsonl"
    examples = [
        {"symbol": "AAPL", "strategy_used": "opening-range-breakout", "lesson_label": "hold_filter", "reasoning_summary": "wait for volume"},
        {"symbol": "MSFT", "strategy_used": "vwap", "lesson_label": "candidate_setup", "reasoning_summary": "reclaim with volume"},
        {"symbol": "AAPL", "strategy_used": "opening-range-breakout", "lesson_label": "candidate_setup", "reasoning_summary": "clean breakout"},
    ]
    path.write_text("\n".join(json.dumps(e) for e in examples))

    memory = TrainingMemory(path)
    result = memory.relevant_examples(symbol="AAPL", strategy_id="opening-range-breakout", limit=2)

    assert len(result) == 2
    assert result[0]["symbol"] == "AAPL"
    assert result[0]["strategy_used"] == "opening-range-breakout"
    assert "reasoning_summary" in result[0]
