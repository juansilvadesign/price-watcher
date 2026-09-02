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
  rules.py               the six alert rules
  history.py             append-only JSONL, one file per target
  notify.py              Notifier interface + console / telegram / toast sinks
  subscribers.py         who receives Telegram alerts besides you
  telegram_api.py        Bot API client; decodes Telegram's error envelope once
  adapters/
    base.py              the adapter contract
    buyticketbrasil.py   site #1
tools/
  telegram_chat_id.py    find YOUR chat id
  telegram_subscribers.py  approve / list / disable friends
targets/*.json           one file per thing being watched
history/*.jsonl          append-only price record
subscribers.json         approved recipients (gitignored, absent until you add one)
tests/                   187 tests, fully offline (real captured fixture)
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
python3 -m unittest discover -s tests -t .   # 187 tests, no network
```

Exit codes: `0` clean · `1` at least one adapter failed · `2` configuration error ·
`3` alerts fired but delivery failed. Cron and `&&` chains can rely on them.

**Failures are per target, not per run.** A misconfigured or unreadable target reports
itself and the run carries on to the rest; the exit code still reflects the worst
outcome (`2` outranks `1` outranks `3`). Targets load in alphabetical order, so a
whole-run abort used to mean which nights you lost was decided by filename.

### Running it unattended

Two cron lines, one per cadence:

```cron
MAILTO=""
PATH=/usr/local/bin:/usr/bin:/bin:/mnt/c/Windows/System32/WindowsPowerShell/v1.0

# the nights you would actually buy
* * * * * /usr/bin/python3 /abs/path/watch.py --only rockinrio2026-09-04 rockinrio2026-09-05 rockinrio2026-09-11 >> /abs/path/history/cron.log 2>&1

# the nights you are only tracking
*/5 * * * * /usr/bin/python3 /abs/path/watch.py --only rockinrio2026-09-06 rockinrio2026-09-07 rockinrio2026-09-12 rockinrio2026-09-13 >> /abs/path/history/cron.log 2>&1
```

**Two cadences, deliberately.** With only record-beating rules armed, alert volume is
set by how often a record is broken — not by the poll rate — so polling fast costs
notifications nothing and buys the ability to catch a dip that appears and sells
inside a gap. What it costs is **requests**. All seven nights at one minute would be
**~10,080/day** against a single site; the three you would buy at one minute plus the
four you are tracking at five is **~5,472/day**, with no loss of resolution where a
purchase would actually happen.

🔴 **`--only` is load-bearing on BOTH lines.** `watch.py` with no `--only` runs every
enabled target, so a missing flag on the `*/5` line silently puts all seven back on
the one-minute schedule — and the output looks almost identical, four extra blocks
being the only tell.

🔴 **A target in `targets/` but named in neither `--only` list is never polled.**
Since the split, adding a target file is no longer enough — the crontab has to name
it too. This is the failure mode that looks most like everything working: the file is
valid, `--list` shows it `[on ]`, and nothing ever reads it.

No `cd` is needed — targets, history and `.env` all resolve relative to the source
file, not the working directory.

🔴 **The `PATH` line is load-bearing on WSL.** cron's default PATH is roughly
`/usr/bin:/bin`, which hides `powershell.exe`; without it the `toast` sink cannot be
built. `WindowsToastNotifier.CANDIDATES` is the second line of defence, and `build()`
degrades to the surviving sinks rather than aborting — but set the PATH anyway.

⚠️ **A console-only sink plus cron is a watcher that tells no one** — the alert lands
in `cron.log` and you never read it. If you are scheduling this, set
`PRICEWATCH_NOTIFIERS` to include `telegram` (reaches your phone) or `toast`.

⚠️ **The interval and the armed rules have to be chosen together.** A fast poll with
a sensitive rule (`price_changed`) is a notification firehose; a fast poll with
`lowest_ever` alone is quiet, because a record can only be broken so often. This
project ships the second combination. Measured over the first 329 cron runs, the
armed rules fired **6 times — 1.8% of runs**.

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

**Rules.** All of them are **edge-triggered**: they fire on a transition, not a state,
so a cron job does not re-alert every tick and train you to ignore it.

| rule | fires when | needs |
|---|---|---|
| `lowest_ever` | this run beats every price ever recorded (silent on the first run — no baseline) | — |
| `below_threshold` | the cheapest *crosses down* to at-or-below your ceiling | `price_brl` |
| `drop_pct` | the cheapest fell ≥ N% since the previous run | `pct` |
| `price_changed` | the cheapest moved **at all** since the previous run | `direction` (`any`/`down`/`up`), optional `min_delta_brl` |
| `lowest_in_window` | this run beats everything standing in the last N hours | `window_hours` |
| `critical_price` | the price is **below** your anomaly floor — on entering the band, then on each new low inside it | `price_brl` |

**As shipped, `lowest_ever` and `critical_price` are armed everywhere, and
`lowest_in_window` on the three nights you would actually buy.** The rest are
configured but disabled — flip `enabled` to re-arm one.

⭐ **Why both.** `lowest_ever` **ratchets shut**: every record it sets raises its own
bar, so the longer it runs the less likely it is to speak — and the day you buy is the
day its bar is highest. On 2026-09-01 the 05/09 night was trading at R$ 330,00 against
a R$ 242,00 record: a **26.7% fall** before it would have said anything. A rolling
window cannot ratchet, because its baseline expires. The two answer different
questions — *"is this the best price ever?"* versus *"is this the best price right
now?"* — and on a buying day you need the second.

⚠️ **`lowest_in_window` is near-degenerate until the history is older than the
window.** With 6h of history and a 6h window it is just `lowest_ever` wearing a
different name; it only becomes selective as the log ages past `window_hours`.

Each successive record fires again, with no cooldown: if the record is R$ 230,00 and
the price hits R$ 228,00 it alerts, and when it hits R$ 220,00 a minute later it
alerts again, because the record moved down with it. A large drop that is **not** a
record (R$ 400 → R$ 370 while the record is R$ 230) stays silent by design.

⚠️ `price_changed` is by far the noisiest of the disabled three — polled every minute
it fires on moves of a few centavos. Two dials if you ever re-arm it:
`"direction": "down"`, and `min_delta_brl` to ignore churn. A bad `direction` value is
rejected at load time, not silently ignored.

A rule enabled without its parameter **refuses to load**. An enabled rule that can
never fire looks identical to a healthy one, and you would only find out by never
getting an alert.

### 🔴 `critical_price` — the anomaly floor, and why it is not just another threshold

Two rules here are **absolute** (`below_threshold`, `critical_price`): they compare
against a number you wrote down. The other three are **relative**: they compare against
a baseline built from history. Only the absolute kind is safe against a mispriced
reading — which is the entire reason this rule exists.

`critical_price` does **two jobs from one number**:

1. **Alerts immediately** on any price below the floor, bypassing the 6h window. It
   fires on *entering* the band and again on each *new low inside* it, then stays quiet
   while a sub-floor price merely holds. A market falling through the floor is reported
   the whole way down; a stuck mispricing does not alert once a minute forever.
2. **Excludes that price from every baseline.** Nothing below the floor can become the
   reference for `lowest_ever` or `lowest_in_window`, so an atypical discount cannot
   mute the normal drop alerts that follow it.

⛔ **The second job is the one that bites, and it is not hypothetical.** On
**2026-09-02T13:46Z** a single `Gramado || Inteira` at **R$ 66,00** — present for one
run, gone the next minute, on a night trading at R$ 220,00 — took the `lowest_ever`
record for 04/09. `lowest_ever` has **no expiry**, so the rule was *permanently dead on
the night it was built for*, and the 6h window was muted alongside it for six hours.
Both rules were armed, both looked healthy, and neither could ever have spoken again.

⭐ **The exclusion is applied on READ, not on write.** Two consequences, and the first
is why it was done that way: it **heals retroactively**, so arming the floor repairs a
history that is already poisoned (04/09's baseline went straight back to R$ 220,00). And
the JSONL stays a faithful record of what the site actually served — a history that
quietly omits the bad row cannot be audited.

⭐ **Set the floor just under the night's observed trading floor**, not at a price you
would like to pay. It answers "is this too cheap to be real?", not "is this a good
deal?" — a genuine bargain is what `lowest_in_window` is for. As shipped: R$ 200,00 on
the three buy nights (observed lows R$ 214,50–242,00), and R$ 250,00 / R$ 350,00 /
R$ 450,00 on the tracking nights, which trade two to three times higher. Replayed over
~1,100 recorded runs across all seven targets, it fires **once** — on the real R$ 66,00.

⚠️ Disabling `critical_price` disables the baseline protection with it. One switch, on
purpose: a target must never end up alerting on anomalies while still baselining them.

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

`[]` then travels the whole way as data: the filters short-circuit on it (there is
nothing to typo-check a filter against) and `watch.py` prints "nothing on sale" and
moves to the next target. The filter typo-guard still raises on any **non-empty**
read — that is where a typo is actually distinguishable from a sold-out market.

## Notifications

Three sinks ship. Combine them freely — `--notifier console telegram toast`, or set
`PRICEWATCH_NOTIFIERS` in `.env` so the crontab line stays short.

| sink | reaches you when | needs |
|---|---|---|
| `console` | you are looking at the terminal | — |
| `telegram` | anywhere, including your phone — yours and your friends' | `BOT_API_TOKEN` + `TELEGRAM_CHAT_ID` (+ optional `subscribers.json`) |
| `toast` | you are at the Windows desktop | WSL + `powershell.exe` (no module to install) |

**Prove delivery before trusting it**, rather than discovering it is broken on the
one alert you cared about:

```bash
python3 watch.py --test-notify                     # uses PRICEWATCH_NOTIFIERS
python3 watch.py --test-notify --notifier toast    # or just one
```

⚠️ **`--test-notify` fans out.** It sends to every subscriber, which is exactly right for
testing the fan-out and wrong for checking one friend you just added — use
`tools/telegram_subscribers.py --test <chat_id>` for that.

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

### Sharing the bot with friends

The bot is **public** — anyone who finds it can message it — so being able to reach the
bot is not the same as being on the list. You are the gate:

```bash
# 1. the friend opens your bot link and sends anything (/start is fine)
python3 tools/telegram_subscribers.py --pending            # who is waiting
python3 tools/telegram_subscribers.py --add 1122334455 --name rafa
python3 tools/telegram_subscribers.py --test 1122334455    # prove it reaches them
python3 tools/telegram_subscribers.py                      # the current list
```

They now receive **every alert for every target**, identical to yours, from the same run.
There is no per-person target filtering — deliberately, so there is no second place a
typo can silently mute somebody. Removing them is `--remove`; `--disable` keeps the entry
and stops sending.

**Two tiers, and they are not symmetric:**

| | reached | a failure means |
|---|---|---|
| **you** (`TELEGRAM_CHAT_ID`) | first, every run | `NotifyError` → exit **3** |
| **a subscriber** (`subscribers.json`) | after you, best-effort | a warning; the exit code does not move |

That asymmetry is the whole feature. Exit 3 means *you were not told* — if a friend
blocking the bot could produce it, every cron run would be red forever and the one code
that is about **you** would stop meaning anything. Every recipient is still attempted
before anything is raised, so your outage does not cost them their message either.

**A permanent refusal disables that subscriber; a transient one does not.** Telegram
answers 403 (`bot was blocked by the user`) or 400 `chat not found` for a chat that will
still be gone next run, and the notifier writes `enabled: false` into `subscribers.json`
with the reason rather than warning about them every minute forever. A 429, a 5xx or a
dropped connection changes nothing and is retried. ⛔ The 400 branch is narrowed to
*chat not found* on purpose: `can't parse entities` is also a 400, and it fails for
**every** recipient at once — treating any 400 as permanent would let one ticket name the
formatter mishandled wipe the entire list in a single run.

