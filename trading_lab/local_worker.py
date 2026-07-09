from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class HTTPClient(Protocol):
    def post_json(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]: ...


@dataclass
class UrllibHTTPClient:
    def post_json(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310 local URL by config
            return json.loads(response.read().decode("utf-8"))


class LocalAIWorker:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        http_client: HTTPClient | None = None,
        training_memory: Any | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.http = http_client or UrllibHTTPClient()
        self.training_memory = training_memory
        self.timeout = timeout

    def review(self, proposal: dict[str, Any]) -> dict[str, Any]:
        compact_mode = "gpt-oss" in self.model.lower()
        training_examples = []
        if self.training_memory is not None:
            training_examples = self.training_memory.relevant_examples(
                symbol=str(proposal.get("ticker") or proposal.get("symbol") or ""),
                strategy_id=str(proposal.get("strategy_id") or ""),
                limit=0 if compact_mode else 3,
            )
        review_proposal = _compact_proposal(proposal) if compact_mode else proposal
        payload = {
            "model": self.model,
            "temperature": 0.0 if compact_mode else 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": _system_prompt(compact=compact_mode),
                },
                {
                    "role": "user",
                    "content": json.dumps({"proposal": review_proposal, "training_examples": training_examples}, sort_keys=True),
                },
            ],
        }
        try:
            response = self.http.post_json(f"{self.base_url}/chat/completions", payload, self.timeout)
            content = response["choices"][0]["message"]["content"]
            parsed = json.loads(_extract_json_text(content))
            return {
                "approved": bool(parsed.get("approved")),
                "thesis": str(parsed.get("thesis") or ""),
                "risk_officer_objection": str(parsed.get("risk_officer_objection") or ""),
                "model_used": self.model,
            }
        except Exception as exc:
            return {
                "approved": False,
                "thesis": "",
                "risk_officer_objection": f"invalid_json_or_local_worker_error: {exc}",
                "model_used": self.model,
            }


def _extract_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    raise ValueError("invalid_json")


def _system_prompt(*, compact: bool) -> str:
    if compact:
        return (
            "You are a strict paper-trading proposal reviewer. Return ONLY minified JSON with "
            "approved:boolean, thesis:string, risk_officer_objection:string. No prose. No markdown. "
            "Approve only if the deterministic rule checklist and risk fields are internally consistent. "
            "Keep thesis and objection under 100 characters each. Do not place trades."
        )
    return (
        "You are the local private analyst for a paper-trading lab. "
        "Return ONLY JSON with approved:boolean, thesis:string, "
        "risk_officer_objection:string. Do not place trades."
    )


def _compact_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "ticker",
        "asset_class",
        "direction",
        "strategy_id",
        "trigger",
        "planned_entry",
        "stop",
        "target",
        "risk_dollars",
        "rule_checklist",
    ]
    return {key: proposal.get(key) for key in keys if key in proposal}
