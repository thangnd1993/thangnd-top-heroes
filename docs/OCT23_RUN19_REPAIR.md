# October 23 â€” Run 19 failure inventory (before production edits)

## Provenance and scope

Newest completed normal UI run: **19**, 2026-10-23 09:12:57â€“10:45:08 UTC (16:12â€“17:45 Vietnam). Run 18 was cancelled; run 17 is comparison only. Desktop build `59885498039f5d9509a8760a14cb9a951e141f3e`, CI `39920326037`, EXE SHA256 `0e75967d4a071977f9c38542ff2826dcaef238e050021b316e5e2352907b12e5`. Two independent account workers; run FAILED, fleet report PARTIAL. No new gameplay session is authorized for this repair.

Evidence root: `C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\tasks\automation\20261023-091257-960784Z-3dffc04e`. Correlated `logs/app.log` lines include `run=19`, index and worker. Reports and original screenshots remain outside Git; no journal edits.

## All enabled flows / all accounts

Results below are actual report outcomes, not inferred eligibility. Monthly aggregate is navigation plus independent child rewards; journal NONE on that aggregate is expected.

### Index 2 / automation-account_0 / 1444.304 seconds

| Reward/flow | Result | Journal | Claim | Error |
|---|---|---|---|---|
| idle-reward | BLOCKED | HISTORICAL_ACTION_LOCKED |  | AMBIGUOUS: historical Idle disk association remains locked. |
| vip-upper-gift | SUCCESS | VERIFIED | 807 |  |
| vip-daily | SUCCESS | VERIFIED | 809 |  |
| ranking-chest | SUCCESS | VERIFIED | 811 |  |
| shop-daily-gift | SUCCESS | VERIFIED | 813 |  |
| shop-weekly-card-gift | SUCCESS | VERIFIED | 815 |  |
| shop-permanent-privilege-gift | SUCCESS | VERIFIED | 817 |  |
| shop-monthly-privilege-gift | SUCCESS | NONE |  |  |
| guild-relic | ALREADY_ATTEMPTED | RESERVED | 487 |  |
| guild-gifts-loot | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED |  |  |
| guild-gifts-member | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED |  |  |
| guild-technology | RESOURCE_NOT_AUTHORIZED | NONE |  |  |
| mail-war | NOT_AVAILABLE | NONE |  |  |
| mail-guild | SUCCESS | VERIFIED | 823 |  |
| mail-system | ALREADY_ATTEMPTED | RESERVED | 425 |  |
| mail-reports | SUCCESS | VERIFIED | 824 |  |
| mail-collection | NOT_AVAILABLE | NONE |  |  |
| dynamic-event-exploration | BLOCKED |  |  |  |

Cleanup: SUCCESS. Event candidates: 7. Event blockers: `{"UNQUALIFIED_NOTIFICATION_GEOMETRY": 8, "EVENT_CONTENT_REQUIRES_QUALIFICATION": 7, "UNQUALIFIED_CONTENT": 7, "UNRESOLVED_SAVED_REWARD_IDENTITY": 2, "ALREADY_ATTEMPTED": 1, "COMPLETED_MISSION_NOT_COLLECTED": 2, "MISSION_LIST_END_UNPROVEN": 1, "CHAPTER_MATERIAL_ACTION_AND_CONTRIBUTION_UNQUALIFIED": 1, "UNQUALIFIED_TASK_GRID_ACTION": 1, "NAVIGATION_REJECTED_BEFORE_INPUT": 1, "UNKNOWN_SCREEN": 1}`.

### Index 3 / automation-account_1 / 1481.625 seconds

| Reward/flow | Result | Journal | Claim | Error |
|---|---|---|---|---|
| idle-reward | BLOCKED | ORIGINAL_EMPTY_PROOF_MISSING |  | Original empty accumulation panel and durable identity are not proven. |
| vip-upper-gift | SUCCESS | VERIFIED | 806 |  |
| vip-daily | SUCCESS | VERIFIED | 808 |  |
| ranking-chest | SUCCESS | VERIFIED | 810 |  |
| shop-daily-gift | SUCCESS | VERIFIED | 812 |  |
| shop-weekly-card-gift | SUCCESS | VERIFIED | 814 |  |
| shop-permanent-privilege-gift | SUCCESS | VERIFIED | 816 |  |
| shop-monthly-privilege-gift | SUCCESS | NONE |  |  |
| guild-relic | SUCCESS | VERIFIED | 822 |  |
| guild-gifts-loot | ALREADY_ATTEMPTED | RESERVED | 138 |  |
| guild-gifts-member | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED |  |  |
| guild-technology | ALREADY_ATTEMPTED | RESERVED | 600 |  |
| mail-war | NOT_AVAILABLE | NONE |  |  |
| mail-guild | UNKNOWN | NONE |  |  |
| mail-system | ALREADY_ATTEMPTED | RESERVED | 656 |  |
| mail-reports | SUCCESS | VERIFIED | 825 |  |
| mail-collection | NOT_AVAILABLE | NONE |  |  |
| dynamic-event-exploration | BLOCKED |  |  |  |

