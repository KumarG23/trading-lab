# Risky-Mode Trading Policy

This account is for high-risk short-term/day-trading experiments. It is not Neal's retirement/DCA/boring account.

Risk is allowed. Unbounded stupidity is not.

## Phase gate

Current phase: paper/proposal mode.

Until explicitly upgraded:

- No Robinhood MCP connection.
- No live orders.
- No trade-capable OAuth authorization.
- No agent may place, modify, or cancel orders.
- All outputs are research, scripts, proposals, journals, or postmortems.

## Allowed universe, initial phase

Allowed:

- Liquid US-listed stocks and ETFs.
- Large/mid-cap names with tight spreads.
- Intraday long/short proposals, but paper only for now.
- Strategies with explicit entry, stop, target, exit, and invalidation.

Banned initially:

- Options.
- Crypto.
- Margin abuse.
- Penny stocks.
- Low-float manipulation bait.
- Illiquid names with wide spreads.
- Averaging down without a prewritten rule.
- Revenge trades.
- Trade ideas based only on vibes, social media hype, or model confidence prose.

## Risk rails for future tiny-live mode

These are design targets, not live permissions yet.

- Max risk per trade: 1% of account to start; 2% only after evidence.
- Max daily realized loss: 3R or 5% of account, whichever is smaller.
- Max weekly realized loss: 8R or 12% of account, whichever is smaller.
- Max open positions: 1 initially.
- Max trades/day: 3 initially.
- Cooldown: stop proposing new trades after 2 consecutive losses unless Jarvis explicitly classifies the second loss as rule-compliant and market conditions still match.
- No size increase after a loss.
- No trade without stop/invalidation.
- No overnight holds unless explicitly reclassified as a swing thesis before market close.

## Proposal requirements

Every trade proposal must include:

- ticker
- strategy ID
- long/short direction
- entry trigger
- stop/invalidation
- target(s)
- expected R
- maximum risk in dollars and % account, if account context is available
- thesis
- disconfirming evidence
- market context
- rule checklist
- reason to skip

If any required field is missing, the correct action is `NO TRADE`.

## Evaluation rules

Strategies are judged by:

- expectancy per trade
- R-multiple distribution
- max drawdown
- profit factor
- sample size
- adherence rate
- mistake categories
- robustness across days/market regimes

A strategy with one glorious win and no discipline is not a strategy. It is a slot machine wearing a lab coat.

## Promotion gates

A strategy may move from paper/proposal to tiny-live candidate only after:

- at least 30 logged paper/proposal trades, preferably 50+
- positive expectancy after estimated slippage/fees
- profit factor above 1.2
- max drawdown inside policy limits
- rule adherence above 85%
- documented failure modes
- Jarvis risk review
- Neal explicit approval

## Circuit breakers

Immediately stop proposals for the day if:

- daily drawdown limit is hit
- 2 consecutive rule-breaking proposals occur
- market data is stale or unreliable
- strategy rules are ambiguous
- scanner output cannot be reproduced
- local model or Codex produces inconsistent calculations

## Agent roles

Jarvis:

- orchestrates the lab
- enforces policy
- refuses malformed proposals
- summarizes performance and failure modes

Codex:

- builds scanners/backtests/journal tooling
- converts strategy ideas into testable rules
- validates calculations with scripts

Local Qwen/Qwen3.6:

- reviews private journals and account-aware context
- identifies repeated mistakes and setup clusters
- proposes refinements for human/Jarvis review

Neal:

- owns final promotion decisions
- approves any future live-trading phase change
