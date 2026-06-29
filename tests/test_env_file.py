from trading_lab.config import LabConfig, load_env_file


def test_load_env_file_parses_unquoted_and_quoted_values(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "ALPACA_API_KEY=abc123",
                "ALPACA_SECRET_KEY='secret value'",
                'ALPACA_BASE_URL="https://paper-api.alpaca.markets"',
                "# ignored",
                "",
            ]
        )
    )

    env = load_env_file(env_path)

    assert env["ALPACA_API_KEY"] == "abc123"
    assert env["ALPACA_SECRET_KEY"] == "secret value"
    assert env["ALPACA_BASE_URL"] == "https://paper-api.alpaca.markets"


def test_lab_config_loads_env_file_without_requiring_shell_export(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("TRADING_LAB_ACCOUNT_EQUITY=2500\nALPACA_API_KEY=key\nALPACA_SECRET_KEY=secret\n")

    cfg = LabConfig.from_env_file(env_path)

    assert cfg.account_equity == 2500
    assert cfg.alpaca_configured is True
    assert cfg.live_trading_enabled is False
