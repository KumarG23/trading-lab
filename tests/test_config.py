from trading_lab.config import LabConfig


def test_lab_config_defaults_to_paper_and_local_worker():
    cfg = LabConfig.from_env({})

    assert cfg.mode == "paper"
    assert cfg.account_equity == 200.0
    assert cfg.local_model_base_url == "http://100.117.167.61:8098/v1"
    assert cfg.local_model == "ggml-org/gpt-oss-120b-GGUF"
    assert cfg.escalation_provider == "codex"
    assert cfg.live_trading_enabled is False


def test_lab_config_reads_alpaca_paper_credentials_without_enabling_live():
    cfg = LabConfig.from_env(
        {
            "TRADING_LAB_ACCOUNT_EQUITY": "2500",
            "ALPACA_API_KEY": "key",
            "ALPACA_SECRET_KEY": "secret",
            "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        }
    )

    assert cfg.account_equity == 2500.0
    assert cfg.alpaca_configured is True
    assert cfg.alpaca_paper is True
    assert cfg.live_trading_enabled is False
