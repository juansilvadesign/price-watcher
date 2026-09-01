# price-watcher — Roadmap

Deliberately short. This is a personal tool with an audience of one; the roadmap is
a queue, not a plan.

## v1 — shipped 2026-09-01
Hub harness + `buyticketbrasil` adapter + Rock in Rio 2026 (3 dates), console alerts,
manual/cron runs, 45 offline tests.

## v2 — only if v1 earns it
- A **second site**, which is the real test of the hub claim. Until one exists, the
  adapter contract is a hypothesis.
- **Telegram sink**, if console + cron turns out to be too passive to act on.

## Explicitly not planned
- A web UI, dashboard or charts. JSONL and a terminal line are the whole interface.
- A generic/AI "guess the price selector" layer. One adapter per site is the design.
- Any form of buying, checkout, cart-holding, login or queue automation. Permanent.
- Multi-user, hosting, auth.
