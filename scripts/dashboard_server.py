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
    return build_dashboard_snapshot(
        store,
        account_equity=cfg.account_equity,
        live_enabled=cfg.live_trading_enabled,
        scanner_path=ROOT / "data" / "processed" / "scanner-watchlist.json",
        telemetry_path=ROOT / "data" / "processed" / "last-paper-watch.json",
    )


def render_dashboard(snapshot: dict) -> str:
    active = "".join(_position_html(p) for p in snapshot["active_positions"]) or '<div class="empty">No active simulated positions. The goblins are contained.</div>'
    proposals = "".join(_proposal_html(p) for p in snapshot["latest_proposals"][:10]) or '<div class="empty">No proposals logged yet.</div>'
    readiness = "".join(_readiness_html(k, v) for k, v in snapshot["readiness"].items())
    by_strategy = "".join(f'<div class="pill"><span>{k}</span><strong>{v}</strong></div>' for k, v in snapshot["proposals_by_strategy"].items()) or '<div class="empty">No strategy counts.</div>'
    scanner = snapshot.get("scanner") or {}
    scanner_cards = "".join(_scanner_html(row) for row in scanner.get("top_matches", [])[:8]) or '<div class="empty">Scanner has not run yet.</div>'
    scanner_watchlist = ", ".join(scanner.get("watchlist", [])[:30]) or "fallback watchlist"
    runtime = snapshot.get("runtime") or {}
    timings = runtime.get("timings_ms") or {}
    metrics = snapshot["metrics"]
    performance = "".join(_kpi(*kpi) for kpi in performance_kpis(metrics))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Market Goblin Containment</title>
