import json

from trading_lab.journal_store import JournalStore
from trading_lab.training_export import export_training_examples


def test_export_training_examples_writes_compact_proposal_outcomes(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    winner = store.log_proposal(
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        trigger="break",
        planned_entry=101.0,
        stop=100.0,
        target=103.0,
        thesis="good setup",
        rule_checklist={"policy_approved": True, "planned_r_multiple": 2.0},
        model_used="local-test",
    )
    dup = store.log_proposal(
        ticker="MSFT",
        strategy_id="opening-range-breakout",
        direction="long",
        trigger="duplicate",
        planned_entry=201.0,
        stop=200.0,
        target=203.0,
        thesis="duplicate",
        status="duplicate_quarantined",
    )
    store.log_paper_trade(
        proposal_id=winner,
        actual_entry=101.0,
        actual_exit=103.0,
        position_size=1,
        pnl=2.0,
        actual_r_multiple=2.0,
        rule_adherent=True,
        exit_reason="target",
    )
    store.log_paper_trade(
        proposal_id=dup,
        actual_entry=201.0,
        actual_exit=203.0,
        position_size=1,
        pnl=2.0,
        actual_r_multiple=2.0,
        rule_adherent=False,
        mistake_category="duplicate_overlap_quarantined",
    )

    output = tmp_path / "training.jsonl"
    result = export_training_examples(tmp_path / "lab.db", output)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

    assert result["examples"] == 1
    assert result["labels"] == {"win": 1}
    assert rows[0]["schema_version"] == "trading-lab-proposal-outcome-v1"
    assert rows[0]["example_id"] == f"proposal-{winner}"
    assert rows[0]["usable_for_sft"] is True
    assert rows[0]["proposal"]["ticker"] == "AAPL"
    assert rows[0]["outcome"]["r_multiple"] == 2.0


def test_export_training_examples_can_exclude_unclosed_rows(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    store.log_proposal(
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        trigger="break",
        planned_entry=101.0,
        stop=100.0,
        target=103.0,
        thesis="pending setup",
    )

    output = tmp_path / "training.jsonl"
    result = export_training_examples(tmp_path / "lab.db", output, include_unclosed=False)

    assert result["examples"] == 0
    assert output.read_text(encoding="utf-8") == ""