Cleanup: SUCCESS. Event candidates: 7. Event blockers: `{"UNQUALIFIED_NOTIFICATION_GEOMETRY": 9, "EVENT_CONTENT_REQUIRES_QUALIFICATION": 9, "UNQUALIFIED_CONTENT": 9, "MISSION_LIST_END_UNPROVEN": 1, "CHAPTER_MATERIAL_ACTION_AND_CONTRIBUTION_UNQUALIFIED": 1, "UNRESOLVED_SAVED_REWARD_IDENTITY": 2, "UNEXPECTED_EVENT_EXIT_UNRESOLVED": 1, "UNKNOWN_SCREEN": 1}`.

### Index 4 / automation-account_0 / 1378.051 seconds

| Reward/flow | Result | Journal | Claim | Error |
|---|---|---|---|---|
| idle-reward | BLOCKED | LEGACY_ACTION_LOCKED |  | LEGACY_ACTION_LOCKED: Idle task 5 lacks proven original empty/identity evidence. |
| vip-upper-gift | SUCCESS | VERIFIED | 827 |  |
| vip-daily | SUCCESS | VERIFIED | 829 |  |
| ranking-chest | SUCCESS | VERIFIED | 831 |  |
| shop-daily-gift | SUCCESS | VERIFIED | 833 |  |
| shop-weekly-card-gift | SUCCESS | VERIFIED | 835 |  |
| shop-permanent-privilege-gift | ACTION_DISPATCHED_UNVERIFIED | RESERVED | 837 |  |
| shop-monthly-privilege-gift | SUCCESS | NONE |  |  |
| guild-relic | SUCCESS | VERIFIED | 844 |  |
| guild-gifts-loot | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED |  |  |
| guild-gifts-member | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED |  |  |
| guild-technology | RESOURCE_NOT_AUTHORIZED | NONE |  |  |
| mail-war | NOT_AVAILABLE | NONE |  |  |
| mail-guild | SUCCESS | VERIFIED | 845 |  |
| mail-system | ALREADY_ATTEMPTED | RESERVED | 293 |  |
| mail-reports | SUCCESS | VERIFIED | 847 |  |
| mail-collection | NOT_AVAILABLE | NONE |  |  |
| dynamic-event-exploration | BLOCKED |  |  |  |

Cleanup: SUCCESS. Event candidates: 8. Event blockers: `{"UNQUALIFIED_NOTIFICATION_GEOMETRY": 10, "UNRESOLVED_SAVED_REWARD_IDENTITY": 2, "COMPLETED_MISSION_NOT_COLLECTED": 2, "MISSION_LIST_END_UNPROVEN": 1, "EVENT_CONTENT_REQUIRES_QUALIFICATION": 5, "UNQUALIFIED_CONTENT": 5, "CHAPTER_MATERIAL_ACTION_AND_CONTRIBUTION_UNQUALIFIED": 1, "UNQUALIFIED_TASK_GRID_ACTION": 1, "NAVIGATION_REJECTED_BEFORE_INPUT": 1, "UNKNOWN_SCREEN": 1}`.

### Index 5 / automation-account_1 / 1369.015 seconds

