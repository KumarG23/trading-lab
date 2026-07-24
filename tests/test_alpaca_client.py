from trading_lab.alpaca_client import AlpacaClient


class FakeHTTP:
    def __init__(self):
        self.urls = []

    def request_json(self, method, url, headers=None, payload=None, timeout=20):
        self.urls.append(url)
        symbol_blob = url.split("symbols=", 1)[1].split("&", 1)[0]
        symbols = symbol_blob.split("%2C")
        return {
            "bars": {
                symbol: [{"t": "2026-06-30T13:30:00Z", "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 100}]
                for symbol in symbols
            }
        }


def test_fetch_stock_bars_batches_symbol_requests_to_avoid_data_api_limit_truncation():
    http = FakeHTTP()
    client = AlpacaClient(base_url="https://paper-api.alpaca.markets", api_key="k", secret_key="s", http_client=http)
    symbols = [f"S{i}" for i in range(45)]

    bars = client.fetch_stock_bars(symbols, timeframe="1Min", start="2026-06-30T13:30:00Z", end="2026-06-30T14:30:00Z", batch_size=20)

    assert len(http.urls) == 3
    assert len(bars) == 45
    assert {bar["symbol"] for bar in bars} == set(symbols)


def test_fetch_stock_bars_follows_alpaca_page_tokens_without_truncation():
    class PagedHTTP:
        def __init__(self):
            self.urls = []

        def request_json(self, method, url, headers=None, payload=None, timeout=20):
            self.urls.append(url)
            if "page_token=" not in url:
                return {
                    "bars": {"AAPL": [{"t": "2026-06-30T13:30:00Z", "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 100}]},
                    "next_page_token": "next token",
                }
            return {
                "bars": {"AAPL": [{"t": "2026-06-30T13:31:00Z", "o": 1.5, "h": 2, "l": 1, "c": 1.7, "v": 120}]},
                "next_page_token": None,
            }

    http = PagedHTTP()
    client = AlpacaClient(base_url="https://paper-api.alpaca.markets", api_key="k", secret_key="s", http_client=http)

    bars = client.fetch_stock_bars(["AAPL"], timeframe="1Min", start="2026-06-30T13:30:00Z", end="2026-06-30T14:30:00Z")

    assert len(bars) == 2
    assert len(http.urls) == 2
    assert "page_token=next+token" in http.urls[1]