<style>
:root {{ --bg:#05020b; --void:#080510; --panel:#11101f; --panel2:#17152a; --text:#f4f0ff; --muted:#a9a0c6; --green:#31f29a; --red:#ff4d7d; --amber:#ffd166; --cyan:#66e6ff; --purple:#8b5cf6; --purple2:#7132f5; --line:rgba(167,139,250,.22); }}
* {{ box-sizing:border-box; }}
body {{ margin:0; min-height:100vh; color:var(--text); font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background: radial-gradient(circle at 18% 10%, rgba(113,50,245,.34), transparent 30%), radial-gradient(circle at 80% 0%, rgba(49,242,154,.16), transparent 24%), linear-gradient(135deg,#030208 0%,#09051a 55%,#12091f 100%); }}
body:before {{ content:""; position:fixed; inset:0; pointer-events:none; opacity:.12; background-image:linear-gradient(rgba(255,255,255,.08) 1px, transparent 1px),linear-gradient(90deg,rgba(255,255,255,.08) 1px, transparent 1px); background-size:42px 42px; mask-image:linear-gradient(to bottom,#000,transparent 78%); }}
main {{ max-width:1520px; margin:0 auto; padding:28px; position:relative; }}
header {{ display:grid; grid-template-columns:1fr auto; gap:22px; align-items:end; margin-bottom:20px; }}
.eyebrow {{ color:var(--green); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; letter-spacing:.22em; text-transform:uppercase; font-size:12px; }}
h1 {{ margin:4px 0 0; font-size:46px; line-height:.95; letter-spacing:-.07em; }}
.sub {{ color:var(--muted); margin-top:10px; max-width:820px; }}
.badge {{ padding:11px 14px; border:1px solid rgba(49,242,154,.35); border-radius:12px; background:rgba(49,242,154,.09); color:var(--green); font-weight:800; box-shadow:0 0 28px rgba(49,242,154,.08); }}
.grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; }}
.card {{ background:linear-gradient(180deg,rgba(23,21,42,.92),rgba(8,5,16,.92)); border:1px solid var(--line); border-radius:22px; padding:18px; box-shadow:0 24px 70px rgba(0,0,0,.42), inset 0 1px 0 rgba(255,255,255,.04); }}
.kpi {{ grid-column:span 3; min-height:128px; position:relative; overflow:hidden; }}
.kpi:after {{ content:""; position:absolute; right:-28px; bottom:-42px; width:120px; height:120px; border-radius:50%; background:radial-gradient(circle,rgba(113,50,245,.34),transparent 62%); }}
.kpi .label {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.16em; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
.kpi .value {{ font-size:38px; font-weight:900; margin-top:10px; letter-spacing:-.06em; }}
.kpi .hint {{ color:var(--muted); margin-top:4px; font-size:13px; }}
.section h2 {{ margin:0 0 12px; font-size:18px; letter-spacing:-.03em; display:flex; align-items:center; gap:8px; }}
.wide {{ grid-column:span 6; }} .full {{ grid-column:1 / -1; }} .third {{ grid-column:span 4; }}
.hero {{ grid-column:span 8; min-height:260px; position:relative; overflow:hidden; }}
.radar {{ position:absolute; right:18px; top:18px; width:170px; height:170px; border-radius:50%; border:1px solid rgba(102,230,255,.25); background:repeating-radial-gradient(circle,transparent 0 24px,rgba(102,230,255,.12) 25px 26px), conic-gradient(from 70deg,rgba(49,242,154,.42),transparent 35%,transparent); filter:drop-shadow(0 0 24px rgba(102,230,255,.18)); }}
.radar:after {{ content:""; position:absolute; inset:50% auto auto 50%; width:6px; height:6px; border-radius:50%; background:var(--green); box-shadow:36px -42px 0 var(--cyan), -50px 28px 0 var(--purple), 22px 48px 0 var(--amber); }}
.list {{ display:grid; gap:10px; }}
.row {{ display:grid; grid-template-columns:72px 1fr auto; gap:12px; align-items:center; padding:12px; border:1px solid rgba(167,139,250,.17); border-radius:16px; background:rgba(255,255,255,.035); }}
.sym {{ font-weight:950; color:var(--cyan); letter-spacing:.02em; }}
.meta {{ color:var(--muted); font-size:13px; }}
.price {{ font-variant-numeric:tabular-nums; color:#f4f0ff; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
.pills {{ display:flex; flex-wrap:wrap; gap:10px; }}
.pill {{ display:flex; gap:10px; align-items:center; padding:10px 12px; border:1px solid rgba(167,139,250,.20); border-radius:12px; background:rgba(113,50,245,.10); color:var(--muted); }}
.pill strong {{ color:var(--text); }}
.ready {{ display:grid; grid-template-columns:180px 110px 1fr; gap:10px; padding:12px; border-radius:16px; border:1px solid rgba(167,139,250,.17); background:rgba(255,255,255,.035); }}
.status-ok {{ color:var(--green); }} .status-blocked,.status-insufficient,.status-forbidden {{ color:var(--amber); }} .status-armed {{ color:var(--red); }}
.empty {{ color:var(--muted); padding:12px; border:1px dashed rgba(167,139,250,.26); border-radius:16px; }}
.scanner {{ grid-column:span 4; }}
.scan-row {{ display:grid; grid-template-columns:64px 1fr 58px; gap:10px; padding:10px 0; border-bottom:1px solid rgba(167,139,250,.12); }}
.scan-row:last-child {{ border-bottom:0; }}
.score {{ color:var(--green); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; text-align:right; }}
.watchlist {{ color:var(--muted); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; line-height:1.55; }}
footer {{ color:var(--muted); margin-top:18px; font-size:12px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
@media (max-width:1000px) {{ .grid {{ grid-template-columns:1fr; }} .kpi,.wide,.full,.third,.hero,.scanner {{ grid-column:auto; }} header {{ grid-template-columns:1fr; }} .ready,.row {{ grid-template-columns:1fr; }} .radar {{ opacity:.2; }} }}
</style>
</head>
<body>
<main>
<header>
  <div><div class="eyebrow">Jarvis Market Goblin Containment Unit</div><h1>Agentic Trading Lab</h1><div class="sub">Dynamic scanner → deterministic strategies → paper journal. AI gets a clipboard, not the launch codes.</div></div>
  <div class="badge">LIVE TRADING DISABLED</div>
</header>
<section class="grid">
  <div class="card hero"><div class="radar"></div><h2>Today's scanner watchlist</h2><p class="watchlist">{scanner_watchlist}</p><div class="pills"><div class="pill"><span>Universe scanned</span><strong>{scanner.get('scan_universe_count', 0)}</strong></div><div class="pill"><span>Top matches</span><strong>{len(scanner.get('top_matches', []))}</strong></div><div class="pill"><span>Loop</span><strong>{timings.get('total', '?')} ms</strong></div><div class="pill"><span>Decision</span><strong>{timings.get('decision', '?')} ms</strong></div></div></div>
  <div class="card scanner"><h2>Radar pings</h2>{scanner_cards}</div>
  {_kpi('Proposals', snapshot['counts']['proposals'], 'all logged proposals')}
  {_kpi('Active', snapshot['counts']['active_positions'], 'simulated positions')}
  {_kpi('Trades', snapshot['metrics']['trade_count'], 'closed paper trades')}
  {performance}
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


def performance_kpis(metrics: dict) -> list[tuple[str, object, str]]:
    trade_count = int(metrics.get("trade_count") or 0)
    total_pnl = float(metrics.get("total_pnl") or 0)
    average_pnl = total_pnl / trade_count if trade_count else 0.0
    return [
        ("P&L", _money(total_pnl), "simulated dollars"),
        ("Average $ / trade", _money(average_pnl), "net after modeled costs"),
        ("Total R", metrics.get("total_r", 0), "normalized risk units"),
        ("Expectancy R", metrics.get("expectancy_r", 0), "average normalized risk/trade"),
        ("Profit Factor", metrics.get("profit_factor", 0), "gross win / gross loss"),
        ("Rule Adherence", f"{float(metrics.get('rule_adherence_rate') or 0):.0%}", "closed trades"),
    ]


def _money(value: float) -> str:
    return f"{'+' if value >= 0 else '-'}${abs(value):.2f}"


def _position_html(p: dict) -> str:
    return f'<div class="row"><div class="sym">{p["ticker"]}</div><div><strong>{p["strategy_id"]}</strong><div class="meta">{p["direction"]} · {p["status"]} · size {p["position_size"]} · risk ${p["risk_dollars"]}</div></div><div class="price">{p["entry"]} / {p["stop"]} / {p["target"]}</div></div>'


def _proposal_html(p: dict) -> str:
    return f'<div class="row"><div class="sym">{p["ticker"]}</div><div><strong>{p["strategy_id"]}</strong><div class="meta">{p["trigger"]}</div></div><div class="price">{p["entry"]} → {p["target"]}</div></div>'


def _scanner_html(row: dict) -> str:
    why = ", ".join(row.get("why", [])) or "candidate"
    return f'<div class="scan-row"><div class="sym">{row["symbol"]}</div><div><strong>${row.get("price", "?")}</strong><div class="meta">{why} · {row.get("change_pct", 0):+}% · RVOL {row.get("relative_volume", 0)}</div></div><div class="score">{row.get("score", 0)}</div></div>'


def _readiness_html(key: str, item: dict) -> str:
    status = item["status"]
    return f'<div class="ready"><strong>{key.replace("_", " ")}</strong><span class="status-{status}">{status.upper()}</span><span class="meta">{item["detail"]}</span></div>'


if __name__ == "__main__":
    raise SystemExit(main())