| Reward/flow | Result | Journal | Claim | Error |
|---|---|---|---|---|
| idle-reward | BLOCKED | HISTORICAL_ACTION_LOCKED |  | AMBIGUOUS: historical Idle disk association remains locked. |
| vip-upper-gift | SUCCESS | VERIFIED | 828 |  |
| vip-daily | SUCCESS | VERIFIED | 830 |  |
| ranking-chest | SUCCESS | VERIFIED | 832 |  |
| shop-daily-gift | SUCCESS | VERIFIED | 834 |  |
| shop-weekly-card-gift | SUCCESS | VERIFIED | 836 |  |
| shop-permanent-privilege-gift | SUCCESS | VERIFIED | 838 |  |
| shop-monthly-privilege-gift | SUCCESS | NONE |  |  |
| guild-relic | SUCCESS | VERIFIED | 843 |  |
| guild-gifts-loot | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED |  |  |
| guild-gifts-member | NOT_AVAILABLE | NONE |  |  |
| guild-technology | RESOURCE_NOT_AUTHORIZED | NONE |  |  |
| mail-war | NOT_AVAILABLE | NONE |  |  |
| mail-guild | SUCCESS | VERIFIED | 846 |  |
| mail-system | ALREADY_ATTEMPTED | RESERVED | 309 |  |
| mail-reports | SUCCESS | VERIFIED | 848 |  |
| mail-collection | NOT_AVAILABLE | NONE |  |  |
| dynamic-event-exploration | BLOCKED |  |  |  |

Cleanup: SUCCESS. Event candidates: 7. Event blockers: `{"UNQUALIFIED_NOTIFICATION_GEOMETRY": 9, "ALREADY_ATTEMPTED": 1, "MISSION_LIST_END_UNPROVEN": 1, "EVENT_CONTENT_REQUIRES_QUALIFICATION": 4, "UNQUALIFIED_CONTENT": 4, "UNQUALIFIED_TASK_GRID_ACTION": 1, "NAVIGATION_REJECTED_BEFORE_INPUT": 1, "UNKNOWN_SCREEN": 1}`.

### Index 8 / automation-account_0 / 1904.609 seconds

| Reward/flow | Result | Journal | Claim | Error |
|---|---|---|---|---|
| idle-reward | BLOCKED | HISTORICAL_ACTION_LOCKED |  | AMBIGUOUS: historical Idle disk association remains locked. |
| vip-upper-gift | SUCCESS | VERIFIED | 849 |  |
| vip-daily | SUCCESS | VERIFIED | 850 |  |
| ranking-chest | SUCCESS | VERIFIED | 853 |  |
| shop-daily-gift | SUCCESS | VERIFIED | 855 |  |
| shop-weekly-card-gift | SUCCESS | VERIFIED | 857 |  |
| shop-permanent-privilege-gift | SUCCESS | VERIFIED | 859 |  |
| shop-monthly-privilege-gift | SUCCESS | NONE |  |  |
| guild-relic | SUCCESS | VERIFIED | 865 |  |
| guild-gifts-loot | SUCCESS | VERIFIED | 867 |  |
| guild-gifts-member | SUCCESS | VERIFIED | 868 |  |
| guild-technology | SUCCESS | VERIFIED | 870 |  |
| mail-war | NOT_AVAILABLE | NONE |  |  |
| mail-guild | SUCCESS | VERIFIED | 871 |  |
| mail-system | ALREADY_ATTEMPTED | RESERVED | 259 |  |
| mail-reports | SUCCESS | VERIFIED | 872 |  |
| mail-collection | NOT_AVAILABLE | NONE |  |  |
| dynamic-event-exploration | BLOCKED |  |  |  |

Cleanup: SUCCESS. Event candidates: 7. Event blockers: `{"UNQUALIFIED_NOTIFICATION_GEOMETRY": 10, "EVENT_CONTENT_REQUIRES_QUALIFICATION": 8, "UNQUALIFIED_CONTENT": 8, "MISSION_PAGE_LOST": 1, "MISSION_LIST_END_UNPROVEN": 1, "CHAPTER_MATERIAL_ACTION_AND_CONTRIBUTION_UNQUALIFIED": 1, "ALREADY_ATTEMPTED": 1, "UNRESOLVED_SAVED_REWARD_IDENTITY": 1, "NAVIGATION_REJECTED_BEFORE_INPUT": 1, "UNKNOWN_SCREEN": 2}`.

### Index 9 / automation-account_1 / 1465.325 seconds

