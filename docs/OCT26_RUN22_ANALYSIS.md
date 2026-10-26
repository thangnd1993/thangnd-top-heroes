# October26 normal application run22 — analysis (build 34b174f)

## Evidence
- Run **22**, `normal-ui-start`, max_concurrency 2 (peak 2), targets **#2 Emmmm, #3 Queen con** (the user's selection).
  2026-10-26 07:58:30–08:14:55 UTC (14:58–15:14 Vietnam), result PARTIAL.
- Executable `C:\Users\ADMIN\Desktop\app\TopHeroesAutoManager\TopHeroesAutoManager.exe`, exe SHA-256 `3e3e6882…574e`,
  commit `34b174ff0bcabf211caef8ee87d93e8081c23cd4`, CI 40284456950 — the delivered build.
- Report `diagnostics\tasks\automation\20261026-075830-561182Z-eeda0c28\`; `app.log` 240 lines tagged `run=22`.
- Protected unchanged, names unchanged (0 write attempts), selections restored, no preserved-POSSIBLE exceptions.

## Results
| Index | Worker s | Startup/Home s | New VERIFIED | Not claimed (reason) |
|---|---:|---:|---:|---|
| 2 | 949.6 | 111.6 | 12 | idle (historical lock), guild-relic / mail-system (old RESERVED/POSSIBLE locks), guild gifts (journal proof review), events BLOCKED |
| 3 | 983.5 | 190.9 | 10 | idle (empty-proof lock), guild-gifts-loot / guild-technology / mail-system (old locks), Monthly daily UNKNOWN, events BLOCKED |

Every dispatched non-aggregate claim has a VERIFIED journal row. No claim was dispatched without a postcondition.

## Proven in real gameplay
- **Run21 capture retry works.** #3 at 15:00:13 VN: `screencap` failed during GAME_LOADING; the app logged
  "Screencap lỗi tạm thời … thử lại 1/2", re-verified the same target and continued to GAME_HOME and 10 VERIFIED claims.
  The same failure in run21 blocked #9 for the whole run.
- The 90 s ADB window was not exercised (both targets resolved in ~23 s).

## Runtime (same account #2, run21 build 8c89e9a → run22 build 34b174f)
| Metric | run21 | run22 |
|---|---:|---:|
| Worker wall | 1020.7 s | 949.6 s (−7 %) |
| `list2` inventory commands | 720 calls / 156.7 s | 468 / 98.2 s (−35 % calls, −58 s) |
| Identity/other ADB commands | 609 / 132.4 s | 552 / 122.2 s |
| Recovery recognition | 227 s / 107 | 233 s / 91 |
| Detection (fixed/guild/mail) | 242 s / 79 | 279 s / 68 |
| Events flow | 122 s | 67 s (shorter because traversal stopped early, not faster) |
Recognition (≈ 510 s of 950 s on #2) is now the dominant cost.

## Defects
### R22-1 — Event traversal ends at the first unrecognised event child page (both accounts) — FIXED (user chose option a)
- Evidence: #2 `events/20261026-081332-864630Z` = qualified seasonal gallery ("Trận Chiến Chạng Vạng", child cards with red dots);
  the explorer entered one child; `…081343-773212Z` = "Tháp Đuốc 2 / Chương II" chapter page with a glowing 3000 milestone chest
  and a "Thưởng" control. Page = UNKNOWN (no qualified shell). `recover_home` from UNKNOWN sent no input (by design) and returned
  UNKNOWN_SCREEN; `DynamicEventExplorer.continue_after_block` (`automation/dynamic_events.py:156-170`) then stops the whole traversal.
  Same sequence on #3 (`…081429-740489Z`). The other 3 Home event candidates (including Tầm Bảo) and the remaining gallery children
  were never visited.
- Root cause: an unsupported child page has no qualified exit, and "UNKNOWN = no input" leaves no way back to the parent, so one
  unsupported page costs every remaining independent event.
- Options: (a) a narrowly qualified **Back-only exit** for an UNKNOWN page entered from a qualified parent in the same visit (unique
  Back anchor in the standard position, no popup/dialog, different fingerprint; no claim permission; page recorded BLOCKED), or
  (b) per-page "known blocker exit" shells with new templates for each seasonal page. (a) relaxes the AGENTS.md rule "UNKNOWN means
  no gameplay input" for navigation Back only, so it requires the user's decision.

### R22-2 — #3 Monthly daily reported UNKNOWN on an un-owned Monthly card — FIXED
- Evidence: `3/shop/20261026-080641-376517Z` shows the Monthly card **not owned** (orange paid activation "329000 / 119000 VND −60 %"
  in place of `Nhận`). No reward was missed; the parent is BLOCKED instead of a positive "not owned" outcome.
- Root cause: `vision/monthly.py:daily_availability` only models owned/claimable and owned/received; an un-owned panel falls to UNKNOWN.

### Remaining locks (design, not defects)
Old RESERVED/POSSIBLE rows (guild relic, mail system, guild gifts, technology on #3, idle historical locks) were respected.

## Repairs (2026-10-26)
- **R22-1:** `app/dynamic_event_port.py:unqualified_child_exit` + one-shot `child_origin` set only by a dispatched child edge;
  `automation/dynamic_events.py` rejects the flag unless the pending edge is a child edge. Back only, no claims, page BLOCKED.
  Recorded as the sole UNKNOWN exception in `AGENTS.md`, `CLAUDE.md`, `docs/SAFETY.md`.
- **R22-2:** new anchor `assets/tasks/phase6/fixed-rewards/monthly-unowned-label` (validity label cropped from the run22 frame, normalized
  orientation) searched in the same Monthly daily region; `vision/monthly.py:daily_availability` returns NOT_AVAILABLE only with that label AND no
  claim, received or owned anchor and no green control. Owned/claimable and owned/received fixtures are unchanged.
- Tests: `tests/test_run22_repairs.py` (26), fixtures `tests/fixtures/run22/`. The guard test and the un-owned Monthly test fail on the pre-fix code;
  the port-level tests need the new function and do not import on the old code.
- Not proven in gameplay until the next user run.
