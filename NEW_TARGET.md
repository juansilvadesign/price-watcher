# Adding a new target — the watch half

**Answer the four questions first, then write the file.** They are in this order because
each one decides the next, and three of the four have already been got wrong once on a
real event.

⛔ **This covers watching only.** price-watcher never buys. If you also want the price
drop to *reserve* a ticket, do this half first and then
[`../ticket-autobuy/NEW_EVENT.md`](../ticket-autobuy/NEW_EVENT.md).

---

## 1 · Which site is it on?

> **Q: paste the event/product URL.**

| answer | what it costs |
|---|---|
| **buyticketbrasil.com** | Nothing. Existing adapter. Parse four params out of the URL (§5) and you are done. |
| **Anything else** | 🔴 **A new adapter — this is the roadmap's v2 item**, not a config change. One small hand-written module per site is the design; there is no generic scraper and there will not be one. Budget a recon pass, and note the adapter contract has never been exercised against a second site, so the "hub" claim is still a hypothesis. |

## 2 · What is the price range?

> **Q: what does the thing normally trade at, and what price would make you act?**

Two different numbers, doing two different jobs. ⛔ Do not collapse them.

- **The acting price** → `critical_price.price_brl`. Anything under it alerts
  immediately, on entering the band and on each new low inside it, bypassing the 6 h
  window entirely.
- **The anomaly floor** → the *same* number, second job: nothing under it may ever
  become a baseline for `lowest_ever` or `lowest_in_window`.
  🔴 **This is not hypothetical.** On 2026-09-02 a single R$ 66,00 row, present for one
  run and gone the next minute, took the `lowest_ever` record on the 04/09 night — which
  has no expiry, so the rule was **permanently dead on the night it was built for**.
  Set it *just under* the observed trading floor.

⚠️ **On buyticketbrasil, `preco_min` is the fee-inclusive *Valor total*.** R$400 means
R$400 out of pocket, not R$400 + 10% taxa.

🔴 **When the two jobs disagree, split them.** They only fit in one number while the
acting price sits *near* the trading floor. That was true on Rock in Rio — R$200 acting
against an observed R$214,50 floor — and false on the very next event looked at: a R$400
acting price against a **R$ 1.197,90** floor. A `critical_price` of 400 there is a
perfectly good alert trigger and a uselessly loose anomaly floor, because a mispriced
R$ 500,00 row still sails under it and takes `lowest_ever` permanently. Put
`critical_price` just under the trading range, and carry the acting price on
`below_threshold` instead.

⛔ **Do not arm `below_threshold` at a ceiling that already sits above the current
floor.** It is edge-triggered, so it can never fire again — dormant on arrival. That
mistake shipped once and had to be re-baselined in v1.1.

## 3 · Which ticket type / variant do you want?

> **Q: name the sector and the entry class — and quote the site's exact string.**

- `filters.extra.sector` — a list, or `null` to watch every sector.
- `filters.extra.entry_class` — see question 4 before you fill this in.

⛔ **Never guess the string.** A `sector` that matches nothing returns an empty list,
which the invariants read as *"nothing on sale matching this target's filters"* — byte-
identical to a market that never dipped. Read it off a live payload first:

```bash
python3 watch.py --only <id> --verbose --dry-run   # prints every listing, writes nothing
```

⚠️ A typo in an `extra` **field name** raises on a non-empty read, which is the guard
working. A typo in the **value** raises nothing at all. Only the second one is silent.

## 4 · Does the venue check the ticket type at the gate?

> **Q: at this venue, will they actually verify a *Meia Estudante* / *PCD* / *Idoso*?**

This is the question that looks like trivia and decides whether the target can ever fire.

| answer | `entry_class` | why |
|---|---|---|
| **No** — nobody checks | `null` (any class) | ⭐ The cheap market *is* the discounted market. On Rock in Rio's 11/09 night, `Inteira` went under R$200 on exactly **one** day, while the sub-R$200 rows were almost entirely *Meia Estudante / Até 21 / PCD / Professor*. Filtering to `Inteira` would have made the whole price ladder unreachable — silently, while looking configured. |
| **Yes** — they verify | the classes you can actually present | A cheap row you cannot use at the door is not a deal. Expect a much thinner market and set the acting price higher. |
| **Unknown** | ⛔ **Find out before arming.** | Guessing `null` risks a ticket you are turned away with; guessing `Inteira` risks a target that never fires. Both are invisible in a log. |

