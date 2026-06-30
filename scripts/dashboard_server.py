#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.config import LabConfig  # noqa: E402
from trading_lab.dashboard_data import build_dashboard_snapshot  # noqa: E402
from trading_lab.journal_store import JournalStore  # noqa: E402

DB_PATH = ROOT / "journal" / "trading-lab.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the Agentic Trading Lab dashboard.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Trading Lab dashboard listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 stdlib API
        path = urlparse(self.path).path
        if path == "/health":
            self._json({"ok": True})
        elif path == "/api/snapshot":
            self._json(_snapshot())
        elif path in {"/", "/dashboard"}:
            self._html(render_dashboard(_snapshot()))
        else:
            self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _snapshot() -> dict:
    cfg = LabConfig.from_env_file(ROOT / ".env")
    store = JournalStore(DB_PATH)
    return build_dashboard_snapshot(store, account_equity=cfg.account_equity, live_enabled=cfg.live_trading_enabled)


def render_dashboard(snapshot: dict) -> str:
    active = "".join(_position_html(p) for p in snapshot["active_positions"]) or '<div class="empty">No active simulated positions.</div>'
    proposals = "".join(_proposal_html(p) for p in snapshot["latest_proposals"][:10]) or '<div class="empty">No proposals logged yet.</div>'
    readiness = "".join(_readiness_html(k, v) for k, v in snapshot["readiness"].items())
    by_strategy = "".join(f'<div class="pill"><span>{k}</span><strong>{v}</strong></div>' for k, v in snapshot["proposals_by_strategy"].items()) or '<div class="empty">No strategy counts.</div>'
    metrics = snapshot["metrics"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Agentic Trading Lab</title>
<style>
:root {{ --bg:#080b10; --panel:#101722; --panel2:#0c111a; --text:#e7f0ff; --muted:#8fa2bd; --green:#2ee59d; --red:#ff5c7a; --amber:#ffd166; --blue:#6aa9ff; --purple:#a78bfa; --line:#1d2a3a; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:radial-gradient(circle at top left,#132238 0,#080b10 38%,#05070b 100%); color:var(--text); font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
main {{ max-width:1440px; margin:0 auto; padding:28px; }}
header {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-end; margin-bottom:22px; }}
h1 {{ margin:0; font-size:34px; letter-spacing:-0.04em; }}
.sub {{ color:var(--muted); margin-top:6px; }}
.badge {{ padding:8px 12px; border:1px solid var(--line); border-radius:999px; background:rgba(16,23,34,.78); color:var(--green); font-weight:700; }}
.grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; }}
.card {{ background:linear-gradient(180deg,rgba(16,23,34,.94),rgba(9,13,20,.94)); border:1px solid var(--line); border-radius:22px; padding:18px; box-shadow:0 24px 70px rgba(0,0,0,.35); }}
.kpi .label {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.12em; }}
.kpi .value {{ font-size:34px; font-weight:800; margin-top:8px; letter-spacing:-.05em; }}
.kpi .hint {{ color:var(--muted); margin-top:4px; }}
.section {{ margin-top:16px; }}
.section h2 {{ margin:0 0 12px; font-size:18px; letter-spacing:-.02em; }}
.wide {{ grid-column:span 2; }}
.full {{ grid-column:1 / -1; }}
.list {{ display:grid; gap:10px; }}
.row {{ display:grid; grid-template-columns:auto 1fr auto; gap:12px; align-items:center; padding:12px; border:1px solid var(--line); border-radius:16px; background:rgba(255,255,255,.025); }}
.sym {{ font-weight:900; color:var(--blue); }}
.meta {{ color:var(--muted); font-size:13px; }}
.price {{ font-variant-numeric:tabular-nums; color:#dce8ff; }}
.pills {{ display:flex; flex-wrap:wrap; gap:10px; }}
.pill {{ display:flex; gap:10px; align-items:center; padding:10px 12px; border:1px solid var(--line); border-radius:999px; background:rgba(255,255,255,.035); color:var(--muted); }}
.pill strong {{ color:var(--text); }}
.ready {{ display:grid; grid-template-columns:180px 110px 1fr; gap:10px; padding:12px; border-radius:16px; border:1px solid var(--line); background:rgba(255,255,255,.025); }}
.status-ok {{ color:var(--green); }} .status-blocked,.status-insufficient,.status-forbidden {{ color:var(--amber); }} .status-armed {{ color:var(--red); }}
.empty {{ color:var(--muted); padding:12px; border:1px dashed var(--line); border-radius:16px; }}
footer {{ color:var(--muted); margin-top:18px; font-size:12px; }}
@media (max-width:900px) {{ .grid {{ grid-template-columns:1fr; }} .wide,.full {{ grid-column:auto; }} header {{ display:block; }} .ready {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<main>
<header>
  <div><h1>Agentic Trading Lab</h1><div class="sub">Paper proposal mode. Deterministic rules first; AI in the review chair, not the cockpit.</div></div>
  <div class="badge">LIVE TRADING DISABLED</div>
</header>
<section class="grid">
  {_kpi('Proposals', snapshot['counts']['proposals'], 'all logged proposals')}
  {_kpi('Active', snapshot['counts']['active_positions'], 'simulated positions')}
  {_kpi('Trades', snapshot['metrics']['trade_count'], 'closed paper trades')}
  {_kpi('Expectancy R', snapshot['metrics']['expectancy_r'], 'average R/trade')}
  {_kpi('Total R', snapshot['metrics']['total_r'], 'closed paper trades')}
  {_kpi('PnL', f"${snapshot['metrics']['total_pnl']:.2f}", 'simulated only')}
  {_kpi('Profit Factor', snapshot['metrics']['profit_factor'], 'gross win / gross loss')}
  {_kpi('Rule Adherence', f"{snapshot['metrics']['rule_adherence_rate']:.0%}", 'closed trades')}
  <div class="card wide section"><h2>Active simulated positions</h2><div class="list">{active}</div></div>
  <div class="card wide section"><h2>Latest proposals</h2><div class="list">{proposals}</div></div>
  <div class="card wide section"><h2>Proposals by strategy</h2><div class="pills">{by_strategy}</div></div>
  <div class="card wide section"><h2>Readiness gates</h2><div class="list">{readiness}</div></div>
</section>
<footer>Generated {snapshot['generated_at']} · refreshes every 60s · broker orders enabled: {snapshot['safety']['broker_orders_enabled']}</footer>
</main>
</body>
</html>"""


def _kpi(label: str, value: object, hint: str) -> str:
    return f'<div class="card kpi"><div class="label">{label}</div><div class="value">{value}</div><div class="hint">{hint}</div></div>'


def _position_html(p: dict) -> str:
    return f'<div class="row"><div class="sym">{p["ticker"]}</div><div><strong>{p["strategy_id"]}</strong><div class="meta">{p["direction"]} · {p["status"]} · size {p["position_size"]} · risk ${p["risk_dollars"]}</div></div><div class="price">{p["entry"]} / {p["stop"]} / {p["target"]}</div></div>'


def _proposal_html(p: dict) -> str:
    return f'<div class="row"><div class="sym">{p["ticker"]}</div><div><strong>{p["strategy_id"]}</strong><div class="meta">{p["trigger"]}</div></div><div class="price">{p["entry"]} → {p["target"]}</div></div>'


def _readiness_html(key: str, item: dict) -> str:
    status = item["status"]
    return f'<div class="ready"><strong>{key.replace("_", " ")}</strong><span class="status-{status}">{status.upper()}</span><span class="meta">{item["detail"]}</span></div>'


if __name__ == "__main__":
    raise SystemExit(main())
