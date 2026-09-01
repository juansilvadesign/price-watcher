# price-watcher

A personal **hub** for watching prices on arbitrary websites — the ones the generic
trackers (Zoom, Buscapé, Amazon trackers) will never cover because they only
integrate with marketplaces they have deals with.

The design premise: **there is no universal scraper.** Each site gets one small,
hand-written adapter, because an adapter that reads one site correctly beats a
generic one that reads every site approximately. Everything *around* the adapter —
registry, scheduling, history, alert rules, notification — is written once and
shared by every site.

```
watch.py                 CLI: one pass over every enabled target
pricewatch/
  models.py              Reading / Alert / AdapterError, money as integer centavos
  registry.py            targets/*.json -> validated Target objects
  filters.py             target-side filtering (allow-list + deny-list)
  rules.py               the three alert rules
  history.py             append-only JSONL, one file per target
  notify.py              Notifier interface + console sink
  adapters/
    base.py              the adapter contract
    buyticketbrasil.py   site #1
targets/*.json           one file per thing being watched
history/*.jsonl          append-only price record
tests/                   45 tests, fully offline (real captured fixture)
```

**Zero dependencies.** Python 3.10+ standard library only — no venv needed, nothing
to install, nothing to keep up to date.

## Use

```bash
python3 watch.py                       # one pass over all enabled targets
python3 watch.py --verbose             # print every listing, not just the cheapest
python3 watch.py --only rockinrio2026-09-04
python3 watch.py --dry-run             # fetch + evaluate, write nothing
python3 watch.py --list                # show the registry
python3 -m unittest discover -s tests -t .   # 45 tests, no network
```

Exit codes: `0` clean · `1` at least one adapter failed · `2` configuration error ·
`3` alerts fired but delivery failed. Cron and `&&` chains can rely on them.

### Running it unattended

Nothing is scheduled for you. When you want it running, add one line to `crontab -e`:

```cron
MAILTO=""
PATH=/usr/local/bin:/usr/bin:/bin:/mnt/c/Windows/System32/WindowsPowerShell/v1.0
*/30 * * * * /usr/bin/python3 /abs/path/watch.py >> /abs/path/history/cron.log 2>&1
```

No `cd` is needed — targets, history and `.env` all resolve relative to the source
file, not the working directory.

🔴 **The `PATH` line is load-bearing on WSL.** cron's default PATH is roughly
`/usr/bin:/bin`, which hides `powershell.exe`; without it the `toast` sink cannot be
built. `WindowsToastNotifier.CANDIDATES` is the second line of defence, and `build()`
degrades to the surviving sinks rather than aborting — but set the PATH anyway.

⚠️ **A console-only sink plus cron is a watcher that tells no one** — the alert lands
in `cron.log` and you never read it. If you are scheduling this, set
`PRICEWATCH_NOTIFIERS` to include `telegram` (reaches your phone) or `toast`.

⚠️ **Pick the interval deliberately.** On the Rock in Rio targets, availability was
observed moving within *minutes*. A daily poll will miss most of what it exists to
catch; a 1-minute poll is rude to someone else's server. 15–30 min is a reasonable
middle, and tighter only on the day you actually intend to buy.

## Adding a target

Drop a JSON file in `targets/`. The filename stem must equal its `id`.

```json
{
  "id": "rockinrio2026-09-04",
  "label": "Rock in Rio 2026 — 04/09 (sex) · Gramado",
  "adapter": "buyticketbrasil",
  "enabled": true,
  "params": { "...": "adapter-specific" },
  "filters": {
    "min_quantity": 1,
    "extra": { "sector": ["Gramado"], "entry_class": null }
  },
  "rules": {
    "lowest_ever":     { "enabled": true },
    "below_threshold": { "enabled": true, "price_brl": 275.00 },
    "drop_pct":        { "enabled": true, "pct": 5.0 }
  }
}
```

**Filters.** `extra` is an allow-list, `extra_exclude` a deny-list, both keyed on
whatever the adapter puts in a reading's `extra` map. `null` means "all values" and
is a documented no-op. `min_quantity` defaults to **1** — sold-out rows still carry
a price and would otherwise win every `min()`.

**Rules.** All three are **edge-triggered**: they fire on a transition, not a state,
so a cron job does not re-alert every tick and train you to ignore it.

| rule | fires when | needs |
|---|---|---|
| `lowest_ever` | this run beats every price ever recorded (silent on the first run — no baseline) | — |
| `below_threshold` | the cheapest *crosses down* to at-or-below your ceiling | `price_brl` |
| `drop_pct` | the cheapest fell ≥ N% since the previous run | `pct` |
| `price_changed` | the cheapest moved **at all** since the previous run | `direction` (`any`/`down`/`up`), optional `min_delta_brl` |

⚠️ `price_changed` is by far the noisiest — on a resale market polled every 30 minutes
it can fire several times a day, including on moves of a few centavos. Two dials:
`"direction": "down"` to hear only about drops, and `min_delta_brl` to ignore churn.
A bad `direction` value is rejected at load time, not silently ignored.

A rule enabled without its parameter **refuses to load**. An enabled rule that can
never fire looks identical to a healthy one, and you would only find out by never
getting an alert.

## Adding a site

1. Write `pricewatch/adapters/<site>.py` with a class exposing `build_url(target)`
   and `fetch(target) -> list[Reading]`. See `adapters/base.py` for the contract.
2. Register it in `adapters/__init__.py`.
3. Add a fixture in `tests/fixtures/` — **a real captured response**, not a
   hand-written sample — and test the parse against it.

The contract's load-bearing rule: **raise `AdapterError` when the site cannot be
read; return `[]` only for a genuine "nothing on sale".** Collapsing those two into
an empty list turns a broken watcher into a healthy-looking one that reports
nothing forever.

