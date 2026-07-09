from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class LabConfig:
    mode: str
    account_equity: float
    local_model_base_url: str
    local_model: str
    escalation_provider: str
    alpaca_api_key: str | None
    alpaca_secret_key: str | None
    alpaca_base_url: str
    live_trading_enabled: bool

    @property
    def alpaca_configured(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_secret_key)

    @property
    def alpaca_paper(self) -> bool:
        return "paper-api" in self.alpaca_base_url

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LabConfig":
        env = env or os.environ
        live_enabled = _truthy(env.get("TRADING_LAB_LIVE_ENABLED"))
        return cls(
            mode=env.get("TRADING_LAB_MODE", "paper"),
            account_equity=float(env.get("TRADING_LAB_ACCOUNT_EQUITY", "200")),
            local_model_base_url=env.get("TRADING_LAB_LOCAL_BASE_URL", "http://100.117.167.61:8098/v1"),
            local_model=env.get("TRADING_LAB_LOCAL_MODEL", "ggml-org/gpt-oss-120b-GGUF"),
            escalation_provider=env.get("TRADING_LAB_ESCALATION_PROVIDER", "codex"),
            alpaca_api_key=env.get("ALPACA_API_KEY"),
            alpaca_secret_key=env.get("ALPACA_SECRET_KEY"),
            alpaca_base_url=env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
            live_trading_enabled=live_enabled,
        )

    @classmethod
    def from_env_file(cls, path: str | Path) -> "LabConfig":
        env = dict(os.environ)
        env.update(load_env_file(path))
        return cls.from_env(env)


def _truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def load_env_file(path: str | Path) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        return {}
    parsed: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        parsed[key] = value
    return parsed