**An absent file and a corrupt file are different things.** No file means nobody is
subscribed — valid, silent, and where every install starts. A file that will not parse
means we do not know *who* the recipients are, so it raises at startup, `build()` drops
the whole Telegram sink with a loud warning, and the run continues on the other channels.
The trade-off, stated: a corrupt list costs you your own Telegram for that run. Delete or
fix the file and it is owner-only again.

Each run prints the fan-out so `history/cron.log` carries it — a subscriber the notifier
auto-disabled at 3am shows up as the count dropping:

```
notifiers: console, telegram, toast
  telegram: you + 2 subscriber(s) — rafa, bruno
```

⛔ `subscribers.json` is **gitignored**: those are other people's chat ids. Same rule as
`.env`, and the same consequence — it exists only on this machine, and losing it means
asking everyone to message the bot again.

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

## Only changes are recorded

`append_if_changed` skips a run that is byte-identical to the last recorded one, so
`history/*.jsonl` is a **change log**: every line is a moment the market actually
moved. At a one-minute poll, recording every run would reach ~190 MB in twelve days
and force each later run to re-parse hundreds of thousands of lines to answer
`min_price_cents` — the watcher would get slower the longer it ran.

The trade-off, stated: the history no longer records *that a poll happened*. Use
`history/cron.log` for liveness. An empty result is never treated as "unchanged".

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

