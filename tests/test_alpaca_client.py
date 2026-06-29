import json

from trading_lab.alpaca_client import AlpacaClient


class FakeHTTP:
    def __init__(self):
        self.calls = []

    def request_json(self, method, url, headers=None, payload=None, timeout=20):
        self.calls.append((method, url, headers, payload, timeout))
        return {"status": "ACTIVE", "portfolio_value": "1000.00", "cash": "500.00"}


def test_alpaca_client_reads_account_without_exposing_credentials():
    http = FakeHTTP()
    client = AlpacaClient(base_url="https://paper-api.alpaca.markets", api_key="key", secret_key="secret", http_client=http)

    account = client.get_account_summary()

    assert account == {"status": "ACTIVE", "portfolio_value": "1000.00", "cash": "500.00"}
    method, url, headers, payload, timeout = http.calls[0]
    assert method == "GET"
    assert url == "https://paper-api.alpaca.markets/v2/account"
    assert headers["APCA-API-KEY-ID"] == "key"
    assert headers["APCA-API-SECRET-KEY"] == "secret"


def test_alpaca_client_refuses_non_paper_base_url_by_default():
    client = AlpacaClient(base_url="https://api.alpaca.markets", api_key="key", secret_key="secret")

    try:
        client.get_account_summary()
    except ValueError as exc:
        assert "paper" in str(exc)
    else:
        raise AssertionError("expected paper safety guard")
