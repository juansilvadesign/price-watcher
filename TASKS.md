# price-watcher — Tasks

**State: v1 shipped and running, 2026-09-01.** 45 tests green offline, three live
targets read end to end, alerts fired and verified edge-triggered across three runs.

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

## Next — nothing is blocking, in rough priority order

- [ ] **Decide the cadence and enable cron.** Nothing is scheduled. The README has
      the line; the interval is a judgement call and prices were seen moving within
      minutes. This is the only thing standing between the tool and being useful.
- [ ] **Tune `price_brl` per target once history exists.** All three ship at 275.00,
      which was the 2026-09-01 Gramado floor. 04/09 was already at R$ 250,00 within
      the hour and 11/09 at R$ 242,00 — the ceilings are stale by construction.
- [ ] **Telegram notifier** if console+cron proves too passive. Interface is ready
      (`notify.SINKS`); needs a BotFather token. Deliberately not stubbed.
- [ ] **The other 4 Rock in Rio dates** — ids are in the README table, each is one
      JSON file. Only add them if you would actually consider those dates.

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
