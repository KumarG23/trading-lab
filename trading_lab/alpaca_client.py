from __future__ import annotations

import json
from urllib.parse import urlencode
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class JSONHTTP(Protocol):
    def request_json(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        timeout: float = 20,
    ) -> dict[str, Any]: ...


@dataclass
class UrllibJSONHTTP:
    def request_json(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        timeout: float = 20,
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310 broker endpoint from config
            return json.loads(response.read().decode("utf-8"))


class AlpacaClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        secret_key: str,
        http_client: JSONHTTP | None = None,
        allow_live: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.secret_key = secret_key
        self.http = http_client or UrllibJSONHTTP()
        self.allow_live = allow_live

    def get_account_summary(self) -> dict[str, Any]:
        self._require_paper()
        account = self.http.request_json("GET", f"{self.base_url}/v2/account", headers=self._headers())
        return {
            key: account.get(key)
            for key in [
                "status",
                "currency",
                "buying_power",
                "cash",
                "portfolio_value",
                "pattern_day_trader",
                "trading_blocked",
                "account_blocked",
                "trade_suspended_by_user",
            ]
            if key in account
        }

    def fetch_stock_bars(
        self,
        symbols: list[str],
        *,
        timeframe: str,
        start: str,
        end: str,
        feed: str = "iex",
        data_url: str = "https://data.alpaca.markets",
        batch_size: int = 25,
    ) -> list[dict[str, Any]]:
        self._require_paper()
        normalized_symbols = [symbol.upper() for symbol in symbols]
        bars: list[dict[str, Any]] = []
        for batch in _chunks(normalized_symbols, batch_size):
            query = urlencode(
                {
                    "symbols": ",".join(batch),
                    "timeframe": timeframe,
                    "start": start,
                    "end": end,
                    "feed": feed,
                    "limit": 10000,
                }
            )
            payload = self.http.request_json(
                "GET",
                f"{data_url.rstrip('/')}/v2/stocks/bars?{query}",
                headers=self._headers(),
            )
            bars.extend(_normalize_bars(payload.get("bars") or {}))
        return sorted(bars, key=lambda item: (item["symbol"], item["timestamp"]))

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

    def _require_paper(self) -> None:
        if self.allow_live:
            return
        if "paper-api" not in self.base_url:
            raise ValueError("Refusing non-paper Alpaca base URL without allow_live=True")


def _chunks(items: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        size = len(items) or 1
    return [items[index : index + size] for index in range(0, len(items), size)]


def _normalize_bars(raw_bars: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    for symbol, symbol_bars in raw_bars.items():
        for bar in symbol_bars:
            bars.append(
                {
                    "symbol": symbol.upper(),
                    "timestamp": bar["t"],
                    "open": bar["o"],
                    "high": bar["h"],
                    "low": bar["l"],
                    "close": bar["c"],
                    "volume": bar["v"],
                }
            )
    return sorted(bars, key=lambda item: (item["symbol"], item["timestamp"]))
