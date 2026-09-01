# price-watcher — Project Identity (Layer 2)

A personal price/availability watcher **hub**. One shared harness, one small adapter
per site. Non-commercial, audience of one. Lives under `knowledge/projects/` because
it is workspace tooling, not a client deliverable.

Origin: [`knowledge/ideas/website-price-watcher-scripts.md`](../../ideas/website-price-watcher-scripts.md)
— read its **§ Recon** before touching the buyticketbrasil adapter.

## The one architectural rule

**The harness is generic; the adapter is disposable.** Anything that would have to
be rewritten for the next site belongs in `pricewatch/adapters/<site>.py`. Anything
shared belongs in the harness. If you find yourself putting a site name in
`rules.py`, `history.py`, `filters.py` or `registry.py`, that is the bug.

## Invariants — do not quietly break these

- **Money is integer centavos, everywhere inside the package.** Floats are not
  allowed near a threshold comparison. `fmt_brl` is the only place ÷100 happens.
- **`AdapterError` means blind; `[]` means sold out.** Never collapse the two. A
  broken adapter that returns `[]` looks healthy forever and silently stops alerting.
- **A rule enabled without its parameter must refuse to load** (`registry.py`).
  Same failure shape: it looks configured and can never fire.
- **A filter naming a field no reading carries must raise** (`filters.py`). A typo'd
  filter is indistinguishable from a sold-out market.
- **Rules are evaluated before the current run is appended to history.** Otherwise
  every run is its own baseline and nothing can ever fire. `watch.py` owns that order.
- **Rules are edge-triggered.** Level-triggered alerts on a cron schedule train the
  reader to ignore them.
- **Zero runtime dependencies.** Standard library only. A personal tool that needs a
  venv rebuilt after six months of not being touched is a tool that stays untouched.
- **Fixtures are real captured responses**, never hand-written approximations of what
  a site "probably" returns.
- **A delivery failure is never swallowed.** Every sink is attempted, then
  `NotifyError` is raised and `watch.py` exits **3**. A notifier that fails quietly
  turns "you were not alerted" into "there was nothing to alert about".
- **A sink that cannot be constructed fails at startup, not at alert time.** A missing
  `TELEGRAM_CHAT_ID` must not be discovered on the one message that mattered.
- ⛔ **`.env` is parsed, never sourced**, and never committed. Anything interpolated
  into a shell, a PowerShell script, or markup gets escaped at the boundary — ticket
  names are third-party text (an apostrophe in one would otherwise break the toast).

## Boundaries

- **It never buys.** No checkout, no card, no order placement, no queue automation,
  no authenticated session. Not a v1 limitation — a permanent boundary.
- **Respect `robots.txt` per site**, and record the check in the adapter docstring.
- **Choose poll intervals deliberately.** The politeness budget is a design input,
  not an afterthought.

## Before changing an adapter

Re-read the site. The recon that produced `buyticketbrasil.py` overturned three
confident assumptions in a row (Bubble SPA → Next.js SSR · "no metadata" → full
JSON-LD · "just use restock mode" → restock mode cannot read this page's price).
Assume the same about the next one.