`subscribers.json` is gitignored for a different reason: it is not a secret, it is other
people's **personal data**. Chat ids identify individuals, this repo may be published,
and nobody on that list agreed to appear in a commit.

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

Seven dates, 04/09–13/09 — **all seven are shipped targets** as of 2026-09-01.
`data_millis` and `evento_local` come from the listing page at `/datas/rockinrio2026`:

| BRT date | `data_millis` | `evento_local` | poll | box office · 2026-09-01 |
|---|---|---|---|---|
| 04/09/2026 (sex) | 1788570000000 | 1765323377313x720803947984191500 | 1 min | on sale |
| 05/09/2026 (sáb) | 1788656400000 | 1765323572984x293448430956314600 | 1 min | on sale |
| 06/09/2026 (dom) | 1788742800000 | 1765323621728x687317125269815300 | 5 min | sold out |
| 07/09/2026 (seg) | 1788829200000 | 1765323705621x670780912989372400 | 5 min | sold out |
| 11/09/2026 (sex) | 1789174800000 | 1765323734393x441784445622288400 | 1 min | on sale |
| 12/09/2026 (sáb) | 1789261200000 | 1765323797528x513509114247905300 | 5 min | sold out |
| 13/09/2026 (dom) | 1789347600000 | 1765323829346x381107157350744060 | 5 min | on sale |

