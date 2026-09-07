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

## v1.9 — shipped 2026-09-02
**Per-recipient language** — `en-US` and `pt-BR`, chosen when you approve a friend
(`--add … --lang pt-BR`, `--set-lang` later). Rules now emit a message key and its
parameters; `messages.py` renders the sentence once per language at delivery. Yours,
console and toast stay English. An unknown `lang` is refused, not defaulted.

## Shipped 2026-09-06 — `NEW_TARGET.md`
The interview to run **before** adding a target: which site · what price range · which
ticket type · **does the venue check the ticket type at the gate**. Plus a fill-in
template at `targets/_template/target.template.json`.
⛔ The template lives in a **subdirectory on purpose** — `load_targets` globs
`targets/*.json` and validates every match *before* the `--only` filter, so an unfilled
placeholder sitting in `targets/` aborts the whole run, armed nights included. Verified
on a throwaway copy 2026-09-06; `glob` is not recursive, so `targets/_template/` is safe.

## Shipped 2026-09-06 — SOAD target (watch-only)

`targets/soad2027-01-15.json` — *System of a Down + Faith No More*, Maracanã,
**15/01/2027**, sector `Pista Premium Itaú Personalité`. Verified by a live probe and a
`--dry-run --verbose` read: 14 listings seen, **2 after filters**, no alerts, nothing
written. ⭐ Same adapter, so this does **not** discharge the v2 item below.

- ✅ **`critical_price` R$ 400,00 is the ONLY armed rule** (Juan). The decision is
  binary — he goes only if a ticket can be had under R$400 — so "new low" at R$1.100,00
  is noise. `lowest_ever` and `lowest_in_window` are **off**.
  ⭐ **That is what makes R$400 coherent this far under the market**, and it resolves the
  two-jobs conflict rather than dodging it: job (1), the alert, fires on entering the
  band and on every downward move inside it, comparing against the **last run's**
  minimum — so it cannot ratchet shut. Job (2), the anomaly floor, has no baseline left
  to protect. ⛔ Re-arming `lowest_ever` means revisiting this number the same day.
- ✅ **`entry_class: ["Meia Estudante", "Inteira"]`** — the opposite of every Rock in Rio
  target, because **Maracanã does verify the type**. Both are usable and for different
  reasons: he holds a Meia Estudante, and an Inteira needs no proof from anyone.
  Inteira is the dearer of the two today and is included anyway — 16 months of secondary
  market can invert that, and excluding it could only ever cost a usable sub-R$400 row.
- ⚠️ **Silence is the designed output.** The market is ~3× above the only armed rule, so
  an empty log is *correct* — and indistinguishable from a target no cron line polls.
  ⛔ Liveness comes from `history/cron.log` being touched, never from alerts.

### Still open
- [ ] 🔴 **SOAD is NOT on a cron line, so it is not being polled.** There is currently
      exactly one `watch.py` line (`--only rockinrio2026-09-11`); the `*/5` tracking
      line was removed in the 11/09 replan. `--list` will still show SOAD `[on ]`.
      ⚠️ **Pick the cadence deliberately** — the politeness budget is a design input. A
      one-minute poll on an event 16 months out is ~525k requests/year for a dip that
      needs a 67% crash; `*/15` is ~35k. Tighten it as the date approaches.
- [ ] **Arm the buy block after 11/09** — see
      [`../ticket-autobuy/ROADMAP.md`](../ticket-autobuy/ROADMAP.md).

## v2 — only if v1 earns it
- A **second site**, which is the real test of the hub claim. Until one exists, the
  adapter contract is a hypothesis.

## Explicitly not planned
- A web UI, dashboard or charts. JSONL and a terminal line are the whole interface.
- A generic/AI "guess the price selector" layer. One adapter per site is the design.
- Any form of buying, checkout, cart-holding, login or queue automation. Permanent.
- **Multi-user, hosting, auth** — and neither v1.8 nor v1.9 changed this. What shipped
  is multi-*recipient*: one owner, one set of watches, extra people on the delivery end,
  now reading in their own language. There are no accounts, no per-person targets,
  nobody else can add a target or read the history, and the bot does not act on anything
  anyone sends it. A friend unsubscribes by blocking the bot (or asking you to
  `--remove` them).
- **More languages than the two shipped, or a translation file.** The catalog is a dict
  in `messages.py` and adding a column is a code change on purpose: the import-time
  check refuses a partial one, which a JSON file loaded at runtime could not do without
  becoming the third thing that takes the Telegram sink down at startup.
- **Localised money, dates or number words.** `fmt_brl` already writes pt-BR grouping
  and every price on every watched site is BRL. A locale layer would be machinery with
  no second case to justify it.
- A long-polling bot that answers commands. It would turn a cron-driven one-shot script
  into a daemon, which is a different tool with a different failure mode.
