# price-watcher — Tasks

**State: v1.4, 2026-09-01.** 93 tests green offline. **All seven Rock in Rio nights**
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

## Next — in priority order
- [ ] **Confirm the alert volume feels right, now at seven nights.** Only
      `lowest_ever` is armed, so volume tracks how often a record breaks, not the poll
      rate — but there are now 7 targets breaking records instead of 3. If it is too
      much, the honest lever is a *floor*: there is no rule today for "a new low, but
      only if it is at least N% below the last record".
- [ ] ⛔ **n8n fallback scheduler — considered and declined 2026-09-01 (Juan).** cron
      already runs under systemd here; n8n would add a Docker dependency, its own
      gotcha corpus, and could not drive the Windows toast sink. Revisit only if cron
      proves unreliable.
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
- [ ] 🔴 **A genuinely empty read CRASHES the run — reproduced, not theorised.**
      `filters.py` guards against a typo'd field with `any(field in r.extra for r in
      readings)`, which is **vacuously False on `[]`**. So a date with no listings
      raises `FilterError`, and `watch.py` catches it **outside** the per-target loop —
      one empty night aborts **every target after it** in that run and exits **2
      (config error)**. It has already happened once in production (`cron.log`).
      This collapses "sold out" into "broken config", the exact pair the project's
      first invariant forbids. Verified 2026-09-01 with a control leg: `[]` raises,
      one real reading passes.
      **Fix (one line, deliberately NOT applied — Juan's call):** skip the typo check
      when `readings` is empty; there is nothing to typo-check against. Then `[]`
      flows to `watch.py`'s existing "nothing on sale" branch, which already handles
      it. Wants its own known-bad leg in the suite: `[]` → clean, unknown field on a
      non-empty read → still raises.
      ⚠️ Now more likely to bite: the three box-office sell-outs are the nights
      closest to going genuinely empty, and 06/09 sorts FIRST on the `*/5` line — so
      it would take 07/09, 12/09 and 13/09 down with it.