| Reward/flow | Result | Journal | Claim | Error |
|---|---|---|---|---|
| idle-reward | BLOCKED | ORIGINAL_EMPTY_PROOF_MISSING |  | Original empty accumulation panel and durable identity are not proven. |
| vip-upper-gift | SUCCESS | VERIFIED | 851 |  |
| vip-daily | SUCCESS | VERIFIED | 852 |  |
| ranking-chest | SUCCESS | VERIFIED | 854 |  |
| shop-daily-gift | SUCCESS | VERIFIED | 856 |  |
| shop-weekly-card-gift | SUCCESS | VERIFIED | 858 |  |
| shop-permanent-privilege-gift | SUCCESS | VERIFIED | 860 |  |
| shop-monthly-privilege-gift | SUCCESS | NONE |  |  |
| guild-relic | ACTION_DISPATCHED_UNVERIFIED | RESERVED | 866 |  |
| guild-gifts-loot | BLOCKED | NONE |  | SafetyError: Feature already entered; no silent re-entry. |
| guild-gifts-member | BLOCKED | NONE |  | SafetyError: Feature already entered; no silent re-entry. |
| guild-technology | BLOCKED | NONE |  | SafetyError: Feature already entered; no silent re-entry. |
| mail-war | CURRENT_BATCH_PENDING | NONE |  |  |
| mail-guild | BLOCKED | NONE |  | SafetyError: Feature already entered; no silent re-entry. |
| mail-system | BLOCKED | NONE |  | BootIdentityUnavailable: KhÃ´ng xÃ¡c minh Ä‘Æ°á»£c Android boot ID. |
| mail-reports | BLOCKED | NONE |  | SafetyError: Mail tab/badge is ambiguous. |
| mail-collection | BLOCKED | NONE |  | SafetyError: Mail tab/badge is ambiguous. |
| dynamic-event-exploration | BLOCKED |  |  |  |

Cleanup: SUCCESS. Event candidates: 7. Event blockers: `{"UNQUALIFIED_NOTIFICATION_GEOMETRY": 8, "UNRESOLVED_SAVED_REWARD_IDENTITY": 2, "ALREADY_ATTEMPTED": 1, "COMPLETED_MISSION_NOT_COLLECTED": 2, "MISSION_LIST_END_UNPROVEN": 1, "EVENT_CONTENT_REQUIRES_QUALIFICATION": 4, "UNQUALIFIED_CONTENT": 4, "UNKNOWN_SCREEN": 2}`.

### Index 10 / automation-account_1 / 1206.992 seconds

| Reward/flow | Result | Journal | Claim | Error |
|---|---|---|---|---|
| idle-reward | BLOCKED | HISTORICAL_ACTION_LOCKED |  | AMBIGUOUS: historical Idle disk association remains locked. |
| vip-upper-gift | SUCCESS | VERIFIED | 873 |  |
| vip-daily | SUCCESS | VERIFIED | 874 |  |
| ranking-chest | SUCCESS | VERIFIED | 875 |  |
| shop-daily-gift | SUCCESS | VERIFIED | 876 |  |
| shop-weekly-card-gift | BLOCKED | NONE |  | SafetyError: Shop/tab-bar identity unavailable; no scroll. |
| shop-permanent-privilege-gift | BLOCKED | NONE |  | SafetyError: Shop/tab-bar identity unavailable; no scroll. |
| shop-monthly-privilege-gift | BLOCKED | NONE |  | SafetyError: Shop/tab-bar identity unavailable; no scroll. |
| guild-relic | SUCCESS | VERIFIED | 877 |  |
| guild-gifts-loot | SUCCESS | VERIFIED | 878 |  |
| guild-gifts-member | NOT_AVAILABLE | NONE |  |  |
| guild-technology | ALREADY_ATTEMPTED | RESERVED | 732 |  |
| mail-war | NOT_AVAILABLE | NONE |  |  |
| mail-guild | SUCCESS | VERIFIED | 879 |  |
| mail-system | ALREADY_ATTEMPTED | RESERVED | 270 |  |
| mail-reports | SUCCESS | VERIFIED | 880 |  |
| mail-collection | NOT_AVAILABLE | NONE |  |  |
| dynamic-event-exploration | BLOCKED |  |  |  |

Cleanup: SUCCESS. Event candidates: 8. Event blockers: `{"UNQUALIFIED_NOTIFICATION_GEOMETRY": 9, "COMPLETED_MISSION_NOT_COLLECTED": 2, "MISSION_LIST_END_UNPROVEN": 1, "EVENT_CONTENT_REQUIRES_QUALIFICATION": 8, "UNQUALIFIED_CONTENT": 8, "CHAPTER_MATERIAL_ACTION_AND_CONTRIBUTION_UNQUALIFIED": 1, "ACTION_DISPATCHED_UNVERIFIED": 1, "UNEXPECTED_EVENT_EXIT_UNRESOLVED": 1, "UNKNOWN_SCREEN": 1}`.

### Index 11 / automation-account_0 / 60.665 seconds

