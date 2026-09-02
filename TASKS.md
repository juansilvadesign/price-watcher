# price-watcher — Tasks

**State: v1.9, 2026-09-02.** 228 tests green offline. Alerts are written **per
recipient language** (`en-US` / `pt-BR`); yours, console and toast stay English.
⏳ The pt-BR path is offline-proven only — `--test <chat_id>` against a real friend
is the outstanding leg. **All seven Rock in Rio nights**
are live targets, read end to end; alerts fired and verified edge-triggered. Console,
Windows toast and Telegram delivery are all **confirmed with a real message**. Cron
runs two cadences: one minute for the three nights he would buy, five for the four
he is only tracking.

## Done — v1 (2026-09-01)

- [x] Harness: registry · filters · rules · history · notifier interface · CLI
- [x] Adapter #1 `buyticketbrasil`, built from a first-hand recon pass
- [x] Three targets: Rock in Rio 2026 on 04/09, 05/09, 11/09 — Gramado, all classes
- [x] Three alert rules: `lowest_ever`, `below_threshold`, `drop_pct` — all edge-triggered
- [x] 45 tests, no network, against a real captured fixture
- [x] Guards, each with a known-bad leg in the suite:
      missing payload raises · empty matrix is data · zero-price rows dropped ·
      enabled-rule-without-parameter refuses to load · unknown filter field raises
- [x] Live verification: 3 consecutive runs, history accumulating, no alert re-spam

## Done — v1.1 (2026-09-01)

- [x] **Ceilings re-baselined.** 04/09 R$ 275,00 → **R$ 230,00**, 11/09 → **R$ 225,00**.
      Both had gone **dormant**: `below_threshold` is edge-triggered, so a ceiling
      sitting above the current floor can never fire again. All three now ARMED.
- [x] **Telegram sink** — token verified (`@price_watcher_hub_bot`), HTML output with
      every third-party value escaped, fails at construction if the chat id is missing.
- [x] **Windows toast sink** — native WinRT via `powershell.exe -EncodedCommand`, **no
      module installed**. Escapes `'` as `&apos;` because the XML rides inside a
      single-quoted PowerShell string and one apostrophe in a ticket name would break it.
- [x] **Sink fan-out** — every sink attempted even after one fails; `NotifyError` then
      exits **3**, distinct from an adapter failure.
- [x] **`--test-notify`** — prove delivery without waiting for a real price drop.
- [x] **`.env` gitignored** + `.env.example`; parsed in Python, ⛔ never sourced.
- [x] `tools/telegram_chat_id.py` — names the failure (bad token / webhook set / you
      have not messaged the bot) instead of printing an empty list.

## Done — v1.2 (2026-09-01)

- [x] **Telegram delivery PROVEN** — `ok=true`, `message_id=3`, delivered to chat
      `1689939411` (`jaypy06`), matching `.env`. Not a probe: a real send.
- [x] **Windows toast confirmed visually** on the desktop.
- [x] **`price_changed` rule** — fires on ANY move since the previous run, with
      `direction` (any/down/up) and `min_delta_brl`. Enabled on all three targets at
      `any` / R$ 0,01. Already fired in production on a R$ 1,10 move.
- [x] 🔴 **Cron installed** — `*/30`, verified by executing the exact cron command
      under a stripped environment, and by a one-minute probe proving the daemon fires.
- [x] **The cron trap that would have killed every run:** cron's PATH hides
      `powershell.exe`, so building the `toast` sink raised and aborted the run at
      startup — losing prices and Telegram too. Fixed three ways: `PATH` in the
      crontab, absolute-path fallbacks, and `build()` now degrades to surviving sinks
      instead of aborting (fatal only when *every* sink dies).