⛔ **The answer does not carry over between venues.** Rock in Rio does not check — that
is a fact about Rock in Rio, established by attending on a *Meia Idoso* on 05/09. It is
not a fact about the site, and it is not a default.

⚠️ **Neither does how much the answer is worth.** Measure the spread before deciding it
matters: on Rock in Rio the discounted classes *were* the entire sub-R$200 market, so
filtering to `Inteira` made the price range unreachable. In the SOAD `Pista Premium Itaú
Personalité` sector, *Meia Estudante* undercuts *Inteira* by **9%** (R$ 1.197,90 vs
R$ 1.320,00) — same question, almost no consequence.

---

## 5 · Write the file

Copy the template — ⛔ **not** into `targets/`, see the trap below — and fill it in:

```bash
cp targets/_template/target.template.json targets/<id>.json
```

**For a buyticketbrasil URL, the four params come straight out of the query string:**

```
https://buyticketbrasil.com/evento/SLUG?data=MILLIS&evento_local=LOCAL&cidade=CIDADE
                                   └ event_slug  └ data_millis  └ evento_local  └ cidade
```

- **`id` must equal the filename stem** or the registry refuses to load it.
- **Do not bake a *status* into `label`.** A label is what an alert shows you, and a
  claim like "sold out" goes stale silently — that is why the box-office column carries
  a date and the labels do not. ✅ A **confirmed show date is fine** and is the existing
  convention (`Rock in Rio 2026 — 11/09 (sex) · Gramado`); an *unconfirmed* one belongs
  in a `_note_*` key until someone reads it off the page.
- ⚠️ **Check what `data_millis` actually resolves to** before trusting a date:
  `python3 -c "import datetime,zoneinfo;print(datetime.datetime.fromtimestamp(M/1000,zoneinfo.ZoneInfo('America/Sao_Paulo')))"`.
  Rock in Rio's land on a round showtime (22:00:00); the SOAD event's lands on a
  23:59:59 end-of-day sentinel. That BRT *date* later proved correct (15/01/2027), but
  the 23:59:59 was never a showtime and was not evidence of one — and note the slug
  reads `...2026` for a 2027 event, so ⛔ **the slug is not a date either.**

### ⛔ The template must NOT be a loose `.json` in `targets/`

`load_targets` does `sorted(root.glob("*.json"))` and validates **every** file **before**
the `--only` filter is applied. So a placeholder with an unfilled rule raises
`ConfigError` at `watch.py:113` and **aborts the entire run — every target, including
the armed ones.** Verified 2026-09-06 on a throwaway copy:

```
ConfigError -> _TEMPLATE.json: rule 'critical_price' is enabled but 'price_cents'
is missing. An enabled rule with no parameter never fires and looks healthy
-- refusing to load it.
```

`glob("*.json")` is not recursive, which is why the template lives in
`targets/_template/` and is safe there. Keep it there.

## 6 · 🔴 Add the id to a crontab line — a new file is no longer enough

Since the cadence split, **both** cron lines name their targets with `--only`. A target
in `targets/` that is in neither list is **never polled**, while `--list` still shows it
`[on ]`.

```bash
crontab -e     # add the new id to the --only list of the cadence you want
```

- `* * * * *` — one minute, for something you would actually buy.
- `*/5 * * * *` — five minutes, for something you are only tracking.

⚠️ **Verify the edited line under a stripped environment before trusting it**
(`env -i …`), the way every other cron line here was. cron's `PATH` hides
`powershell.exe`, which once aborted every run at startup.

## 7 · Prove it reads

```bash
python3 watch.py --only <id> --dry-run --verbose   # fetch + evaluate, write nothing
python3 -m unittest discover -s tests -t .          # the suite must stay green
```

⛔ **A single empty read is not a sold-out signal.** The site briefly served an empty
`matriz_preco` on 2026-09-02 while the raw payload had data; 10/10 immediate re-probes
returned 21 rows. Re-probe before concluding anything.