| Reward/flow | Result | Journal | Claim | Error |
|---|---|---|---|---|
| idle-reward | BLOCKED | HISTORICAL_ACTION_LOCKED |  | AMBIGUOUS: historical Idle disk association remains locked. |
| vip-upper-gift | BLOCKED | NONE | None | SafetyError: Initial recovery blocked: ADB_ERROR |
| vip-daily | SAFETY_BLOCKED | NONE | None | SafetyError: Initial recovery blocked: ADB_ERROR |
| ranking-chest | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| shop-daily-gift | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| shop-weekly-card-gift | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| shop-permanent-privilege-gift | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| shop-monthly-privilege-gift | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| guild-relic | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| guild-gifts-loot | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| guild-gifts-member | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| guild-technology | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| mail-war | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| mail-guild | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| mail-system | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| mail-reports | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| mail-collection | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |
| dynamic-event-exploration | NOT_RUN_TARGET_BLOCKED | NONE |  | ADB_ERROR |

Cleanup: SUCCESS. Event candidates: None. Event blockers: `{}`.

## Confirmed runtime defects and intended repairs

| Index / UTC | Evidence (relative to run root) | Production function | Finding and intended fix |
|---|---|---|---|
| 4 / 09:43:27â€“09:44:04 | `4/shop/20261023-094327-586528Z-bxh-shop.png`, subsequent 094336, 094348, 094404 frames | `process_reward`, `observe_reward`, `availability` | 837 dispatched; receipt then visible received label. Ticker obscures first settled post-frame. Received label is 0.9997 in 094404; earlier 094348 is 0.4682 while ticker covers it. Speaker template itself misses ticker (~0.489), so special longer ticker wait is never entered. Preserve 837 POSSIBLE; improve bounded known-page post-verification without any claim retry. |
| 10 / 10:31:20â€“10:31:35 | `10/shop/20261023-103120-177555Z-bxh-shop.png`, `103135-281667Z` | `FixedRewardPort.find_tab`, `FixedRewardDetector.observe` | Daily claim 876 succeeds. Weekly and Permanent fail before any swipe (103110/103115); Monthly later swipes once, then fails (103128). All three are skipped. Offline reproduction identifies the exact gate: Back scores 0.959763 / 0.959954 / 0.959933 against 0.96 in frames 103110/103115/103128; Shop page remains positively identified. Require unique strict subpixel-aligned Back evidence (>=0.98), retain all overlay/conflict vetoes; no historical tap coordinates. |
| 9 / 10:10:10â€“10:11:35 | `9/guild/actions.json`, frames 101010, 101023, 101039, 101050 | `GuildMailPort.navigate/guild`, Guild claim verification | 866 dispatched, receipt dismissed, one cooldown frame then unexplained Home. No further recorded automation input. Original claim stays POSSIBLE. Existing no-reentry guard blocks independent Guild siblings; implement only explicit bounded documented safe-Home recovery entry, not silent claim replay. |
| 9 / 10:12:03â€“10:17:55 | `9/mail/actions.json`, 101216 Mail, 101237 Chat, 101248 Home, 101321 onward World | `GuildMailPort.settle/open_reward` | Only initial Homeâ†’Mail input recorded. Cause of intervening screen changes UNPROVEN. Repeated sibling settle polls on positively known GAME_WORLD waste ~5 minutes. Stop polling known foreign surface; recover boundedly only through existing qualified recovery. No blind input. |
| 10 / 10:42:40â€“10:42:56 | `10/events/20261023-104240-816526Z-bxh-shop.png`, 104249 and 104256 | `DynamicEventPort._claim_postcondition`, inline objective effect | 881 dispatched. Completed 1/1 objective disappears; next unmet objective moves to its position, item receipt toast visible. Current verifier requires same-card claimed label or personal-task badge/receipt schema, unsupported for inline row removal. Need independent two-frame exact successor/item-effect proof, otherwise retain uncertainty. 881 remains POSSIBLE. |
| 2/3/4/5/8/9/10 / Event visits | per-account Event reports; representative `2/events/20261023-093422-252755Z-bxh-shop.png` | `task_grid_shell/task_grid_rows`, navigation qualification | Five-card race task grid has a visible green 10/10 action. It is recorded UNQUALIFIED_TASK_GRID_ACTION, not exhausted. Determine failed caption/progress/geometry gate offline; never infer free permission solely from green control. |
| 11 / first 60.665 seconds | `11` recovery report, ADB resolver samples | `Manager._resolve` | Exact indexed transport unavailable. No screenshot/game input; all downstream flows NOT_RUN_TARGET_BLOCKED. This is transport failure, not missed detector reward. No global ADB restart/default serial allowed. |
| all reached accounts | timing records in account reports | Session/Port checks â†’ Manager capture/input; detectors | 1,021â€“1,263 inventories and 137â€“170 captures per account. Repeated identity work plus recovery/feature template matching dominate. Optimize within one fresh transaction; retain original PID/boot/disk/protection and screenshot ownership. Never cache availability. |
| fleet final inventory | before/after instances and correlated command records | `automation_fleet` final audit | Protected index 1 stoppedâ†’running; index 8 label changed Soupâ†’LDPlayer-8 with same disk identity. Causes UNPROVEN. Zero name-write attempts alone cannot identify actor. Report protection flags separately from external runtime changes. Never restore labels/runtime. |