- [x] **History un-versioned** (Juan's call) — gitignored, `.gitkeep` retained.

## Changed — v1.3 (2026-09-01)

- [x] 🔴 **Rule scope narrowed to `lowest_ever` alone** (Juan): notify when the price
      drops below the lowest ever seen, and nothing else. `below_threshold`,
      `drop_pct` and `price_changed` are configured but **disabled**. Successive
      records each fire — 230 → 228 → 220 alerts twice. A non-record drop is silent.
- [x] 🔴 **Cron tightened to every minute** so a dip at 17:01 is seen at 17:01.
- [x] **Change-only recording** (`append_if_changed`) — without it, one-minute polling
      would reach ~190 MB by 13/09 and re-parse ~414,000 lines per run.
- [x] Juan's requirement encoded verbatim as a test (`TestSuccessiveNewLows`).

## Done — v1.4 (2026-09-01)

- [x] **The remaining four nights are shipped** — 06/09, 07/09, 12/09, 13/09. Same
      shape as the other three: Gramado, entry class unfiltered, `lowest_ever` alone
      armed. Registry now loads **7 targets**.
- [x] 🔴 **"Sold out" was checked, not assumed — and it was the opposite of empty.**
      06/09, 07/09 and 12/09 have no box-office inventory, and were among the *fullest*
      pages on buyticketbrasil that day: 207–253 Gramado *Inteira* each, priced 60–140%
      above the nights still officially on sale. This site is the **secondary** market,
      so an official sell-out *creates* its supply. Consequence: no restock rule was
      needed, and `lowest_ever` baselines and fires on them normally. Had it been taken
      at face value, the obvious move would have been a `[]`→non-`[]` restock rule that
      could never fire, on three targets that were never empty.
- [x] **Face value recorded** — Gramado *Inteira* R$ 870,00 / *Meia* R$ 435,00. Lives in
      each new target's `_note_face_value` and in the README. ⛔ **No rule reads it.**
      `below_threshold` ships at R$ 435,00 but **disabled**, because arming a ceiling on
      a night already under face is dormant on arrival — the v1.1 trap.
- [x] **Status is dated, not baked into labels.** The box-office column carries
      `2026-09-01`; the target labels do not say "sold out", because a label is what an
      alert shows you and that claim goes stale silently.
- [x] 🔴 **Split cron cadence** — `* * * * *` for 04/09, 05/09, 11/09; `*/5 * * * *` for
      06/09, 07/09, 12/09, 13/09, both via `--only`. Seven nights on the one-minute line
      would have been **~10,080 requests/day** to one site; the split is **~5,472/day**
      with no lost resolution on the nights a purchase would actually happen.
      Both lines verified under a stripped `env -i` before installing.
- [x] **Two pinned tests extended 3 → 7** — the shipped-target count and the verbatim
      per-night URL map. Both *failed first* on the new files, which is what they are for.
- [x] **A test class that never ran** — `TestShippedTargetUrls` sat below
      `if __name__ == "__main__"` in `test_buyticketbrasil.py`, so a direct
      `python3 tests/test_buyticketbrasil.py` collected 10 tests and silently skipped it.
      Guard moved to the end; the direct run now collects 12.

## Done — v1.5 (2026-09-01)

- [x] 🔴 **The empty-read `FilterError` is decided and fixed** (Juan, by interview).
      `filters.py` short-circuits on an empty `readings` list: there is nothing to
      typo-check a filter against, and `any(field in r.extra for r in [])` is
      **vacuously False**, so both guards used to fire on a legitimately empty read and
      collapse "sold out" into "broken config" — the pair the first invariant forbids.
      ⛔ The guards keep their teeth: a typo on a **non-empty** read still raises, which
      is the only case where a typo is distinguishable from an empty market.
- [x] 🔴 **The blast radius was a second, independent defect — also fixed.** `watch.py`
      caught `FilterError` **outside** the per-target loop, so *any* config error, typo
      included, aborted every target after it. It is now caught per target and symmetric
      with the `AdapterError` branch above it: report, mark the target `config`, keep
      going. The run still exits **2** — config outranks adapter (1) and delivery (3),
      preserving the old precedence, since a `FilterError` previously discarded any
      earlier delivery failure by returning immediately.
- [x] **Both fixes have a known-bad leg that FAILED FIRST on the pre-fix code**, checked
      by reverting the two source files and re-running:
      `[]` under the shipped filters raised · `[]` end-to-end through `main()` exited
      **2** instead of 0 · a typo'd target left the next one unpolled
      (`'z-good' not found in '… === label a-bad [a-bad]'` — the blast radius, printed).
      Their control legs passed on both sides: a typo on a non-empty read still raises,
      and a clean two-target run still exits 0.
- [x] **New `tests/test_watch.py`** drives `main()` against a stub adapter registered in
      `adapters.ADAPTERS` — no network, no fixture. 93 → **101 tests**.
- [x] **Live re-verification** — all 7 nights read clean under `--dry-run --notifier
      console`, exit 0, and a real `lowest_ever` fired on 13/09 (R$ 324,50 → R$ 308,00),
      so the alert path still works. Console-only deliberately, to avoid double-alerting
      alongside cron; dry-run writes nothing, so cron still delivers that low itself.

## Done — v1.6 (2026-09-01)

- [x] 🔴 **`lowest_ever` ratchets shut — and the buy day is when its bar is highest.**
      Every record it sets raises its own bar, so the rule gets *quieter the longer it
      runs*, which is exactly inverted from the need: Juan buys on the day. Measured on
      2026-09-01, the three buy nights needed **−9,1 % (04/09)**, **−26,7 % (05/09)** and
      *any* dip **(11/09)** before `lowest_ever` would say a word.
- [x] **New rule `lowest_in_window`** — beats everything standing in the last N hours.
      Its baseline expires, so it cannot ratchet. Armed at **`window_hours: 6`** on the
      three buy nights (04, 05, 11/09); configured-but-disabled on the four tracking
      nights, where an extra alert is one he cannot act on.
- [x] ⭐ **The change log made this harder than it looks, and the fix does two jobs.**
      `append_if_changed` means a window can hold **zero rows** while the price was
      perfectly well defined — it just never moved. A naive `min` over rows inside the
      window reads that as "no data" when it means "no change". So
      `History.min_price_cents_since` **carries the last run before the cutoff forward**.
      That same carry-forward is what keeps the rule **edge-triggered**: without it a
      price returning to a level it already held inside the window reads as a fresh low,
      and an oscillating market re-alerts on every swing back.
- [x] **Known-bad rerun against a naive window query** — swapped in the no-carry-forward
      version and got exactly the 3 predicted failures, with the false alert printed
      verbatim: `6h LOW — R$ 250,00 … beating R$ 300,00` on a price the market had
      already held. Controls passed both ways.
- [x] **Permit *and* refuse legs against the real history files**, not just fixtures:
      one centavo under the live 6h baseline fires on all three buy nights; exactly at
      the baseline is silent.
- [x] **Registry guards** — `lowest_in_window` enabled without `window_hours` refuses to
      load, as do `0`, negative, string and **boolean** windows (`isinstance(True, int)`
      is True in Python, so a bare `true` would otherwise load as a plausible 1-hour
      window nobody wrote). Plus a control leg proving a valid window still loads.
- [x] **The shipped-target pin now encodes intent per night** instead of "only
      `lowest_ever`", and asserts the buy-night set is actually present — otherwise a
      renamed id would make that branch vacuous and the pin would guard nothing.
      Verified by mis-arming 06/09: it fails and names the target.
- [x] **`if __name__` guard moved to the end of `test_rules.py`** — two classes sat
      below it. Latent rather than live (⚠️ `discover` imports the module, so they were
      collected; a direct run of this file fails at import anyway), but it is the same
      defect v1.4 fixed in `test_buyticketbrasil.py`.
- [x] 101 → **114 tests**, still fully offline.

## Done — v1.7 (2026-09-02)

- [x] ✅ **`lowest_in_window` CONFIRMED firing in production — 7 times, not a probe.**
      `grep -a '6h LOW' history/cron.log` returns 7 real cron fires between
      `2026-09-02T01:42Z` and `13:46Z` (09-04 ×4, 09-05 ×2, 09-11 ×1). Verified
      independently rather than taken from the log: replaying the real rule over the
      production JSONL predicts **10** fires across the full 19.7h of history, and the
      3 extras all fall **before the rule was armed** (targets written
      `2026-09-01 22:17:35 -03` = `01:17:35Z`). Eligible after arming = 7. Actual = 7,
      matching on both price and baseline in every row. ⛔ The open item said "a probe
      is not a production fire" — this is the production fire.
- [x] ✅ **Delivery verified too.** All 5 `DELIVERY FAILED` lines name `toast:` only
      (WSL `accept4` vsock errors). `MultiNotifier` attempts every sink before raising,
      so Telegram was never blocked and never failed.
- [x] 🔴 **Found: a one-run R$ 66,00 had already killed 04/09.** `Gramado || Inteira`
      at R$ 66,00 appeared for **exactly one run** (`13:46:04Z`), on the same qty-235
      listing that was R$ 220,00 the minute before and R$ 275,00 the minute after. It
      took the `lowest_ever` record — which has **no expiry** — so on the primary buy
      night, two days out, *both* armed rules required a price under R$ 66,00 to speak.
      A genuine drop to R$ 180,00 would have produced nothing. Both rules looked healthy.
- [x] ✅ **New rule `critical_price` — the anomaly floor.** Two jobs from one number:
      alert immediately on any price below it (bypassing the window), and never let
      such a price become a baseline for `lowest_ever` / `lowest_in_window`.
      Cadence by Juan's call: **on entering the band, then on each new low inside it**,
      silent while a sub-floor price merely holds. Armed on **all seven** nights —
      it is a data-quality guard as much as an alert, and a tracking night runs
      `lowest_ever` too. Per-target X, just under each night's observed floor:
      R$ 200,00 on 04/05/11 · R$ 250,00 on 13 · R$ 350,00 on 07/12 · R$ 450,00 on 06.
- [x] ⭐ **The exclusion is applied on READ, not on write** — so it **heals
      retroactively**. 04/09's baselines went straight back to R$ 220,00 from R$ 66,00
      the moment the floor was armed; the other six targets did not move, which is the
      control that the floors are not eating legitimate data. Dropping anomalies at
      ingest would have left every already-poisoned history poisoned for good, and
      `lowest_ever` has no expiry, so "for good" is literal. The JSONL keeps the bad
      row for audit.
- [x] 🔴 **Fixed alongside it: the status line contradicted its own rule.**
      `watch.py` computed "record low so far" with an unfloored `min_price_cents`, so
      04/09 printed `R$ 66,00` while the rules were working off `R$ 220,00`. That is
      the number a human reads at 2am to decide whether the silence is trustworthy.
      Pinned by a test plus a known-bad leg with the floor disarmed.
- [x] ✅ **114 → 141 tests**, all offline. The new guards are mutation-proven: three
      separate reverts (`_anomaly_floor` → `None`, `_cheapest_legit` ignoring the floor,
      `critical_price` losing its in-band cadence guard) each fail the intended legs
      first — 6, 4 and 2 failures respectively — and the source restored byte-identical.
- [x] ⭐ **Replayed over ~1,100 recorded runs across all 7 targets, `critical_price`
      fires exactly once** — on the real R$ 66,00. Zero false positives at these floors.
- [x] ⚠️ **A bare `true` in `price_brl` is now rejected at load.** `isinstance(True, int)`
      is True, so it would have converted to R$ 1,00 — a floor that reads as armed and
      matches nothing. Caught before conversion; afterwards it is an ordinary `100` and
      no later validator can see it. Same trap `_validate_window_hours` already guards.

## Done — v1.8 (2026-09-02) — sharing the bot with friends

Juan's ask: the bot is public but only ever messaged him; he wants the friends **he
selects** to receive the same alerts. Shape decided by interview (2026-09-02): friends
message the bot, **he approves**; everyone gets everything; a friend's failure is
best-effort; the list lives in a gitignored `subscribers.json`.

- [x] **`pricewatch/subscribers.py`** — the recipient list, validated the way
      `registry.py` validates targets: refuses rather than defaults. Missing `chat_id`,
      a bare `true` as a chat id, a quoted `"false"` for `enabled`, a duplicate id, or a
      wrong root shape each refuse to load.
- [x] ⭐ **An absent file and a corrupt file are different states.** Absent = nobody
      subscribed, valid and silent, byte-identical to the old owner-only behaviour.
      Unparseable = we do not know *who* the recipients are → raises. Same pair as
      `AdapterError` vs `[]`; collapsing them would make a typo'd file look like "no
      friends subscribed" forever, because not receiving alerts is exactly what that
      looks like from outside.
- [x] **Two-tier fan-out in `TelegramNotifier`.** Owner first (critical → `NotifyError`
      → exit **3**), then every enabled subscriber (best-effort → warning, exit code
      untouched). **Every recipient is attempted before anything raises** — the
      `MultiNotifier` rule one layer down, so a dead owner chat does not cost the
      friends their message and vice versa.
- [x] 🔴 **Auto-disable on a permanent refusal only.** A 403 (`bot was blocked by the
      user`) or a 400 `chat not found` writes `enabled: false` + the reason into the
      file, so a friend who blocks the bot stops costing a warning every minute.
      ⛔ **The 400 branch is narrowed to "chat not found" deliberately:**
      `can't parse entities` is also a 400 and fails for **every** recipient at once —
      treating any 400 as permanent would wipe the entire list in one run from a single
      ticket name the formatter mishandled. Pinned by a test that says so by name.
- [x] **`set_enabled` re-reads before writing.** Two crontab lines fire in the same
      minute, so two runs hold the file at once; writing back a startup snapshot would
      revert the other run's disable. Not atomic against a true race — the window is
      narrowed to read→`os.replace`, and untouched entries survive.
- [x] **`pricewatch/telegram_api.py`** — one place that decodes Telegram's error
      envelope. The refusal that matters lives in the **body of the 4xx**, which
      `urllib` raises past; without decoding it, "this person blocked the bot" and "the
      network hiccuped" are the same event. `tools/telegram_chat_id.py` now shares it.
- [x] **`tools/telegram_subscribers.py`** — `--pending` (who messaged the bot and is not
      on the list) · `--add/--remove/--enable/--disable` · `--test <id>` (one synthetic
      alert to one chat, because `watch.py --test-notify` fans out to everybody) ·
      default `--list`. Refuses to add your own `TELEGRAM_CHAT_ID`, and names the
      getUpdates traps (webhook set, recent-only queue) instead of printing an empty list.
- [x] **A comma-separated `TELEGRAM_CHAT_ID` is refused at startup**, pointing at the
      subscriber tool. Left alone it is sent verbatim as one chat id and Telegram answers
      400 `chat not found` every run: a setup that looks configured and reaches nobody.
- [x] **Every run prints the fan-out** (`telegram: you + 2 subscriber(s) — rafa, bruno`)
      so `cron.log` carries it; a subscriber auto-disabled at 3am shows as the count
      dropping. The `notifiers:` header now reports the sinks that **survived** `build()`
      rather than the ones requested — a corrupt list drops the sink, and a header still
      claiming it would contradict the run underneath it.
- [x] ⛔ **`subscribers.json` gitignored** (verified by exit code, not by output). Not a
      secret — other people's personal data, in a repo that may be published.
- [x] **114 → 187 tests**, all offline. **Mutation-proven, 4 reverts:** any-400-is-
      permanent (2 legs fail, incl. *"a formatting bug disabled real subscribers"*) ·
      a friend's failure re-raises (2) · corrupt file reads as `[]` (4) · `set_enabled`
      writes a stale snapshot (1). Sources restored byte-identical, sha256 verified.
- [x] **Fixed an ambient-state trap in the existing suite**: `TestTelegram` built a
      notifier with the default store, so those assertions would have started reading
      the real `subscribers.json` and failing the day a friend was added — the same
      shape as the `.env` trap already noted in `test_missing_chat_id_fails_at_construction`.
- [x] ✅✅ **PROVEN LIVE 2026-09-02** — Juan added his own **second Telegram account** as
      the first subscriber and the fan-out delivered. Not a probe: a real second chat on
      the real notifier path.
- [ ] ⚠️ **The failure half is still unobserved.** No subscriber has ever been
      auto-disabled in production, so the 403 → `enabled: false` write is proven by test
      and by mutation, never by a live block. Expected, not observed.
- [ ] 🟡 **Commit the 7 dirty doc/config files.** The code landed as `ec584ac`; the docs
      did not. ⛔ **`.gitignore` is the urgent one** — it carries the `subscribers.json`
      rule, and a real subscriber file now exists on disk.

## Done — v1.9 (2026-09-02) — per-recipient language

- [x] **`en-US` + `pt-BR`, chosen per friend when you approve them.**
      `--add <id> --name <who> --lang pt-BR`, `--set-lang <id> --lang <l>` to change it,
      and a `lang` column in `--list`. It is a plain field in `subscribers.json`, so
      editing by hand works. ⛔ Yours is **not** in that file — you are not a subscriber,
      and console + toast are yours alone and stay English.
- [x] 🔴 **A rule can no longer write a sentence.** One firing now reaches recipients who
      read different languages, so the wording cannot be chosen when the rule fires.
      Rules emit a **message key + params**; `pricewatch/messages.py` renders it once per
      language inside the sink. `Alert.headline`/`.detail` survive as the **en-US
      rendering of that same catalog** — so console, toast and every existing test read
      unchanged, and English is still written down in exactly one place. Two sets of
      f-strings would have drifted the first time a rule's wording changed, and only the
      person reading the *other* language would ever have seen it.
- [x] **Two keys where a branch changes a word**, not one sentence with a swapped clause:
      `price_changed.up`/`.down` and `critical_price.entering`/`.new_low`. "is a new low
      below" sits mid-sentence in English and cannot be assumed to survive that position.
- [x] 🔴 **The catalog is validated at IMPORT**, and all three checks guard a defect that
      is silent in production. `_subscriber_failed` catches every exception from a send,
      and a `KeyError` carries no `error_code`, so it is classified transient and warned
      about forever without disabling anyone or moving the exit code:
      ① a key missing from a language → that friend receives nothing, every run;
      ② a placeholder typo (`{prise}`) → same silent warning;
      ③ a **dropped** placeholder → the sentence still reads fine, it just stops saying
      what the previous record was;
      ④ a placeholder no formatter covers → raises *nothing anywhere* and renders raw
      centavos (`25000` for `R$ 250,00`).
      The catalog is source code, so a failure fails in the first test run and cannot
      ship. `test_the_shipped_catalog_passes_its_own_validator` is the control leg.
- [x] 🔴 **An unknown `lang` is refused; an absent one defaults to en-US.** Absent means
      nobody chose. `"pt_br"` raises — because a fallback here is invisible to *everyone
      who could report it*: the entry looks configured, your own copy of every alert is
      English regardless, and the friend receives working English forever without knowing
      it was meant to be Portuguese. Cost stated and accepted: a typo drops the Telegram
      sink for the run (`build()` degrades, other sinks survive) until fixed.
- [x] **Rendering is LAZY, per recipient, inside the try that already owns them.** A
      broken template in one language costs exactly the people who read it — the
      `MultiNotifier` rule two layers down. A broken *owner* language still raises and
      still delivers to the friends. Pinned by mutation: rendering all languages eagerly
      up front breaks 3 tests.
- [x] **`--test <chat_id>` sends in the language that chat is already approved with**
      (via `owner_lang`), not `DEFAULT_LANG`. It is the *only* chance to catch a wrong
      language: every alert you personally receive afterwards is English regardless.
- [x] **The fan-out header carries it** — `telegram: you + 2 subscriber(s) — rafa
      [pt-BR], alex [en-US]` — so `cron.log` records the half you cannot verify from
      your own phone.
- [x] **`set_enabled` preserves `lang`.** It rebuilds the entry field by field, so every
      field it forgets is silently lost: a friend auto-disabled at 3am and re-enabled
      later would have come back reading English. Pinned by mutation.
- [x] **228 tests green offline** (187 → 228). New: `tests/test_messages.py` (17) plus
      language and render-failure coverage in `test_notify.py` / `test_subscribers.py`.
- [x] **4 mutations, each caught by the right test and only it:** `set_enabled` drops
      `lang` → 1 failure · eager rendering → 3 · `format()` ignores its `lang` → 5 ·
      subscribers rendered at `owner_lang` → 4. Source restored and diffed clean after.
- [x] **Verified end to end offline** through the real `lowest_ever` + `lowest_in_window`
      rules on the real `rockinrio2026-09-04` target: owner got `NEW LOWEST — R$ 250,00`,
      the pt-BR friends got `NOVA MÍNIMA — R$ 250,00`, identical money, identical label,
      third-party ticket name escaped in both.
- [ ] ⏳ **Not yet proven against live Telegram.** `--test <chat_id>` against a real
      pt-BR friend is the outstanding leg; every check above is offline.

## Next — in priority order
- [x] ✅ **Alert volume: MEASURED, not guessed — and it is not the problem.** Over the
      first **329 cron runs** the armed rules fired **6 times (1,8 %)**. The *floor*
      idea (a new low only if ≥ N% below the last record) would have been tuning down a
      signal that was never noisy — dropped rather than built. The real defect was the
      opposite one: too *few* alerts on the day that matters, which is what
      `lowest_in_window` addresses. ⚠️ Re-measure once the window rule has run a full
      day; 6h of history is not yet a rate for it.
- [ ] ⛔ **n8n fallback scheduler — considered and declined 2026-09-01 (Juan).** cron
      already runs under systemd here; n8n would add a Docker dependency, its own
      gotcha corpus, and could not drive the Windows toast sink. Revisit only if cron
      proves unreliable.
- [x] ✅ **`lowest_in_window` has outgrown the window — no longer degenerate.**
      On 2026-09-01, with ~7h of log against a 6h window, the two baselines were
      identical on all **7** targets: the instrument reading its own youth, not a
      finding ([[feedback_identical_values_across_items_measure_the_instrument]]).
      Re-measured 2026-09-02 with ~20h of log, they now **diverge on 5 of 7**
      (09-05 242,00 vs 245,30 · 09-07 368,50 vs 385,00 · 09-11 214,50 vs 242,00 ·
      09-12 478,50 vs 489,50 · 09-13 275,00 vs 324,50). The rule is genuinely
      selective, and the 7 production fires are the behavioural confirmation.
- [ ] ⚠️ **Re-measure alert volume now that a second rule is armed everywhere.**
      `critical_price` replayed over ~1,100 runs fires once, so it adds ~nothing at
      these floors — but that is a backward-looking number on 20h of history, and the
      buy nights are the volatile ones. Check the rate again after 04/09.
- [ ] 🔴 **A new target file is no longer enough.** Since the cadence split, both cron
      lines name their targets with `--only`, so a target in `targets/` that is in
      neither list is never polled — while `--list` still shows it `[on ]`. Add the id
      to a crontab line at the same time you add the file.

## Known-unknown — do not assume

- [ ] **Only 04/09's payload was read end-to-end during the recon.** 05/09 and 11/09
      parse correctly and return sane data, so the shape holds, but no other *site*
      has been touched. The adapter contract is unproven against a second site — the
      hub claim is a design, not yet a demonstrated fact.
- [ ] `preco_destaque` (`{tipo, entrada, valor}`, R$ 10.000,00 on 04/09) is
      unexplained — presumably a strike-through anchor. **Do not build a "% off"
      rule on it** until someone confirms what it means.
- [ ] Behaviour when an event sells out entirely, or when a date passes, is **still**
      untested against the live site. Expected: `matriz_preco` empty → `[]` → "nothing
      on sale", no alert, no crash. Expected, not observed — and note that the three
      box-office sell-outs did **not** produce it, so they are not the test case.
- [x] ✅✅ **RESOLVED v1.5, and OBSERVED LIVE v1.7 — twice, on both sides of the fix.**
      The fix was two defects, not one: the vacuous `any()` in `filters.py` made `[]`
      fatal, and `watch.py`'s catch sat outside the loop so *any* `FilterError` was
      contagious. Both are pinned by tests that failed first on the old code.
      ⛔ **The old note here — "no live target has ever actually returned `[]`" — is
      wrong and has been corrected.** It happened twice:
      ① **Pre-fix**, at `history/cron.log:1078`: `rockinrio2026-09-11` returned 0
      readings and aborted the run. Provably pre-fix from its format — the current code
      prints `  CONFIG ERROR:` (indented, from `run_target`), while that line reads
      `config error:` and carries a `FilterError` message that `load_targets` never
      raises. That combination is unreachable in the code as it stands.
      ② **Post-fix**, 2026-09-02 ~14:10Z, same target: `0 listings seen` →
      *"nothing on sale matching this target's filters"*, exit **0**, no crash.
      ⚠️ It was **transient** — 10/10 immediate re-probes returned 21 rows, and the raw
      payload during the outage had `matriz_preco` present with data, so the site
      briefly served an empty matriz. Under the invariant that reads as "sold out", and
      the cost is one skipped run per occurrence at a one-minute poll. ⛔ Do not treat
      a single `[]` here as a sold-out signal without a re-probe.
