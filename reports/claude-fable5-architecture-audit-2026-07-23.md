# Claude Fable 5 Architecture Audit — Agentic Trading Lab

**Audit date:** 2026-07-23
**Audited commit:** `1bba66a9a44307da38669b0d0934e3920382db02`
**Mode:** Read-only independent audit; high effort
**Privacy scope:** Git-tracked source/tests/docs only. No `.env`, journal database, raw market/training data, trade rows, credentials, or private account records were provided.

# Adversarial Architecture Audit — Agentic Trading Lab
**Scope:** Can this system reach its end-state — *a genuinely data-trained local trading model supervised by Codex and Claude*?
**Method:** Read-only review of git-tracked source/tests/docs/policy/reports. No `.env`, no DBs, no `data/`, no training JSONL, no trade rows. The 2026-07-23 Opus audit (`reports/claude-opus-audit-2026-07-23.md`) treated as prior evidence only.

## Blunt verdict

**The lab cannot reach the stated end-state on its current trajectory.** Not because the engineering is sloppy — it's unusually disciplined for a hobby lab (78 tests, fail-closed LLM worker, quarantine-aware exports, honest docs) — but because the *learning problem is set up backwards*. The current design would fine-tune an LLM to imitate the theses of proposals whose labels are single-trade coin flips, computed under fantasy fills, drawn from a sample censored by the very model you're trying to replace, at a data rate roughly two orders of magnitude too small. Every one of those five defects is fatal alone.

The achievable end-state is different and better: **a small classical model (logistic/GBM) trained on counterfactually-resolved candidate outcomes, with LLMs (Codex/Claude) confined to supervision, research, and code** — which is exactly where they add value. The infrastructure you've built is ~70% reusable for that goal.

---

## Findings (ranked by threat to the end-state)

### F1 — The training label is noise. **[fatal as designed]**
`training_export.py:152-161` labels examples `win`/`loss` from one realized trade outcome, and `usable_for_sft` (`training_export.py:105`) gates on `closed AND rule_adherent AND proposed`. Two problems:

- **A single trade's outcome is ~a coin flip.** For a strategy near breakeven expectancy, SFT on "winning" proposals teaches the model to reproduce the *surface features of lucky trades*. There is no label anywhere for "this setup class has positive expectancy across N occurrences" — the only label that matters.
- **The `rule_adherent` filter is vacuous.** Every simulated trade hard-codes `rule_adherent: True` (`backtest.py:177`), and the paper lifecycle never sets it false. The prior audit noted this (`§4: "the metric is uninformative"`); it's still true, and now it silently gates your SFT corpus.

Your own doc knows this: *"raw volume of mediocre setups is just overfit goblin feed"* (`docs/local-model-codex-workflow.md:68`). The code does not act on that sentence.

### F2 — Selective-labels bias: rejected candidates vanish. **[fatal as designed]**
In `autonomous_runner.py:86-103`, candidates rejected by the gate, the dedupe, or the LLM reviewer are simply `continue`d — no journal row, no outcome. In `backtest.py:44-47`, gate-rejected candidates are recorded but never simulated. Consequences:

- You can **never measure whether the LLM reviewer has skill**, because its rejections have no counterfactual outcome. The single cheapest, highest-value experiment in this lab — "does the reviewer beat always-approve?" — is structurally impossible to run.
- A future model trained on this corpus inherits a distribution censored by its predecessor's (unmeasured) biases. This is the classic selective-labels problem, and it compounds every day the loop runs.
- The dataset contains **no "skip" class**. A trading model's most valuable output is *no trade*; the only skip examples anywhere are the 3,604 `hold_filter` rows imported from a *different bot, different strategies, different era* (`docs/testing-readiness.md:40`).

