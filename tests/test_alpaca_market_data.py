from trading_lab.alpaca_client import AlpacaClient


class FakeHTTP:
    def __init__(self):
        self.calls = []

    def request_json(self, method, url, headers=None, payload=None, timeout=20):
        self.calls.append((method, url, headers, payload, timeout))
        return {
            "bars": {
                "AAPL": [
                    {"t": "2026-06-29T13:30:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1000},
                    {"t": "2026-06-29T13:31:00Z", "o": 100.5, "h": 101.5, "l": 100, "c": 101.2, "v": 1500},
                ]
            }
        }


def test_fetch_stock_bars_uses_alpaca_data_endpoint_and_normalizes_bars():
    http = FakeHTTP()
    client = AlpacaClient(base_url="https://paper-api.alpaca.markets", api_key="key", secret_key="secret", http_client=http)

    bars = client.fetch_stock_bars(["aapl"], timeframe="1Min", start="2026-06-29T13:30:00Z", end="2026-06-29T14:00:00Z")

    assert bars[0]["symbol"] == "AAPL"
    assert bars[0]["timestamp"] == "2026-06-29T13:30:00Z"
    assert bars[0]["open"] == 100
    method, url, headers, payload, timeout = http.calls[0]
    assert method == "GET"
    assert url.startswith("https://data.alpaca.markets/v2/stocks/bars?")
    assert "symbols=AAPL" in url
    assert "timeframe=1Min" in url
    assert headers["APCA-API-KEY-ID"] == "key"
