# V3 forward rule v0 — frozen before outcomes

Status: preregistered 2026-09-30, **no measured edge**. Effective no earlier than `2026-09-30T14:00:00Z` AND the forward-intake service's first successful activation timestamp. An event observed earlier is context only; never backdate a decision from SEC publication time. Change this rule only as a new version after preserving the old rule and all abstentions. All outcomes are offline counterfactuals, not orders.

## Candidate denominator

For every distinct, tamper-checked frozen-universe event with provider `sec-edgar-ex-99.1`, kind `earnings`, and `first_seen_at == available_at`, observed during a real XNYS regular session before 14:30 ET: look for the first *completed* 1-minute IEX bar opening at or after the next minute boundary after actual availability. Fetch it live, not retrospectively; it must be received within 2 minutes after its close and start no later than 10 minutes after observation. Decision time is the actual acquisition time and must leave at least 90 minutes to session close. Record one event-level abstention if no timely bar or price/size/risk criteria fail. No story tone, discretionary LLM vote, or post-event winner selection.

Long-only stop-entry: planned entry one cent above that bar's high, stop one cent below its low, target 2x initial price risk above entry. Require stop width between 0.2% and 5% of entry and target above entry. Integer shares = min(floor($200/entry), floor($2/(entry-stop))). Require at least one share. Entry deadline is 10 minutes after decision (or 90 minutes before actual close, whichever comes first); if deadline is not later than decision, abstain. Resolver applies its independently tested gap/no-fill, slippage/fee and IEX-continuity rules. These numbers are frozen as an experiment, **not tuned or promoted**.

## Comparison and decision

Log every event and abstention; no-fill is a zero-dollar outcome, data-gap/pending are not P&L observations. No-trade baseline is exactly zero exposure and zero P&L. Always-admit baseline resolves every valid fixed-rule plan under identical fills/costs, without a ranker; v0 equals this baseline by construction and cannot claim an incremental model edge. Count distinct events and sessions, resolved/no-fill/gap/pending separately. Do not compute a return or promotion verdict until independent, fully observed forward events exist. Broker-paper orders require a separate explicit Neal approval; live trading remains disabled.

IEX minute bars are not SIP NBBO, and sparse IEX bars cannot be filled in from quotes. Store request feed, receipt time and actual returned bars privately. Record missing minutes as `data_gap`; do not synthesize OHLC or treat a quote as a fill. External source/data corrections or latency can invalidate a run; retain the original decision snapshot, never revise the plan after outcome is visible.