## Notifications

Three sinks ship. Combine them freely — `--notifier console telegram toast`, or set
`PRICEWATCH_NOTIFIERS` in `.env` so the crontab line stays short.

| sink | reaches you when | needs |
|---|---|---|
| `console` | you are looking at the terminal | — |
| `telegram` | anywhere, including your phone | `BOT_API_TOKEN` + `TELEGRAM_CHAT_ID` |
| `toast` | you are at the Windows desktop | WSL + `powershell.exe` (no module to install) |

**Prove delivery before trusting it**, rather than discovering it is broken on the
one alert you cared about:

```bash
python3 watch.py --test-notify                     # uses PRICEWATCH_NOTIFIERS
python3 watch.py --test-notify --notifier toast    # or just one
```

Every sink is attempted even if an earlier one fails, so a Telegram outage does not
cost you the toast. A delivery failure is never swallowed: it exits **3**, which is
distinct from an adapter failure (1) precisely because 3 is the one that means *you
were not told*.

### Telegram setup

`TELEGRAM_CHAT_ID` is **your** chat id — the destination — **not** the bot's. A bot
cannot open a conversation, so the chat has to write to it first:

1. Create the bot with [@BotFather](https://t.me/BotFather); put the token in `.env`
   as `BOT_API_TOKEN`.
2. In Telegram, send your bot any message (`/start` is fine).
3. `python3 tools/telegram_chat_id.py` → prints the id. Put it in `.env`.

The helper distinguishes the failure modes rather than printing an empty list: an
invalid token, a webhook set on the bot (which makes `getUpdates` always empty), and
"you have not messaged it yet" each say so.

### Windows toast (from WSL)

Uses the built-in WinRT toast API through `powershell.exe -EncodedCommand`, under the
stock Windows PowerShell AppId. Nothing to install — no BurntToast.

⚠️ **A clean send is not a visible toast.** `Show()` returns success even when Focus
Assist / Do Not Disturb suppresses the banner. The sink can only report that Windows
accepted it, so do not make `toast` your only channel.

### Adding another channel

Add a class with `name` and `send(target_label, alerts)` to `notify.py`, register it
in `SINKS`. Give it an injectable transport like the two above so it stays testable
with no network. Nothing is stubbed here — an untested notifier that silently no-ops
is worse than not having one.

## The price history is not versioned

`history/*.jsonl` is **gitignored**. Under a 30-minute cron it would dirty the repo
every half hour for a record nobody reads back. ⚠️ **Consequence, stated plainly:
those files exist only on this machine — there is no second copy.** `history/.gitkeep`
keeps the directory alive in a fresh clone.

## Secrets

`.env` holds the bot token and is **gitignored**; `.env.example` documents the keys
and is committed. ⛔ The file is **parsed in Python, never sourced in a shell** —
sourcing leaks every value into shell history and into every child process, and one
malformed line executes arbitrary code. Real environment variables override `.env`.

## Site #1 — buyticketbrasil

Brazilian **secondary-market** ticket marketplace (its own banner: *"não canal
oficial de venda… os preços podem ser superiores aos dos canais oficiais"*).
Reconnaissance write-up:
[`knowledge/ideas/website-price-watcher-scripts.md`](../../ideas/website-price-watcher-scripts.md) § Recon.

What the recon established, and why the adapter looks the way it does:

- Next.js App Router over a Bubble backend — **not** a client-rendered SPA. There is
  no XHR to intercept; every price is server-rendered into the first response.
- The **`RSC: 1`** header returns the same payload at ~half the bytes **and with the
  embedded JSON unescaped**. The plain HTML response escapes it. The adapter
  requires the RSC endpoint for that reason, not just for the size.
- No cookies, no JS, no User-Agent spoofing. The adapter sends an honest,
  identifiable UA rather than pretending to be Chrome.
- `robots.txt` is `Allow: /` with `Disallow: /api/` and `/_next/`. This adapter only
  touches `/evento/…`, which is explicitly allowed.
- ⚠️ `preco_min` is in **centavos**. All money in this project is integer centavos;
  the ÷100 happens only in `fmt_brl` at display time.
- The DOM shows only the single cheapest price. The full ~19-combination matrix is
  in the payload — **a CSS/XPath scraper here would be strictly worse than useless.**

### Rock in Rio 2026

Seven dates, 04/09–13/09. The three shipped targets are 04/09, 05/09 and 11/09.
The other four resolve the same way — `data_millis` and `evento_local` come from
the listing page at `/datas/rockinrio2026`:

| BRT date | `data_millis` | `evento_local` |
|---|---|---|
| 04/09/2026 | 1788570000000 | 1765323377313x720803947984191500 |
| 05/09/2026 | 1788656400000 | 1765323572984x293448430956314600 |
| 06/09/2026 | 1788742800000 | 1765323621728x687317125269815300 |
| 07/09/2026 | 1788829200000 | 1765323705621x670780912989372400 |
| 11/09/2026 | 1789174800000 | 1765323734393x441784445622288400 |
| 12/09/2026 | 1789261200000 | 1765323797528x513509114247905300 |
| 13/09/2026 | 1789347600000 | 1765323829346x381107157350744060 |

Entry class is deliberately **unfiltered**: Rock in Rio does not check ticket type
at the gate, so the cheapest class wins. To restrict it — e.g. to the classes you
hold documentation for — add to a target file:

```json
"extra_exclude": { "entry_class": ["Meia PCD", "Acompanhante PCD", "Meia Idoso"] }
```

## Scope

**It watches and notifies. It never buys.** No checkout, no stored card, no order
placement, no queue automation, no login. That boundary is deliberate and is not a
v1 limitation to be lifted later.