The box-office column is **dated on purpose** — it was true when observed and nothing
re-checks it. It is deliberately *not* in the target labels, which is what an alert
shows you: a label saying "sold out" would keep saying it long after that stopped
being true.

**Face value, Gramado** (Juan, 2026-09-01): **Inteira R$ 870,00 · Meia R$ 435,00.**
Because the gate does not check ticket class, R$ 435,00 is the working benchmark for
the cheapest *usable* ticket — anything above it is resale premium. It is recorded in
each new target's `_note_face_value` and **no rule reads it.** `below_threshold` ships
configured at R$ 435,00 but **disabled**: arming a ceiling on a night already trading
below it produces a rule that is dormant on arrival — the exact trap re-baselined away
in v1.1. Arm it only on a night currently *above* face.

⚠️ **"Sold out" at the box office does not mean sold out here.** On 2026-09-01, 06/09,
07/09 and 12/09 had no official inventory left — and were among the *fullest* pages on
this site that day, 207–253 Gramado *Inteira* listings each, priced 60–140% above the
nights still officially on sale. buyticketbrasil is the **secondary** market: an
official sell-out is what creates its supply, not what removes it. So a sold-out date
still baselines and still fires `lowest_ever` normally. Expect `[]` from a date that
has genuinely finished — not from one that is merely sold out.

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
