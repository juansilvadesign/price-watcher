# price-watcher — Roadmap

Deliberately short. This is a personal tool with an audience of one; the roadmap is
a queue, not a plan.

## v1 — shipped 2026-09-01
Hub harness + `buyticketbrasil` adapter + Rock in Rio 2026 (3 dates), console alerts,
manual/cron runs, 45 offline tests.

## v1.1–v1.8 — shipped 2026-09-01/02
Telegram + Windows toast sinks · four more rules (`price_changed`, `lowest_in_window`,
`critical_price` and its anomaly floor) · all 7 Rock in Rio nights on a split cron ·
**sharing the bot with approved friends** (`subscribers.json`).

## v2 — only if v1 earns it
- A **second site**, which is the real test of the hub claim. Until one exists, the
  adapter contract is a hypothesis.

## Explicitly not planned
- A web UI, dashboard or charts. JSONL and a terminal line are the whole interface.
- A generic/AI "guess the price selector" layer. One adapter per site is the design.
- Any form of buying, checkout, cart-holding, login or queue automation. Permanent.
- **Multi-user, hosting, auth** — and v1.8 did not change this. What shipped is
  multi-*recipient*: one owner, one set of watches, extra people on the delivery end.
  There are no accounts, no per-person targets, nobody else can add a target or read
  the history, and the bot does not act on anything anyone sends it. A friend
  unsubscribes by blocking the bot (or asking you to `--remove` them).
- A long-polling bot that answers commands. It would turn a cron-driven one-shot script
  into a daemon, which is a different tool with a different failure mode.
