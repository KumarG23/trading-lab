# Claude Fable 5 Final Audit — Evidence-First Trading Slice

**Audit date:** 2026-07-24  
**Commits audited:** `d45528d`, `86a9236`  
**Mode:** Read-only, high-effort, commit-pinned audit  
**Independent execution verification by Jarvis:** `python3 -m pytest tests -q` → **90 passed**

## Verdict

**PASS — ship-worthy as a research-only slice.** No blocking defects found in `d45528d` + `86a9236`. The planned-risk fix is correct and consistently applied across both lanes; safety invariants (no broker orders, paper-only URLs, shadow-only model) hold under adversarial reading. Remaining issues are realism/coverage gaps appropriate for the roadmap, not release blockers.

## Blocking Findings

**None.** Specific adversarial checks that came back clean:

- Planned-risk R is sourced from stored/candidate `risk_dollars` in both lanes, not recomputed from entry−stop: `trading_lab/journal_store.py:335-336` and `trading_lab/backtest.py:172-173`. Gap-through regression asserts −2.0R on a gap stop: `tests/test_paper_lifecycle.py:141-163`.
- Shadow review dict mutation is fixed (`dict(self.worker.review(candidate))`, `trading_lab/autonomous_runner.py:110`)—a worker returning a shared/cached dict can no longer be polluted by `shadow_status` injection.
- Entry-bar reprocessing chronology is fixed (`bar_dt <= entered_at`, `trading_lab/paper_lifecycle.py:62`) with regression `tests/test_paper_lifecycle.py:189-212`; pre-entry open cannot be used as a stop fill (`allow_open_gap=not entered_this_bar`, `trading_lab/paper_lifecycle.py:87`, `trading_lab/fill_engine.py:57`; test `tests/test_paper_lifecycle.py:166-186`).
- Net-R-first training label ordering correctly labels a net-negative target exit as a loss: `trading_lab/training_export.py:155-163`, regression `tests/test_training_export.py:88-90`.

## Deferred Follow-ups

1. **Partial-bar entry can permanently mask an entry-bar stop.** `scripts/run_orb_proposals.py` fetches bars with `end = now`. Floor `end` to the last completed minute.
2. **Backtest lane silently drops unresolved candidates.** Live simulation flattens at 15:45; historical replay needs the same EOD flatten behavior.
3. **Short-direction fill paths are untested.** Add dedicated short fill/PnL tests before shorts are enabled. Shorts remain disabled by policy.
4. **Symbols with no bars in a batch never expire/flatten.** Halted or missing symbols need explicit lifecycle handling.
5. **Cutoff expiry can cancel an entry that triggered before cutoff within the same fetched batch.** Resolve eligible bars before wall-clock expiry.
6. **SQLite migration needs a legacy-schema regression test.** The additive migration is correct by inspection and was verified successfully against the live database.
7. **Training export joins assume one position/trade per proposal.** Enforce that invariant or avoid a possible Cartesian duplicate later.
8. **Historical replay is O(timestamps × bars)** and currently dedupes to one candidate per strategy/ticker/direction/session; optimize before large-universe backfill.
9. **EOD flatten can use a stale last close** when the symbol has sparse bars.

## Verified Strengths

- **Shadow-only candidate capture:** proposals and paper positions persist regardless of model approval, rejection, worker error, or review cap. New tests cover all three non-happy paths.
- **Policy/model separation:** `PolicyGate` is the sole admission authority. Model output is annotation only under `local_worker_shadow_*` fields.
- **Fill realism and chronology:** shared gap-aware entries/exits, adverse slippage, conservative stop-first same-bar handling, pre-creation-bar exclusion, and no duplicate flatten close.
- **Fees/slippage/PnL/R parity:** live paper lifecycle and historical replay use the same fill primitives and net-PnL/planned-risk-R convention.
- **No-order safety:** no order endpoints exist in the client; non-paper URLs and `live_trading_enabled` are refused; runtime mode remains proposal-only.
- **Training provenance honesty:** schema v2 hard-codes `usable_for_sft: false`, `usable_for_predictive_training: false`, and `artifact_purpose: research_provenance`.