## Safety blocks which must not be removed

- Idle historical ambiguous association / missing original-empty proof / task 5 remain locked. A new day is not proof of a new Idle accumulation.
- Original uncertain journals, including relic 487, loot 138, technology 600/732 and mail 259/293/309/425/656, are not new availability.
- Guild batch journals flagged JOURNAL_PROOF_REVIEW_REQUIRED retain VERIFIED state and proof-review hold; do not erase/replay them.
- STONE Technology is not authorized; WOOD-only flow on index 8 succeeded.
- Event Go buttons, book resource actions, auto-throw/material controls and unqualified training-map chests are not proven free claims. Preserve explicit blockers.
- No account worker was aborted solely by the Shop or Guild failure: index 10 continued Guild/Mail/Events and index 9 reached Events. Index 11 alone was target-blocked.

## Exclusive timing baseline

Percentages use account elapsed time. Recovery/feature detection columns are exclusive and exclude nested OCR; stage elapsed totals overlap and must not be added. Residual is account wall time minus all exclusive metrics. Startup/navigation/verification inclusive timings remain in original reports.

| Index | Wall s | Inventory s (%) | Other identity s (%) | Capture s (%) | Recovery detection s (%) | Feature detection s (%) | OCR s (%) | Wait s (%) | Residual s |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 1444.304 | 265.46 (18.4%) | 199.29 (13.8%) | 90.56 (6.3%) | 278.61 (19.3%) | 320.16 (22.2%) | 127.09 (8.8%) | 68.12 (4.7%) | 21.70 |
| 3 | 1481.625 | 268.17 (18.1%) | 204.65 (13.8%) | 93.00 (6.3%) | 303.66 (20.5%) | 321.27 (21.7%) | 128.42 (8.7%) | 67.72 (4.6%) | 18.23 |
| 4 | 1378.051 | 254.41 (18.5%) | 193.92 (14.1%) | 82.27 (6.0%) | 300.81 (21.8%) | 329.43 (23.9%) | 57.29 (4.2%) | 68.92 (5.0%) | 19.39 |
| 5 | 1369.015 | 255.51 (18.7%) | 187.74 (13.7%) | 78.18 (5.7%) | 292.36 (21.4%) | 315.05 (23.0%) | 88.91 (6.5%) | 61.73 (4.5%) | 18.09 |
| 8 | 1904.609 | 310.78 (16.3%) | 246.70 (13.0%) | 111.25 (5.8%) | 410.38 (21.5%) | 458.07 (24.1%) | 164.54 (8.6%) | 68.93 (3.6%) | 24.82 |
| 9 | 1465.325 | 254.16 (17.3%) | 206.06 (14.1%) | 106.70 (7.3%) | 361.63 (24.7%) | 284.74 (19.4%) | 68.61 (4.7%) | 77.30 (5.3%) | 20.64 |
| 10 | 1206.992 | 231.03 (19.1%) | 178.31 (14.8%) | 76.50 (6.3%) | 227.59 (18.9%) | 253.78 (21.0%) | 69.06 (5.7%) | 79.14 (6.6%) | 19.83 |
| 11 | 60.665 | 21.33 (35.2%) | 11.36 (18.7%) | 0.00 (0.0%) | 0.00 (0.0%) | 0.00 (0.0%) | 0.00 (0.0%) | 25.21 (41.6%) | 0.21 |

No after-repair end-to-end measurement exists. A few-minute healthy-account target is **not achieved or claimed** by this inventory. Phase 8 remains PARTIAL. User owns the final normal-UI Start.

### Offline reproducibility notes

