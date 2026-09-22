"""One-shot, read-only SEC earnings intake and Alpaca news entitlement probe.

SEC_CONTACT_EMAIL environment variable is sent to the SEC as User-Agent contact.
No trading, model inference, news storage, scheduled process, or order endpoint.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from trading_lab.catalyst_events import import_jsonl
from trading_lab.config import LabConfig
from trading_lab.v3_sources import alpaca_news_probe, fetch_sec, sec_events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="AZO")
    parser.add_argument("--cik", type=int, default=866787)
    parser.add_argument("--ledger", type=Path, default=Path("data/events/catalysts-v1.jsonl"))
    parser.add_argument("--sec", action="store_true")
    parser.add_argument("--alpaca-news", action="store_true")
    args = parser.parse_args()
    if not args.sec and not args.alpaca_news:
        parser.error("choose --sec or --alpaca-news")
    result = {}
    if args.sec:
        contact = os.environ.get("SEC_CONTACT_EMAIL")
        if not contact:
            parser.error("SEC_CONTACT_EMAIL required for SEC requests")
        seen = datetime.now(timezone.utc)
        submissions, fetch_document = fetch_sec(args.cik, contact=contact)
        # Each fetched page has its own (later) observation time; batch ledger
        # availability is recorded only at the final successful import.
        events = sec_events(submissions, cik=args.cik, symbol=args.symbol, observed_at=seen,
                            fetch_document=fetch_document)
        if events:
            # Keep the input in ignored local storage for audit; not a public artifact.
            source = args.ledger.with_suffix(".sec-input.jsonl")
            source.parent.mkdir(parents=True, exist_ok=True)
            with os.fdopen(os.open(source, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as output:
                os.fchmod(output.fileno(), 0o600)
                output.write("".join(json.dumps(event) + "\n" for event in events))
            result["sec"] = import_jsonl(source, args.ledger)
        else:
            result["sec"] = {"matched_recent_8k_item_202": 0, "appended": 0}
    if args.alpaca_news:
        config = LabConfig.from_env_file(".env")
        if not config.alpaca_api_key or not config.alpaca_secret_key:
            parser.error("local Alpaca credentials are not configured")
        try:
            result["alpaca_news"] = alpaca_news_probe(api_key=config.alpaca_api_key,
                              secret_key=config.alpaca_secret_key, symbol=args.symbol)
        except urllib.error.HTTPError as exc:
            result["alpaca_news"] = {"reachable": False, "http_status": exc.code}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
