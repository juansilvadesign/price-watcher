# price-watcher — Tasks

**State: v1.1, 2026-09-01.** 69 tests green offline. Three live targets read end to
end; alerts fired and verified edge-triggered across three runs. Console + Windows
toast delivery **confirmed visually on the desktop**; Telegram is wired and tested
offline but has **never delivered a real message** — it is blocked on a chat id.

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

## Next — in priority order
- [ ] **Confirm the alert volume feels right.** Only `lowest_ever` is armed and the
      poll is every minute, so volume tracks how often a record breaks, not the poll
      rate. If it is still too much, the honest lever is a *floor* — there is no rule
      today for "a new low, but only if it is at least N% below the last record".
- [ ] ⛔ **n8n fallback scheduler — considered and declined 2026-09-01 (Juan).** cron
      already runs under systemd here; n8n would add a Docker dependency, its own
      gotcha corpus, and could not drive the Windows toast sink. Revisit only if cron
      proves unreliable.
- [ ] **The other 4 Rock in Rio dates** — ids are in the README table, one JSON file
      each. Only if you would actually consider those nights.

## Known-unknown — do not assume

- [ ] **Only 04/09's payload was read end-to-end during the recon.** 05/09 and 11/09
      parse correctly and return sane data, so the shape holds, but no other *site*
      has been touched. The adapter contract is unproven against a second site — the
      hub claim is a design, not yet a demonstrated fact.
- [ ] `preco_destaque` (`{tipo, entrada, valor}`, R$ 10.000,00 on 04/09) is
      unexplained — presumably a strike-through anchor. **Do not build a "% off"
      rule on it** until someone confirms what it means.
- [ ] Behaviour when an event sells out entirely, or when a date passes, is
      untested against the live site. Expected: `matriz_preco` empty → `[]` → "nothing
      on sale", no alert, no crash. Expected, not observed.
