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

## Next — in priority order

- [ ] 🔴 **Get the Telegram chat id and prove real delivery.** Message
      @price_watcher_hub_bot, run `tools/telegram_chat_id.py`, put the id in `.env`,
      then `python3 watch.py --test-notify`. Until that message actually arrives,
      Telegram is unproven — offline tests only prove the payload, never the delivery.
- [ ] 🔴 **Decide the cadence and enable cron.** Still nothing scheduled; history holds
      3 runs, all from the build session. This is the last thing between the tool and
      being useful, and day one is 04/09.
- [ ] **Re-check the ceilings as history accumulates.** They are set just under the
      2026-09-01 floors and will go dormant again the moment the price drops under them.
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
