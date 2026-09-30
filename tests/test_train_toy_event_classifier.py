from scripts.train_toy_event_classifier import train_demo


def test_toy_training_is_repeatable_and_explicitly_not_trading_evidence():
    a = train_demo()
    assert a == train_demo()
    assert a['rows'] == a['train_rows'] + a['chronological_test_rows']
    assert a['mode'] == 'educational_synthetic_only_not_trading_evidence'
    assert a['broker_orders'] == 0 and a['trading_edge_claim'] is False
    assert a['model']['log_loss'] > 0 and a['constant_baseline']['brier'] > 0