Saved PNGs are normalized landscape with metadata rotated_from_portrait=true. Restore portrait before ScreenshotService when replaying fixtures, otherwise device geometry is wrong. The original matching pixels are unchanged. OpenCV thread-cap experiment (16/1/2) on four frames shows no material gain; do not change global threads as a performance fix.

## Monthly independent child outcomes (original run19)

| Index | Monthly quick | Monthly daily |
|---|---|---|
| 2 | {'result': 'SUCCESS', 'journal': 'VERIFIED', 'claim_id': 818, 'claim_dispatched': True} | {'result': 'SUCCESS', 'journal': 'VERIFIED', 'claim_id': 820, 'claim_dispatched': True} |
| 3 | {'result': 'SUCCESS', 'journal': 'VERIFIED', 'claim_id': 819, 'claim_dispatched': True} | {'result': 'SUCCESS', 'journal': 'VERIFIED', 'claim_id': 821, 'claim_dispatched': True} |
| 4 | {'result': 'SUCCESS', 'journal': 'VERIFIED', 'claim_id': 839, 'claim_dispatched': True} | {'result': 'SUCCESS', 'journal': 'VERIFIED', 'claim_id': 842, 'claim_dispatched': True} |
| 5 | {'result': 'SUCCESS', 'journal': 'VERIFIED', 'claim_id': 840, 'claim_dispatched': True} | {'result': 'SUCCESS', 'journal': 'VERIFIED', 'claim_id': 841, 'claim_dispatched': True} |
| 8 | {'result': 'SUCCESS', 'journal': 'VERIFIED', 'claim_id': 861, 'claim_dispatched': True} | {'result': 'SUCCESS', 'journal': 'VERIFIED', 'claim_id': 863, 'claim_dispatched': True} |
| 9 | {'result': 'SUCCESS', 'journal': 'VERIFIED', 'claim_id': 862, 'claim_dispatched': True} | {'result': 'SUCCESS', 'journal': 'VERIFIED', 'claim_id': 864, 'claim_dispatched': True} |
| 10 | NOT_REACHED: parent tab blocked | NOT_REACHED: parent tab blocked |

## Repair boundary

Run19 race-grid shell is correctly recognized (five complete cards); failed gates are action-column OCR and one missing fraction reading, not card count. Complete current control isolation and paired raw progress readings repair the missed free 10/10 card, with conflicting recognized fractions still vetoed. No account coordinates or new click route.

Claim 881 has an item toast and removed objective, but no already-qualified receipt plus exact consumption counter/successor identity proof. It stays POSSIBLE; row absence/toast alone are not upgraded to VERIFIED. Inline removal verification remains an explicit unsupported proof variant, not a successful fix. Claim866 has only one cooldown frame before unexplained Home; it also stays POSSIBLE. Claim837 remains POSSIBLE even though a later original clean frame shows received state; this repair changes future bounded verification, not live journals.

## Per-feature elapsed spans (overlapping CPU categories above)

| Index | Initial readiness/Home s (%) | Idle s | VIP s | Ranking s | Shop s | Guild s | Mail s | Events s | Cleanup s |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 116.99 (8.1%) | 0.63 | 85.43 | 65.22 | 229.40 | 296.93 | 270.58 | 372.86 | 1.68 |
| 3 | 120.91 (8.2%) | 0.74 | 74.29 | 60.91 | 245.36 | 362.08 | 218.09 | 393.04 | 1.93 |
| 4 | 116.68 (8.5%) | 0.76 | 76.79 | 61.20 | 277.93 | 299.34 | 216.00 | 323.62 | 1.61 |
| 5 | 99.05 (7.2%) | 0.58 | 74.00 | 64.70 | 256.36 | 304.75 | 214.53 | 348.93 | 1.69 |
| 8 | 119.26 (6.3%) | 0.80 | 87.75 | 62.70 | 244.07 | 562.43 | 270.39 | 550.10 | 1.99 |
| 9 | 130.69 (8.9%) | 0.73 | 79.99 | 69.41 | 240.71 | 144.51 | 380.50 | 412.49 | 1.50 |
| 10 | 146.59 (12.1%) | 0.81 | 80.37 | 71.10 | 107.02 | 318.25 | 175.31 | 301.10 | 1.37 |
| 11 | 55.61 (91.7%) | 0.31 | 0.91 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.53 |