### F3 — Labels are computed under fantasy fills, so even a perfect learner learns the wrong function. **[fatal until fixed]**
`paper_lifecycle.py:75-88` fills exits at the *exact* stop/target price, zero slippage, zero fees; entries fill at exactly `planned_entry` on a touch. The backtest has slippage knobs (`backtest.py:18-19`) but the **live proposal loop that generates your actual training data has none** (`run_orb_proposals.py:77-82` passes no slippage). Worse, the universe scanner actively steers toward $3–80 retail names (`universe_scanner.py:118`, "small-account price band" bonus, `min_dollar_volume=250_000` at `universe_scanner.py:31` — that's *thin*) — i.e., the sim is most wrong precisely where the scanner pushes hardest. The prior audit flagged this (P1-7); it remains open, and its severity is higher than "P1" once you realize **these prices are your labels**.

### F4 — The LLM in the decision path adds no signal and actively poisons the corpus. **[high]**
The reviewer's job, per its own system prompt, is: *"Approve only if the deterministic rule checklist and risk fields are internally consistent"* (`local_worker.py:99-104`). PolicyGate already did that, deterministically (`policy_gate.py:61-135`). So the LLM contributes:
- Stochastic censorship of the dataset (F2), including **availability bias**: any worker exception → auto-reject (`local_worker.py:77-83`), meaning local-server downtime silently deletes data-collection days.
- SFT-target pollution: the review's `thesis` overwrites the candidate's and is journaled (`autonomous_runner.py:132`), then exported as the proposal's thesis (`training_export.py:117`). The end-state model would be trained to imitate **gpt-oss boilerplate attached to coin-flip outcomes**.

Your own build notes say the old bot's core failure was "using Claude as the recurring inner loop" (`docs/build-notes.md:28`). You rebuilt that failure one layer down, with a smaller model and a job that needed no model.

### F5 — Data arithmetic: the corpus can't reach trainable size by living forward. **[fatal for LLM tuning; binding constraint for everything]**
Evidence: **33** proposal/outcome examples as of 2026-07-23 (`docs/testing-readiness.md:42`); ORB effectively fires ≤1/symbol/day (prior audit §5); 50 proposals/day hard cap; ~250 sessions/year. Optimistically ~3–5k examples/year — but intraday signals on a tech-heavy watchlist are one correlated SPY bet (prior audit §4), so *effective* independent samples are ~1k/year. LoRA/SFT for decision quality wants 10⁴–10⁵ *clean, independent, representative* examples. You are 1.5–2 orders of magnitude short, forever, at live-tick speed. The only escape is historical backfill (see roadmap R2-9) — which the backtest harness nearly supports but nobody has aimed at data generation.

### F6 — No evaluation machinery exists at all. **[high]**
`walk-forward` appears in exactly two places in Python: as a hard-coded *blocker string* in reports (`scripts/trading_lab_progress_report.py:126`, `tests/test_daily_summary.py:35`). There is no train/test split, no held-out eval set, no baseline comparison, no calibration measurement, no model promotion criteria anywhere in code or docs. The promotion ladder (`docs/local-model-codex-workflow.md:52-58`) governs *strategies*, not *models*. "Genuinely data-trained" requires "genuinely evaluated," and that subsystem has zero lines of code.

### F7 — Leakage and feedback loops. **[medium-high]**
- **TrainingMemory leaks outcomes into decisions**: `_compact` ships `outcome`/`pnl_pct` of symbol-matched past examples into the review prompt (`training_memory.py:44`), and retrieval scoring *prefers* `candidate_setup` (past winners, `training_memory.py:25-26`), whose label was itself assigned by outcome (`training_data.py:62-71`). That's a survivorship-curated symbol-prior ("NVDA won before → approve NVDA") — a slow-motion overfitting channel. Ironically it's **dead code in the default config**: `gpt-oss` in the model name triggers compact mode with `limit=0` (`local_worker.py:44-51`, `config.py:37`). Complexity with no effect, waiting to become a leak when the model changes.
- **Backtest replay** is clean on signal timing (visible bars ≤ t, entry strictly after `signal_ts`, `backtest.py:86,131`) — good — but fills at signal-bar close on next-bar touch are optimistic on gap-throughs (prior audit §4, confirmed still true).
- **Watchlist look-ahead**: any historical backtest fed the *current* scanner watchlist or `DEFAULT_SCAN_UNIVERSE` (`universe_scanner.py:9-22` — a hand-picked list of 2026 survivors and meme names) selects tomorrow's winners for yesterday's test. No as-of-date universe exists.

### F8 — Non-stationarity is unmodeled and unrecorded. **[medium-high]**
Proposals journal `signal_timestamp` and opening-range levels (`opening_range_breakout.py:117-121`) but **not** the regime state, relative volume, spread proxy, or scanner score at decision time. `bullish_market_regime` (`market_regime.py`) is a live filter, never a recorded feature — so you cannot slice outcomes by regime later, cannot recency-weight, and cannot detect edge decay except by watching aggregate expectancy rot. Also: the regime function returns `True` on missing/insufficient SPY data (`market_regime.py:13-14, 27`) — fail-open for a *risk filter*.

### F9 — Strategy spec ↔ code drift breaks the lab's core contract. **[medium]**
README step 1: "Define a strategy as explicit rules in `strategies/*.yaml`." The ORB YAML requires VWAP alignment for longs, a 09:35–11:00 active window, max 0.15% spread, retest confirmation, and kill conditions at 50 trades (`opening-range-breakout.yaml:16-21, 44-47`). The code implements **none of these** (`opening_range_breakout.py` — no VWAP check, fires until the 14:30 cutoff, no spread data, no kill-condition enforcement anywhere in the repo). The YAMLs are aspirational fiction, which means "rule adherence" as a metric has no ground truth, and strategy discovery is untethered from its own hypotheses.

### F10 — Risk/execution controls: good bones, known holes. **[medium, correctly deprioritized]**
The gate itself is solid (`policy_gate.py`). Still open from the prior audit: no aggregate notional cap across concurrent positions on a $200 cash account; no kill switch/heartbeat. New observations: research lane intentionally bypasses loss breakers (`autonomous_runner.py:80-85` passes zeros) — fine for research, but it means research expectancy includes trades a halted live system would never take, guaranteeing live/research divergence; `market_is_open` ignores holidays and half-days (`paper_lifecycle.py:129-134`), so half-day flattens price off stale closes; and `dashboard_data.py:40,45` defaults missing `portfolio_admitted` to `True`, so **pre-split legacy rows inflate the "portfolio" lane** the post-fix verification said was clean.

### F11 — Supervision exists as vibes, not as a workflow. **[medium]**
Roles are well-written (`docs/local-model-codex-workflow.md:3-24`, `prompts/codex-escalation.md`) but there is no formal loop: no scheduled audit cadence, no machine-checkable gates, and the prior audit's "Post-fix verification … NO_P0_BLOCKERS" was appended to the same report it audits — self-attestation, no artifact trail (I verified one claim above is actually leaky: F10 legacy-row default). Nothing prevents promotion-by-enthusiasm except discipline.

---

## What's genuinely good (credit where due)

- Deterministic code owns sizing/gating; LLM failures fail closed (`local_worker.py:77-83`).
- Live loop and backtest share strategy + gate code (`backtest.py:10-27`) — the single most important backtest property, and rare in hobby labs.
- Same-bar stop-beats-target convention is conservative (`paper_lifecycle.py:27`, `backtest.py`).
- Quarantine-aware training export with atomic writes (`training_export.py:24-26, 87-88`).
- Live-trading refusal interlocks in every script (`run_backtest.py:38-39`, `run_orb_proposals.py:57-59`).
- The docs are honest about their own weaknesses to a degree the code hasn't caught up with.

---

## Ranked roadmap

### R0 — Redefine the end-state (decision, not code; do first)
1. **Change the target model class.** The "data-trained local trading model" should be a **calibrated probability model** — P(target-before-stop | candidate features) — trained with logistic regression/GBM on engineered features, not a fine-tuned LLM emitting trades. LLM fine-tuning stays viable only for the *journal-analyst/reviewer* role (format-following, postmortem drafting), where imitation is the right objective. Evidence: F1, F4, F5.
2. **Move the LLM reviewer to shadow mode.** Log its verdict on every candidate; never let it block journaling or simulation. Its skill becomes measurable (verdict vs. resolved outcome) for the first time. Evidence: F2, F4 (`autonomous_runner.py:101-103`).

### R1 — Fix labels at the source (before collecting one more month of data)
3. **Slippage + fees in `paper_lifecycle`** — mirror the backtest knobs into `run_orb_proposals.py`. Until then every label is optimistic. (F3)
4. **Counterfactual resolution:** simulate outcomes for *all* gate-passing candidates — LLM-rejected, slot-rejected, dedupe-rejected — tagged `counterfactual: true`. This kills selection bias, creates the skip class, and multiplies data volume several-fold from the same market activity. (F2, F12→F2)
5. **Journal decision-time features:** regime bool, relvol, time-of-day bucket, scanner score, spread proxy, on every proposal. These are the future model's inputs *and* the key to regime-sliced eval. Also flip `bullish_market_regime` to fail-closed. (F8)
6. **Enforce YAML↔code parity** (implement ORB's VWAP/active-window/spread filters or amend the YAML), and implement kill conditions as code that demotes strategies automatically. (F9)

### R2 — Build the evaluation machinery (the actual missing subsystem)
7. **Walk-forward harness:** rolling train/test by *session*, session-clustered metrics, per-day expectancy. Wire the "walk-forward promotion gates" report string to real computation. (F6)
8. **Frozen eval sets + baselines:** held-out resolved candidates; score any reviewer (LLM or GBM) on AUC/calibration vs. two baselines — *always-approve* and *approve-iff-gate-passes*. Promotion rule: beat both, out-of-sample, or stay in shadow. (F6)
9. **Historical backfill for corpus size:** run the shared-code backtest over 1–2 years of 1-min bars with slippage, storing candidate/outcome rows in the same schema as live — this is the *only* route to 10⁴+ examples (F5). Precondition: as-of-date universe support, or restrict backfill to SPY/QQQ/mega-caps where survivorship is negligible (F7).

### R3 — Formalize Codex + Claude supervision (proposal)
10. Adopt a **machine-readable readiness artifact**: a `readiness.json` computed from the journal (sample sizes per strategy per regime, OOS expectancy, eod_flatten fraction, slippage-modeled flag, eval-set scores). Then the workflow becomes:
    - **Codex = builder.** TDD tasks only, per `prompts/codex-escalation.md`; never authors promotion decisions.
    - **Claude = auditor.** Scheduled (weekly/monthly) adversarial review that must cite `readiness.json` values and file:line evidence; verdict recorded in `reports/` as a *separate* file from any fix-verification, signed with the commit hash audited (fixes the F11 self-attestation problem).
    - **Local model = trainee.** Lives in shadow mode until it clears R2-8 gates; each promoted version gets a model card (data window, eval scores, known failure regimes).
    - **Neal = sole promoter.** Any lane/gate/model promotion requires the current readiness artifact + auditor sign-off + explicit approval. Prompt confidence still does not count.

### R4 — Execution hardening (correctly last; live money is far away)
11. Aggregate notional ≤ cash, kill switch + heartbeat, holiday/half-day calendar, fix the `portfolio_admitted` legacy-default inflation in `dashboard_data.py:40,45`, and the prior audit's Gate B checklist. (F10)

---

## Bottom line

You built a good laboratory and pointed it at the wrong experiment. The gates, journal, lane split, and shared live/backtest code are worth keeping. But "fine-tune Qwen on our winning proposals" is a dead end four different ways (noise labels, censored sample, fantasy fills, 100× too little data) — and the current loop is quietly baking all four defects into the corpus every trading day. Redefine the trainee as a calibrated classical model over counterfactually-resolved candidates, demote the LLM reviewer to shadow mode until it proves it beats always-approve, and build the evaluation subsystem that currently exists only as a string in a progress report. Do that, and "data-trained local model supervised by Codex and Claude" stops being a slogan and becomes a pipeline.

No live trading. No model promotion. Fix the labels first — everything downstream of them is currently decorative.
