# October26 normal application run25 — analysis (build 94bc2f7)

## Evidence
- Run **25**, 2026-10-26 13:44:23–13:58:04 UTC (**20:44–20:58 Vietnam**), concurrency 2 (peak 2), #2 Emmmm and #3 Queen con, PARTIAL.
- Exe SHA-256 `b0c58b8c…87ec4d`, commit `94bc2f7a3b49b4f769bc1944f45f57b73be0c167`, CI 40325619349 — the delivered build.
- Still the **same game day** as runs 22–24 (daily reset 02:00 UTC = 09:00 Vietnam): daily rewards were already VERIFIED and correctly not repeated.

## Why the report said PARTIAL
1. `protected_state_unchanged: false` — Protected **#6 Chicken** was running before and stopped after the run (`cause: UNPROVEN`).
   `app.log` run=25 shows lifecycle commands only for #2 and #3 (launch 20:44:24, stop 20:57:55/20:58:03); no command addressed #6.
   The stop was external (user/LDPlayer). The old report could not prove that and counted it as a Protected breach. **Fixed** (below).
2. Old journal locks (by design, never replayed): idle (historical/empty-proof locks), guild-relic RESERVED, guild gifts journals 575/577
   "JOURNAL_PROOF_REVIEW_REQUIRED", mail-system RESERVED, #3 technology/gifts RESERVED. These keep every run PARTIAL until reconciled.
3. Events: every root was visited (paid-pack fix proven: #3 visited 5/5, run24 4/5), but most Event content pages are not qualified → BLOCKED.

## Proven in real gameplay (run25)
- R24-1 paid-pack close: all 5 Event roots visited on both accounts.
- OCR server: #2 OCR 79 s/131 calls → **7 s**/85; #3 122 s/195 → **11 s**/108.
- Guild Technology again: #2 5→4 ordinary, 4→0 quick, VERIFIED (journals 1020, 1022).
- Wall time: #2 990 → **821 s** (−17 %), #3 930 → **813 s** (−13 %) versus run24.

## Fix in this round
`ldplayer/client.py` records every indexed LDPlayer command per index (`record_indexed_command`), the only per-instance command path.
`app/automation_fleet.py` reports `automation_commanded_indexes`; a Protected runtime change with zero commands from this process and no
run membership is `EXTERNAL_NO_AUTOMATION_COMMAND` and does not fail `protected_state_unchanged`; any command to it keeps `UNPROVEN`
and fails it. Test: `tests/test_run19_repairs.py::test_protected_runtime_delta_is_separate_from_flags_and_never_restored[False|True]`.