Run19 does not contain a separate full postcondition-verification metric for fixed or Guild/Mail claims. Do not infer one from inclusive navigation/capture totals. This repair adds `postcondition_verification` measurement around the actual verification sequence; underlying capture/detection/OCR/DB categories remain exclusive and worker-local. Input and cleanup costs are recorded separately in the original metrics; no fabricated percentage is assigned to missing stages.

## Self-review and validation contract

- Fresh-operation guard shares only the current Manager transaction proof; no disk/PID/boot/protection/selection cache. Indexed serial and explicit transport boot still checked on every capture/input. Last selected read supplies the guard with current runtime.
- Failed capture and any attempted dispatch invalidate prior frames. Current-frame reuse occurs only inside the same port while no input has consumed it.
- Shop footer uses strict >=0.98 subpixel alignment after weak Back evidence; full-footer duplicate search remains. No confidence lowering, account coordinates, paid controls or alternative route.
- Guild/Mail gets ONE recorded navigation-only sibling recovery per feature, including failed attempts. A fresh Home frame permits at most one explicitly recorded re-entry, never a claim replay. Unknown/unqualified surfaces remain without input.
- Existing journal policy, reset rules, WOOD-only contribution, frozen plan, workers, instance ownership and cleanup terminal guards are unchanged. No live journals have been edited.
- Protected flag/selection audit is reported independently from runtime deltas; original stricter `protected_state_unchanged` and overall PASS criteria remain unchanged. Causes of manual/runtime/label changes are not inferred.
- Original evidence fixtures contain game UI only; no credentials, tokens, cookies, API keys or unrelated files were copied. OCR transcript contains only the task card text and pixel hashes.
- Full CI/portable smoke and artifact provenance must pass before replacing Desktop app; final normal-UI Start belongs to USER. No gameplay acceptance was run in this repair.

## Offline before/after measurements

Same host, same original portrait pixels, old classes loaded from Git `5988549`, current classes, warm-up excluded, three samples each in alternating order, median wall seconds. No other test process running during this final benchmark. These are detector component timings, not account runtime.

| Original run19 frame | Before s | After s | Reduction |
|---|---|---|---|
| shop-back-resampled | 2.094 | 1.933 | 7.7% |
| shop-permanent-ticker | 2.638 | 2.212 | 16.2% |
| shop-permanent-received | 3.884 | 3.472 | 10.6% |

Production Manager + Session call-count benchmark uses the existing fake transport,
never a real ADB command. Before/after: capture inventory reads **3→2**, input
inventory reads **5→3**, indexed boot reads **2→1** each; explicit transport boot
and indexed serial reads stay **1→1**. PID/disk/protection changes still fail before
capture/input. This is transaction-local reuse, not a session-wide identity cache.

Current unconsumed navigation/confirmation frames now carry into the next fixed or
Guild/Mail reward and final Home inspection. A failed fresh capture or attempted
input consumes prior evidence, including uncertain transport errors. Known World
settling returns immediately instead of six additional captures per Mail sibling.
All healthy availability/postcondition exits still return immediately; only an
already-dispatched, known-page UNKNOWN post-state gains at most two extra capture
attempts for the proven ticker obstruction. No global timeout increase.

Validation before CI: 285 related tests passed; another 71 receipt/overlay/transport
checks passed; final new run19 suite **22 passed**. Suites overlap; do not add these
numbers as distinct tests. Ruff on all affected files and diff whitespace checks
passed. Self-review covered duplicate dispatch, stale frames, journal preservation,
retry bounds, exact target, sibling isolation and unchanged flow scope. Live DB
comparison: **859/859 journal rows byte-for-byte unchanged**, max ID881.

Full end-to-end after-repair duration is **NOT MEASURED** because this task forbids
another gameplay run. The few-minute target remains unproven. Fresh passing CI and
portable delivery do not establish runtime acceptance or Phase8 PASS.

## Final UNKNOWN coverage correction

First full gate: `b1aefcb`, CI39985246415, all steps passed. A final negative
boundary check then reproduced an additional reporting defect: a green card with
recognized geometry but contradictory progress remained UNKNOWN, yet
`unresolved_grid_actions` treated its geometry alone as accounted for. The new
assertion failed on the original run19 pixels. The final targeted correction
requires a positively AVAILABLE/NOT_AVAILABLE row before accounting for a green
control; UNKNOWN keeps UNQUALIFIED_TASK_GRID_ACTION and cannot mark traversal
exhausted. No input permission or journal eligibility is added. Fresh full CI is
required for this final correction before Desktop delivery.
