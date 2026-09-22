"""One-shot, read-only SEC earnings intake and Alpaca news entitlement probe.

SEC_CONTACT_EMAIL environment variable is sent to the SEC as User-Agent contact.
No trading, model inference, news storage, scheduled process, or order endpoint.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from trading_lab.catalyst_events import import_jsonl
from trading_lab.config import LabConfig
from trading_lab.v3_sources import alpaca_news_probe, fetch_sec, sec_events
from trading_lab.v3_news import capture_news
from trading_lab.v3_news_history import audit_news, load_snapshots, next_window
from trading_lab.v3_universe import CORE, ELIGIBLE, FINGERPRINT
from trading_lab.v3_ciks import CIKS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="AZO")
    parser.add_argument("--cik", type=int, default=866787)
    parser.add_argument("--ledger", type=Path, default=Path("data/events/catalysts-v1.jsonl"))
    parser.add_argument("--sec", action="store_true", help="one issuer SEC exhibit intake")
    parser.add_argument("--sec-core", action="store_true", help="bounded 24-name core SEC intake")
    parser.add_argument("--sec-eligible", action="store_true", help="bounded 44-name core plus expansion SEC intake")
    parser.add_argument("--alpaca-news", action="store_true")
    parser.add_argument("--capture-news", action="store_true", help="store one bounded incremental news snapshot")
    parser.add_argument("--audit-news", action="store_true", help="offline snapshot overlap and duplicate counts")
    args = parser.parse_args()
    if not any((args.sec, args.sec_core, args.sec_eligible, args.alpaca_news, args.capture_news, args.audit_news)):
        parser.error("choose a SEC mode, --alpaca-news, --capture-news, or --audit-news")
    if sum((args.sec, args.sec_core, args.sec_eligible)) > 1:
        parser.error("choose one SEC intake mode")
    result = {}
    directory = Path("data/events/news-snapshots")
    if args.audit_news:
        result["audit_news"] = audit_news(load_snapshots(directory))
    if args.sec or args.sec_core or args.sec_eligible:
        contact = os.environ.get("SEC_CONTACT_EMAIL")
        if not contact:
            parser.error("SEC_CONTACT_EMAIL required for SEC requests")
        events = []
        names = ([(args.symbol, args.cik)] if args.sec else
                 [(symbol, CIKS[symbol]) for symbol in (CORE if args.sec_core else sorted(ELIGIBLE))])
        for index, (symbol, cik) in enumerate(names):
            if index:
                time.sleep(0.6)  # stay well below SEC fair-access ceiling
            seen = datetime.now(timezone.utc)
            submissions, fetch_document = fetch_sec(cik, contact=contact)
            events.extend(sec_events(submissions, cik=cik, symbol=symbol, observed_at=seen,
                                     fetch_document=fetch_document))
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
    if args.alpaca_news or args.capture_news:
        config = LabConfig.from_env_file(".env")
        if not config.alpaca_api_key or not config.alpaca_secret_key:
            parser.error("local Alpaca credentials are not configured")
        if args.alpaca_news:
            try:
                result["alpaca_news"] = alpaca_news_probe(api_key=config.alpaca_api_key,
                                  secret_key=config.alpaca_secret_key, symbol=args.symbol)
            except urllib.error.HTTPError as exc:
                result["alpaca_news"] = {"reachable": False, "http_status": exc.code}
        if args.capture_news:
            now = datetime.now(timezone.utc)
            start, _ = next_window(load_snapshots(directory), now=now)
            capture = capture_news(api_key=config.alpaca_api_key, secret_key=config.alpaca_secret_key,
                                   observed_at=now, window_start=start)
            if capture["universe_sha256"] != FINGERPRINT:
                raise ValueError("universe version changed mid-capture")
            directory.mkdir(parents=True, exist_ok=True)
            destination = directory / (capture["observed_at"].replace(":", "-").replace("+00-00", "Z") + ".json")
            with os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as output:
                json.dump(capture, output, ensure_ascii=False, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            result["capture_news"] = {"articles": len(capture["articles"]),
                                      "earnings_keyword_leads": sum(bool(x["earnings_keyword_lead"]) for x in capture["articles"]),
                                      "snapshot": str(destination), "universe_sha256": FINGERPRINT}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
