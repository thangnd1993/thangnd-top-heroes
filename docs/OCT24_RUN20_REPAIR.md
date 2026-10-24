# October24 normal application run20 — diagnosis and repair

## Exact evidence

- Run ID **20**, origin **normal-ui-start**, two workers, eight frozen targets.
- October24 **12:54:12–13:41:58 Vietnam** (~47m46s). Report result PARTIAL; SQLite run status FAILED / completed0 / failed8 refers to account coverage, not claim counts.
- Executable `C:\Users\ADMIN\Desktop\app\TopHeroesAutoManager\TopHeroesAutoManager.exe`.
- Commit `c2dac26e20db28f6e3e635960b2c0f34f31ffccb`, CI `40062497019`, SHA256 `8682e8caef1cfbb036f8b8c2748cc56d52bf99ff02659874463ca994c1b3957a` recorded by THIS run.
- Root report: `C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\tasks\automation\20261024-055412-465873Z-a4dcc84e\fleet-report.json`.
- Each account is `<root>/<index>/account-report.json`; all flow reports and referenced recovery reports were read. Actual blocked-content screenshots were visually inspected, not inferred from old runs.
- **Actual application log read:** `logs/app.log` contains695 lines explicitly tagged `run=20`, spanning October24 12:54:12.445–13:41:57.894. The file metadata still displays an October23 modification time, which is NOT evidence that log content is missing. Correlated per-account line counts:2=135,3=15,4=130,5=140,8=26,9=129,10=92,11=26;2 run-level lines. TransportResolutionError stack traces on8/11 agree with their exact ABSENT targets. Index3 logs one open_game at12:54:59.746 and ANDROID_HOME at12:55:13.472; no package-launch stdout was recorded. Missing stdout, not a missing general log, limits that root-cause diagnosis.
- Read-only journal snapshot: 904 rows, max ID926. Run20 added 45 rows: **43 VERIFIED and 2 RESERVED/POSSIBLE (883/885, VIP daily)**. No production journal was changed during repair.
- Report: Protected flags/runtime unchanged, all selections restored, names unchanged, zero name-write attempts. No emulator or gameplay session was started for this task.

## Actual per-account runtime

| Index | Label at run time | Worker wall seconds | Startup/Home | VIP | BXH | Shop | Guild | Mail | Events | Cleanup |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | Emmmm | 1224.598 | 111.365 | 85.142 | 49.945 | 184.594 | 209.008 | 152.722 | 425.736 | 1.61 |
| 3 | Queen con | 62.542 | 56.928 | 1.82 | — | — | — | — | — | 1.57 |
| 4 | 3-Chíp | 1029.771 | 96.829 | 94.986 | 50.742 | 184.699 | 242.191 | 171.562 | 182.617 | 1.421 |
| 5 | 4-Em Pé | 1137.96 | 124.209 | 73.726 | 54.089 | 165.675 | 230.775 | 169.697 | 313.67 | 1.47 |
| 8 | soup | 56.579 | 53.072 | 0.801 | — | — | — | — | — | 1.316 |
| 9 | Mini Queen | 1069.26 | 146.922 | 74.178 | 54.132 | 178.933 | 193.996 | 131.43 | 282.911 | 1.648 |
| 10 | HiHi | 629.256 | 118.2 | 56.084 | 32.204 | 80.06 | 176.485 | 60.293 | 99.06 | 1.355 |
| 11 | Smile | 56.6 | 52.448 | 0.833 | — | — | — | — | — | 1.372 |

Wall intervals include worker overhead; stage metrics can nest, so inclusive stage totals MUST NOT be summed as separate cost. Slowest worker: index2 (1224.598s); slowest flow: its Events (425.736s). Index9 startup/Home took146.922s. Queue wait is separate from worker wall time.

### Largest measured exclusive costs (seconds / calls)

| Index | Recovery recognition | Other detection | Inventory commands | Identity commands | OCR | Capture commands | Deliberate waits |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | 256.681/125 | 215.555/103 | 181.741/824 | 151.563/722 | 180.975/274 | 78.059/130 | 65.134/62 |
| 3 | 3.474/2 | 0/0 | 22.223/85 | 12.964/32 | 0/0 | 3.358/2 | 18.006/17 |
| 4 | 235.395/111 | 241.832/85 | 164.952/751 | 134.168/647 | 70.919/110 | 63.495/114 | 53.832/46 |
| 5 | 239.399/124 | 230.156/96 | 176.116/802 | 142.809/698 | 126.189/194 | 71.011/126 | 67.337/51 |
| 8 | 0/0 | 0/0 | 18.047/87 | 11.345/47 | 0/0 | 0/0 | 25.614/40 |
| 9 | 248.084/123 | 186.189/100 | 168.291/782 | 143.582/690 | 75.881/115 | 90.565/127 | 77.382/62 |
| 10 | 111.311/79 | 117.914/59 | 130.065/609 | 92.611/471 | 29.279/52 | 48.958/81 | 56.868/37 |
| 11 | 0/0 | 0/0 | 18.8/86 | 11.163/47 | 0/0 | 0/0 | 24.613/39 |

## Complete frozen reward inventory

A visible green control is not automatically eligible: unresolved original action identity, POSSIBLE and invalid historical causal proof remain locks. NOT_RUN does not mean NOT_AVAILABLE. The Monthly aggregate has independent upper/bulk and daily children; its journal NONE must not hide child VERIFIED states.

### Index 2 / Emmmm

| Reward | Actual result | Journal / claim | Dispatched this run | Error / reason |
|---|---|---|---|---|
| idle-reward | BLOCKED | HISTORICAL_ACTION_LOCKED | False | AMBIGUOUS: historical Idle disk association remains locked. |
| vip-upper-gift | SUCCESS | VERIFIED/882 | True | — |
| vip-daily | ACTION_DISPATCHED_UNVERIFIED | RESERVED/883 | True | — |
| ranking-chest | SUCCESS | VERIFIED/886 | True | — |
| shop-daily-gift | SUCCESS | VERIFIED/887 | True | — |
| shop-weekly-card-gift | SUCCESS | VERIFIED/889 | True | — |
| shop-permanent-privilege-gift | SUCCESS | VERIFIED/890 | True | — |
| shop-monthly-privilege-gift | SUCCESS | NONE | True | — |
| shop-monthly-quick-collect (independent child) | SUCCESS | VERIFIED/893 | True | — |
| shop-monthly-daily (independent child) | SUCCESS | VERIFIED/895 | True | — |
| guild-relic | ALREADY_ATTEMPTED | RESERVED/487 | False | — |
| guild-gifts-loot | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED | False | — |
| guild-gifts-member | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED | False | — |
| guild-technology | RESOURCE_NOT_AUTHORIZED | NONE | False | — |
| mail-war | NOT_AVAILABLE | NONE | False | — |
| mail-guild | SUCCESS | VERIFIED/899 | True | — |
| mail-system | ALREADY_ATTEMPTED | RESERVED/425 | False | — |
| mail-reports | SUCCESS | VERIFIED/900 | True | — |
| mail-collection | NOT_AVAILABLE | NONE | False | — |
| dynamic-event-exploration | BLOCKED | NONE | False | — |

Cleanup: SUCCESS; selection restored: True.

Event candidates: 8; rewards dispatched: 0; scan COMPLETE.

- Candidate `51c0d7f0008219ca9efc2c2f89250d4b78d8061b71e09b6be5f3a8dbd682ad6d`: BLOCKED, visits=1, nested=2.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event:ac8b25cd7e4add55fae097944d640edd62ad672583abc9c43eca82fe475de884`; captures `20261024-060757-389649Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event:ac8b25cd7e4add55fae097944d640edd62ad672583abc9c43eca82fe475de884`; captures `20261024-060757-389649Z-bxh-shop.png`.
  - UNRESOLVED_SAVED_REWARD_IDENTITY; page `event:event:personal-tasks`; captures `20261024-060810-116116Z-bxh-shop.png`, `20261024-060830-517162Z-bxh-shop.png`.
  - COMPLETED_MISSION_NOT_COLLECTED; page `event:event:personal-tasks`; captures `20261024-060810-116116Z-bxh-shop.png`.
  - MISSION_LIST_END_UNPROVEN; page `event:event:personal-tasks`; captures `20261024-060810-116116Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event:e859baacab247efbb8c6361953657ad6bae95c54adbf69ec04a437e382000f9d`; captures `20261024-060836-942308Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event:e859baacab247efbb8c6361953657ad6bae95c54adbf69ec04a437e382000f9d`; captures `20261024-060836-942308Z-bxh-shop.png`.
- Candidate `21dcdb3330a0d0d72581c50ca27b34cf3a38c659b64d7739e1c228449ccbfbff`: BLOCKED, visits=1, nested=5.
  - UNRESOLVED_SAVED_REWARD_IDENTITY; page `event:functional-race-task-grid:race-task-grid`; captures `20261024-061003-711058Z-bxh-shop.png`.
  - UNQUALIFIED_TASK_GRID_ACTION; page `event:functional-race-task-grid:race-task-grid`; captures `20261024-061003-711058Z-bxh-shop.png`.
  - NAVIGATION_REJECTED_BEFORE_INPUT; page `event:functional-race-task-grid:race-task-grid`; captures `20261024-061003-711058Z-bxh-shop.png`.
- Candidate `e094d2d5607dd56e3f3af7d08c1cbc631dde7da672c403cfe85fd9070fe40bf0`: BLOCKED, visits=1, nested=2.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:thdbng:0e6186a66dfa0cde8881bb444bf6edf51d7787b0f005ed325ffb0d0da599eed9`; captures `20261024-061211-000399Z-bxh-shop.png`, `20261024-061236-173275Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:thdbng:0e6186a66dfa0cde8881bb444bf6edf51d7787b0f005ed325ffb0d0da599eed9`; captures `20261024-061211-000399Z-bxh-shop.png`, `20261024-061236-173275Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:thdbng:abc179a4ea8c04468bbad8867831e2429562c0eb1e27bd36c5f4dd07fc4e76cc`; captures `20261024-061221-678834Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:thdbng:abc179a4ea8c04468bbad8867831e2429562c0eb1e27bd36c5f4dd07fc4e76cc`; captures `20261024-061221-678834Z-bxh-shop.png`.
- Candidate `9beb7ca19c853e7098e0b01ee9a93ac42a45f1f5d352ca7cd23e07945c730a86`: BLOCKED, visits=1, nested=0.
  - UNKNOWN_SCREEN; page `UNKNOWN`; captures `20261024-061255-659637Z-bxh-shop.png`.
- Candidate `5139d8845ad318d444a55457e5eec8303ee074f4ad96f6e494aba11dd1b9df19`: BLOCKED, visits=0, nested=0.
  - GLOBAL_TRAVERSAL_BLOCKER; page `—`; captures .
- Candidate `76e58746cd0e6d7be80a1bd58ba85ba1556b30ae1c10f5c8ca1fb266b5d805f7`: BLOCKED, visits=1, nested=4.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event gia tri:c96ec35d7495c9b98d54f75de88594286103fee43c2e75f2b55072a0cacdd82f`; captures `20261024-061343-395107Z-bxh-shop.png`, `20261024-061404-579808Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event gia tri:c96ec35d7495c9b98d54f75de88594286103fee43c2e75f2b55072a0cacdd82f`; captures `20261024-061343-395107Z-bxh-shop.png`, `20261024-061404-579808Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event gia tri:aac8e2521c99f76a6bb42ae9b0171e8b8f2bc1f5aa9de2e74a188151866fc987`; captures `20261024-061355-498109Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event gia tri:aac8e2521c99f76a6bb42ae9b0171e8b8f2bc1f5aa9de2e74a188151866fc987`; captures `20261024-061355-498109Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event gia tri:85ea578c4dcf6516ae95328d4ce60fc112120b799249a3009203445bd0c7e0af`; captures `20261024-061414-729490Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event gia tri:85ea578c4dcf6516ae95328d4ce60fc112120b799249a3009203445bd0c7e0af`; captures `20261024-061414-729490Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event gia tri:d677c42110e6fe5c5a6628e52feb583b1b2c438bc3507e3ca116f2eb246acbe2`; captures `20261024-061424-687073Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event gia tri:d677c42110e6fe5c5a6628e52feb583b1b2c438bc3507e3ca116f2eb246acbe2`; captures `20261024-061424-687073Z-bxh-shop.png`.
- Candidate `f1fa4eb86233a8f8d8e0f0b2ad240d414f5f3f9a0fec3fc086fed445596190a3`: BLOCKED, visits=0, nested=0.
  - PRIOR_ROOT_REACQUISITION_FAILED; page `home`; captures `20261024-061434-144349Z-bxh-shop.png`.
- Candidate `f041fde6dec0f0a221c51496213f4d0eee2ab69295742708b003ac5b9687dc1a`: BLOCKED, visits=1, nested=0.
  - EVENT_REACQUISITION_FAILED; page `home`; captures `20261024-061321-278246Z-bxh-shop.png`.
  - PRIOR_ROOT_REACQUISITION_FAILED; page `home`; captures `20261024-061335-260224Z-bxh-shop.png`.

### Index 3 / Queen con

| Reward | Actual result | Journal / claim | Dispatched this run | Error / reason |
|---|---|---|---|---|
| idle-reward | BLOCKED | ORIGINAL_EMPTY_PROOF_MISSING | False | Original empty accumulation panel and durable identity are not proven. |
| vip-upper-gift | BLOCKED | NONE | False | SafetyError: Initial recovery blocked: ACTION_FAILED |
| vip-daily | SAFETY_BLOCKED | NONE | False | SafetyError: Initial recovery blocked: ACTION_FAILED |
| ranking-chest | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| shop-daily-gift | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| shop-weekly-card-gift | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| shop-permanent-privilege-gift | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| shop-monthly-privilege-gift | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| guild-relic | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| guild-gifts-loot | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| guild-gifts-member | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| guild-technology | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| mail-war | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| mail-guild | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| mail-system | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| mail-reports | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| mail-collection | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |
| dynamic-event-exploration | NOT_RUN_TARGET_BLOCKED | NONE | False | ACTION_FAILED |

Cleanup: SUCCESS; selection restored: True.

Recovery **ACTION_FAILED**: Game launch did not change Android home.

Source: `C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\recovery\3-a82846a37bab6b4c45c77ee4b087dd164883863d97f2d76195cbd72efc82a4af\20261024-055417-599674Z\report.json`.

### Index 4 / 3-Chíp

| Reward | Actual result | Journal / claim | Dispatched this run | Error / reason |
|---|---|---|---|---|
| idle-reward | BLOCKED | NONE | False | Không xác minh được Android boot ID. |
| vip-upper-gift | SUCCESS | VERIFIED/884 | True | — |
| vip-daily | ACTION_DISPATCHED_UNVERIFIED | RESERVED/885 | True | — |
| ranking-chest | SUCCESS | VERIFIED/888 | True | — |
| shop-daily-gift | SUCCESS | VERIFIED/891 | True | — |
| shop-weekly-card-gift | SUCCESS | VERIFIED/892 | True | — |
| shop-permanent-privilege-gift | SUCCESS | VERIFIED/894 | True | — |
| shop-monthly-privilege-gift | SUCCESS | NONE | True | — |
| shop-monthly-quick-collect (independent child) | SUCCESS | VERIFIED/896 | True | — |
| shop-monthly-daily (independent child) | SUCCESS | VERIFIED/897 | True | — |
| guild-relic | SUCCESS | VERIFIED/898 | True | — |
| guild-gifts-loot | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED | False | — |
| guild-gifts-member | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED | False | — |
| guild-technology | RESOURCE_NOT_AUTHORIZED | NONE | False | — |
| mail-war | SUCCESS | VERIFIED/901 | True | — |
| mail-guild | SUCCESS | VERIFIED/902 | True | — |
| mail-system | ALREADY_ATTEMPTED | RESERVED/293 | False | — |
| mail-reports | SUCCESS | VERIFIED/903 | True | — |
| mail-collection | NOT_AVAILABLE | NONE | False | — |
| dynamic-event-exploration | BLOCKED | NONE | False | — |

Cleanup: SUCCESS; selection restored: True.

Recovery **UNKNOWN_SCREEN**: Screen remained UNKNOWN; no input sent.

Source: `C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\recovery\4-e4df71fdeede9229af662e94226104b2873185e8c4ccba09ef9d38cb65829865\20261024-061210-846584Z\report.json`.

Event candidates: 7; rewards dispatched: 0; scan COMPLETE.

- Candidate `51c0d7f0008219ca9efc2c2f89250d4b78d8061b71e09b6be5f3a8dbd682ad6d`: BLOCKED, visits=1, nested=1.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event:ac8b25cd7e4add55fae097944d640edd62ad672583abc9c43eca82fe475de884`; captures `20261024-060948-162940Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event:ac8b25cd7e4add55fae097944d640edd62ad672583abc9c43eca82fe475de884`; captures `20261024-060948-162940Z-bxh-shop.png`.
  - UNRESOLVED_SAVED_REWARD_IDENTITY; page `event:event:personal-tasks`; captures `20261024-060959-284966Z-bxh-shop.png`, `20261024-061018-163854Z-bxh-shop.png`.
  - COMPLETED_MISSION_NOT_COLLECTED; page `event:event:personal-tasks`; captures `20261024-060959-284966Z-bxh-shop.png`.
  - MISSION_LIST_END_UNPROVEN; page `event:event:personal-tasks`; captures `20261024-060959-284966Z-bxh-shop.png`.
- Candidate `47c52a4c7759243206721f2f579dd7f3d09559573e667a1ea2b985447d4fe781`: BLOCKED, visits=1, nested=2.
  - UNEXPECTED_EVENT_EXIT_UNRESOLVED; page `home`; captures `20261024-061106-235843Z-bxh-shop.png`.
- Candidate `210d67f53367ba9f1bfda28e4a10fcf30e54e5c5148006ada6b39128d1654d31`: BLOCKED, visits=1, nested=2.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:thdbng:0e6186a66dfa0cde8881bb444bf6edf51d7787b0f005ed325ffb0d0da599eed9`; captures `20261024-061117-151653Z-bxh-shop.png`, `20261024-061144-705017Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:thdbng:0e6186a66dfa0cde8881bb444bf6edf51d7787b0f005ed325ffb0d0da599eed9`; captures `20261024-061117-151653Z-bxh-shop.png`, `20261024-061144-705017Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:thdbng:e7ac19ad20ae18c7d139f9137e9c8367f3e4b79fa4d3886ad095a908acac5977`; captures `20261024-061127-726877Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:thdbng:e7ac19ad20ae18c7d139f9137e9c8367f3e4b79fa4d3886ad095a908acac5977`; captures `20261024-061127-726877Z-bxh-shop.png`.
- Candidate `a5441d357e145d8d1bb686bab3f172b76aef2e419ef1edfea922804b5251eb4b`: BLOCKED, visits=1, nested=0.
  - UNKNOWN_SCREEN; page `UNKNOWN`; captures `20261024-061202-003751Z-bxh-shop.png`.
- Candidate `a2abb05fcd5aa1ed12efe16c8995b2a62aab2ee4a04bde1b44ee6ab1bdb68741`: BLOCKED, visits=0, nested=0.
  - GLOBAL_TRAVERSAL_BLOCKER; page `—`; captures .
- Candidate `9ad9cc6f9343bf7be38382e6b6819e920180c3f5fb7812d860a5c92ba2f86cbe`: BLOCKED, visits=0, nested=0.
  - GLOBAL_TRAVERSAL_BLOCKER; page `—`; captures .
- Candidate `f1fa4eb86233a8f8d8e0f0b2ad240d414f5f3f9a0fec3fc086fed445596190a3`: BLOCKED, visits=0, nested=0.
  - GLOBAL_TRAVERSAL_BLOCKER; page `—`; captures .

### Index 5 / 4-Em Pé

| Reward | Actual result | Journal / claim | Dispatched this run | Error / reason |
|---|---|---|---|---|
| idle-reward | BLOCKED | HISTORICAL_ACTION_LOCKED | False | AMBIGUOUS: historical Idle disk association remains locked. |
| vip-upper-gift | SUCCESS | VERIFIED/904 | True | — |
| vip-daily | SUCCESS | VERIFIED/905 | True | — |
| ranking-chest | SUCCESS | VERIFIED/906 | True | — |
| shop-daily-gift | SUCCESS | VERIFIED/907 | True | — |
| shop-weekly-card-gift | SUCCESS | VERIFIED/908 | True | — |
| shop-permanent-privilege-gift | SUCCESS | VERIFIED/909 | True | — |
| shop-monthly-privilege-gift | SUCCESS | NONE | True | — |
| shop-monthly-quick-collect (independent child) | SUCCESS | VERIFIED/911 | True | — |
| shop-monthly-daily (independent child) | SUCCESS | VERIFIED/913 | True | — |
| guild-relic | SUCCESS | VERIFIED/915 | True | — |
| guild-gifts-loot | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED | False | — |
| guild-gifts-member | NOT_AVAILABLE | NONE | False | — |
| guild-technology | RESOURCE_NOT_AUTHORIZED | NONE | False | — |
| mail-war | SUCCESS | VERIFIED/921 | True | — |
| mail-guild | SUCCESS | VERIFIED/922 | True | — |
| mail-system | ALREADY_ATTEMPTED | RESERVED/309 | False | — |
| mail-reports | SUCCESS | VERIFIED/923 | True | — |
| mail-collection | NOT_AVAILABLE | NONE | False | — |
| dynamic-event-exploration | BLOCKED | NONE | False | — |

Cleanup: SUCCESS; selection restored: True.

Recovery **UNKNOWN_SCREEN**: Screen remained UNKNOWN; no input sent.

Source: `C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\recovery\5-9ded940bf8189266c4a64eb56ba65aee47b2c001c83057db488a646a999ec775\20261024-063109-413835Z\report.json`.

Event candidates: 7; rewards dispatched: 1; scan COMPLETE.

- Candidate `51c0d7f0008219ca9efc2c2f89250d4b78d8061b71e09b6be5f3a8dbd682ad6d`: BLOCKED, visits=1, nested=1.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event:ac8b25cd7e4add55fae097944d640edd62ad672583abc9c43eca82fe475de884`; captures `20261024-062635-753854Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event:ac8b25cd7e4add55fae097944d640edd62ad672583abc9c43eca82fe475de884`; captures `20261024-062635-753854Z-bxh-shop.png`.
  - UNRESOLVED_SAVED_REWARD_IDENTITY; page `event:event:personal-tasks`; captures `20261024-062645-035192Z-bxh-shop.png`, `20261024-062713-563348Z-bxh-shop.png`.
  - ALREADY_ATTEMPTED; page `event:event:personal-tasks`; captures `20261024-062645-035192Z-bxh-shop.png`.
  - COMPLETED_MISSION_NOT_COLLECTED; page `event:event:personal-tasks`; captures `20261024-062645-035192Z-bxh-shop.png`.
  - MISSION_LIST_END_UNPROVEN; page `event:event:personal-tasks`; captures `20261024-062645-035192Z-bxh-shop.png`.
- Candidate `957cb16052ce9024a78e9423c9b77bb34a4b2ba64fc7f6d601c2b9b156ff9304`: BLOCKED, visits=1, nested=5.
  - UNRESOLVED_SAVED_REWARD_IDENTITY; page `event:functional-race-task-grid:race-task-grid`; captures `20261024-062831-294025Z-bxh-shop.png`.
  - UNQUALIFIED_TASK_GRID_ACTION; page `event:functional-race-task-grid:race-task-grid`; captures `20261024-062831-294025Z-bxh-shop.png`.
  - NAVIGATION_REJECTED_BEFORE_INPUT; page `event:functional-race-task-grid:race-task-grid`; captures `20261024-062831-294025Z-bxh-shop.png`.
- Candidate `210d67f53367ba9f1bfda28e4a10fcf30e54e5c5148006ada6b39128d1654d31`: BLOCKED, visits=1, nested=2.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:thdbng:0e6186a66dfa0cde8881bb444bf6edf51d7787b0f005ed325ffb0d0da599eed9`; captures `20261024-063024-996943Z-bxh-shop.png`, `20261024-063044-304241Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:thdbng:0e6186a66dfa0cde8881bb444bf6edf51d7787b0f005ed325ffb0d0da599eed9`; captures `20261024-063024-996943Z-bxh-shop.png`, `20261024-063044-304241Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:thdbng:e7ac19ad20ae18c7d139f9137e9c8367f3e4b79fa4d3886ad095a908acac5977`; captures `20261024-063033-391387Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:thdbng:e7ac19ad20ae18c7d139f9137e9c8367f3e4b79fa4d3886ad095a908acac5977`; captures `20261024-063033-391387Z-bxh-shop.png`.
- Candidate `f1fa4eb86233a8f8d8e0f0b2ad240d414f5f3f9a0fec3fc086fed445596190a3`: BLOCKED, visits=1, nested=0.
  - UNKNOWN_SCREEN; page `UNKNOWN`; captures `20261024-063101-955760Z-bxh-shop.png`.
- Candidate `f54f86cb094f179c3ecb1a9dc11362eba0c6a41e6d1a3a8e549ded26988454a2`: BLOCKED, visits=0, nested=0.
  - GLOBAL_TRAVERSAL_BLOCKER; page `—`; captures .
- Candidate `8ef6d1b604d8b0282dc5463cc412956bc962d3b2b6e370ed38d1b5815f36ede5`: BLOCKED, visits=0, nested=0.
  - GLOBAL_TRAVERSAL_BLOCKER; page `—`; captures .
- Candidate `83f9053965eb6a0cec5ce6d3b17475f9f0381b37faa03fbbffdc8a64d52f04f8`: BLOCKED, visits=0, nested=0.
  - GLOBAL_TRAVERSAL_BLOCKER; page `—`; captures .

### Index 8 / soup

| Reward | Actual result | Journal / claim | Dispatched this run | Error / reason |
|---|---|---|---|---|
| idle-reward | BLOCKED | HISTORICAL_ACTION_LOCKED | False | AMBIGUOUS: historical Idle disk association remains locked. |
| vip-upper-gift | BLOCKED | NONE | False | SafetyError: Initial recovery blocked: ADB_ERROR |
| vip-daily | SAFETY_BLOCKED | NONE | False | SafetyError: Initial recovery blocked: ADB_ERROR |
| ranking-chest | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| shop-daily-gift | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| shop-weekly-card-gift | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| shop-permanent-privilege-gift | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| shop-monthly-privilege-gift | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| guild-relic | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| guild-gifts-loot | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| guild-gifts-member | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| guild-technology | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| mail-war | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| mail-guild | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| mail-system | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| mail-reports | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| mail-collection | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| dynamic-event-exploration | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |

Cleanup: SUCCESS; selection restored: True.

Recovery **ADB_ERROR**: LDPlayer xác định ADB emulator-5570 cho #8, nhưng target không sẵn sàng; stage=TARGET_TRANSPORT_UNAVAILABLE; indexed_boot=False; transports={'emulator-5570': 'ABSENT'}

Source: `C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\recovery\8-0f7d564e5a532e36678c10a8b046b369c2287219d542880ff30ee375e76b2266\20261024-061442-615337Z\report.json`.

### Index 9 / Mini Queen

| Reward | Actual result | Journal / claim | Dispatched this run | Error / reason |
|---|---|---|---|---|
| idle-reward | BLOCKED | ORIGINAL_EMPTY_PROOF_MISSING | False | Original empty accumulation panel and durable identity are not proven. |
| vip-upper-gift | SUCCESS | VERIFIED/910 | True | — |
| vip-daily | SUCCESS | VERIFIED/912 | True | — |
| ranking-chest | SUCCESS | VERIFIED/914 | True | — |
| shop-daily-gift | SUCCESS | VERIFIED/916 | True | — |
| shop-weekly-card-gift | SUCCESS | VERIFIED/917 | True | — |
| shop-permanent-privilege-gift | SUCCESS | VERIFIED/918 | True | — |
| shop-monthly-privilege-gift | SUCCESS | NONE | True | — |
| shop-monthly-quick-collect (independent child) | SUCCESS | VERIFIED/919 | True | — |
| shop-monthly-daily (independent child) | SUCCESS | VERIFIED/920 | True | — |
| guild-relic | ALREADY_ATTEMPTED | RESERVED/866 | False | — |
| guild-gifts-loot | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED | False | — |
| guild-gifts-member | NOT_AVAILABLE | NONE | False | — |
| guild-technology | RESOURCE_NOT_AUTHORIZED | NONE | False | — |
| mail-war | NOT_AVAILABLE | NONE | False | — |
| mail-guild | JOURNAL_PROOF_REVIEW_REQUIRED | VERIFIED | False | — |
| mail-system | ALREADY_ATTEMPTED | RESERVED/455 | False | — |
| mail-reports | SUCCESS | VERIFIED/924 | True | — |
| mail-collection | NOT_AVAILABLE | NONE | False | — |
| dynamic-event-exploration | BLOCKED | NONE | False | — |

Cleanup: SUCCESS; selection restored: True.

Event candidates: 8; rewards dispatched: 1; scan COMPLETE.

- Candidate `51c0d7f0008219ca9efc2c2f89250d4b78d8061b71e09b6be5f3a8dbd682ad6d`: BLOCKED, visits=1, nested=1.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event:ac8b25cd7e4add55fae097944d640edd62ad672583abc9c43eca82fe475de884`; captures `20261024-062904-959761Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event:ac8b25cd7e4add55fae097944d640edd62ad672583abc9c43eca82fe475de884`; captures `20261024-062904-959761Z-bxh-shop.png`.
  - UNRESOLVED_SAVED_REWARD_IDENTITY; page `event:event:personal-tasks`; captures `20261024-062916-338566Z-bxh-shop.png`, `20261024-062945-318312Z-bxh-shop.png`.
  - ALREADY_ATTEMPTED; page `event:event:personal-tasks`; captures `20261024-062916-338566Z-bxh-shop.png`.
  - COMPLETED_MISSION_NOT_COLLECTED; page `event:event:personal-tasks`; captures `20261024-062916-338566Z-bxh-shop.png`.
  - MISSION_LIST_END_UNPROVEN; page `event:event:personal-tasks`; captures `20261024-062916-338566Z-bxh-shop.png`.
- Candidate `1feab67072e9bae8572546e68fb3b7e8297317b535a400c7fd55f883a6bf5f03`: BLOCKED, visits=1, nested=2.
  - UNEXPECTED_EVENT_EXIT_UNRESOLVED; page `home`; captures `20261024-063038-795557Z-bxh-shop.png`.
- Candidate `210d67f53367ba9f1bfda28e4a10fcf30e54e5c5148006ada6b39128d1654d31`: BLOCKED, visits=1, nested=2.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:thdbng:0e6186a66dfa0cde8881bb444bf6edf51d7787b0f005ed325ffb0d0da599eed9`; captures `20261024-063051-003947Z-bxh-shop.png`, `20261024-063112-777163Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:thdbng:0e6186a66dfa0cde8881bb444bf6edf51d7787b0f005ed325ffb0d0da599eed9`; captures `20261024-063051-003947Z-bxh-shop.png`, `20261024-063112-777163Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:thdbng:e7ac19ad20ae18c7d139f9137e9c8367f3e4b79fa4d3886ad095a908acac5977`; captures `20261024-063059-727053Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:thdbng:e7ac19ad20ae18c7d139f9137e9c8367f3e4b79fa4d3886ad095a908acac5977`; captures `20261024-063059-727053Z-bxh-shop.png`.
- Candidate `7e261b61c86d5e43b38357789e86d69f2996cfe06a0e7ab0b8fd5f6625f3fe3f`: BLOCKED, visits=1, nested=0.
  - UNKNOWN_SCREEN; page `UNKNOWN`; captures `20261024-063130-609102Z-bxh-shop.png`.
  - PRIOR_ROOT_REACQUISITION_FAILED; page `home`; captures `20261024-063319-712107Z-bxh-shop.png`.
- Candidate `68e90ebfb359ec915cfbcfeb1ec85507afcaf6a2d7f18ed24f00d766ed15686d`: BLOCKED, visits=1, nested=0.
  - EVENT_REACQUISITION_FAILED; page `home`; captures `20261024-063157-076772Z-bxh-shop.png`.
  - PRIOR_ROOT_REACQUISITION_FAILED; page `home`; captures `20261024-063211-752890Z-bxh-shop.png`.
- Candidate `0d73d04beefe0fc3a4f426d9722ce78103d7c56c2dfd6ad8decea48668ddafe5`: BLOCKED, visits=1, nested=4.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event gia tri:c96ec35d7495c9b98d54f75de88594286103fee43c2e75f2b55072a0cacdd82f`; captures `20261024-063221-042310Z-bxh-shop.png`, `20261024-063238-587620Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event gia tri:c96ec35d7495c9b98d54f75de88594286103fee43c2e75f2b55072a0cacdd82f`; captures `20261024-063221-042310Z-bxh-shop.png`, `20261024-063238-587620Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event gia tri:aac8e2521c99f76a6bb42ae9b0171e8b8f2bc1f5aa9de2e74a188151866fc987`; captures `20261024-063230-233457Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event gia tri:aac8e2521c99f76a6bb42ae9b0171e8b8f2bc1f5aa9de2e74a188151866fc987`; captures `20261024-063230-233457Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event gia tri:85ea578c4dcf6516ae95328d4ce60fc112120b799249a3009203445bd0c7e0af`; captures `20261024-063247-501976Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event gia tri:85ea578c4dcf6516ae95328d4ce60fc112120b799249a3009203445bd0c7e0af`; captures `20261024-063247-501976Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event gia tri:d677c42110e6fe5c5a6628e52feb583b1b2c438bc3507e3ca116f2eb246acbe2`; captures `20261024-063255-210010Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event gia tri:d677c42110e6fe5c5a6628e52feb583b1b2c438bc3507e3ca116f2eb246acbe2`; captures `20261024-063255-210010Z-bxh-shop.png`.
- Candidate `9f57cfce8be97cabcfac201aa08f7e105f2b86437b3b6fa6cf312ee0fe672843`: BLOCKED, visits=0, nested=0.
  - PRIOR_ROOT_REACQUISITION_FAILED; page `home`; captures `20261024-063303-841339Z-bxh-shop.png`.
- Candidate `24528874d1b70c5dfe103d8ec4b402e7875444ac7a902d7f6aa89be66e2b54fe`: BLOCKED, visits=1, nested=0.
  - EVENT_REACQUISITION_FAILED; page `home`; captures `20261024-063303-841339Z-bxh-shop.png`.

### Index 10 / HiHi

| Reward | Actual result | Journal / claim | Dispatched this run | Error / reason |
|---|---|---|---|---|
| idle-reward | BLOCKED | HISTORICAL_ACTION_LOCKED | False | AMBIGUOUS: historical Idle disk association remains locked. |
| vip-upper-gift | NOT_AVAILABLE | NONE | False | — |
| vip-daily | SUCCESS | VERIFIED/925 | True | — |
| ranking-chest | NOT_AVAILABLE | NONE | False | — |
| shop-daily-gift | NOT_AVAILABLE | NONE | False | — |
| shop-weekly-card-gift | NOT_AVAILABLE | NONE | False | — |
| shop-permanent-privilege-gift | NOT_AVAILABLE | NONE | False | — |
| shop-monthly-privilege-gift | BLOCKED | NONE | False | — |
| shop-monthly-quick-collect (independent child) | NOT_AVAILABLE | NONE/— | False | — |
| shop-monthly-daily (independent child) | UNKNOWN | NONE/— | False | — |
| guild-relic | NOT_AVAILABLE | NONE | False | — |
| guild-gifts-loot | NOT_AVAILABLE | NONE | False | — |
| guild-gifts-member | SUCCESS | VERIFIED/926 | True | — |
| guild-technology | ALREADY_ATTEMPTED | RESERVED/732 | False | — |
| mail-war | NOT_AVAILABLE | NONE | False | — |
| mail-guild | NOT_AVAILABLE | NONE | False | — |
| mail-system | ALREADY_ATTEMPTED | RESERVED/270 | False | — |
| mail-reports | NOT_AVAILABLE | NONE | False | — |
| mail-collection | NOT_AVAILABLE | NONE | False | — |
| dynamic-event-exploration | BLOCKED | NONE | False | — |

Cleanup: SUCCESS; selection restored: True.

Event candidates: 3; rewards dispatched: 0; scan COMPLETE.

- Candidate `51c0d7f0008219ca9efc2c2f89250d4b78d8061b71e09b6be5f3a8dbd682ad6d`: BLOCKED, visits=1, nested=0.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event:ac8b25cd7e4add55fae097944d640edd62ad672583abc9c43eca82fe475de884`; captures `20261024-064036-095367Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event:ac8b25cd7e4add55fae097944d640edd62ad672583abc9c43eca82fe475de884`; captures `20261024-064036-095367Z-bxh-shop.png`.
- Candidate `87bb11ab5085cf21d3f9f04c712e5480948e120fe1b800fcf04bad0303719fe1`: BLOCKED, visits=1, nested=1.
  - NAVIGATION_REJECTED_BEFORE_INPUT; page `event:trin chien chqng v?ng:a8843c883fb2343e31ccc6ed355da321c4cce4ce68c4d3eaf60571cdefd3ebbe`; captures `20261024-064050-866927Z-bxh-shop.png`.
- Candidate `2d403e0b41e8ef017d965ee523dcb82a2710eee2933ebf82ae7d430a9a2f85af`: BLOCKED, visits=1, nested=2.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event gia tri:c96ec35d7495c9b98d54f75de88594286103fee43c2e75f2b55072a0cacdd82f`; captures `20261024-064128-363284Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event gia tri:c96ec35d7495c9b98d54f75de88594286103fee43c2e75f2b55072a0cacdd82f`; captures `20261024-064128-363284Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event gia tri:aac8e2521c99f76a6bb42ae9b0171e8b8f2bc1f5aa9de2e74a188151866fc987`; captures `20261024-064137-652301Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event gia tri:aac8e2521c99f76a6bb42ae9b0171e8b8f2bc1f5aa9de2e74a188151866fc987`; captures `20261024-064137-652301Z-bxh-shop.png`.
  - EVENT_CONTENT_REQUIRES_QUALIFICATION; page `event:event gia tri:d677c42110e6fe5c5a6628e52feb583b1b2c438bc3507e3ca116f2eb246acbe2`; captures `20261024-064144-501128Z-bxh-shop.png`.
  - UNQUALIFIED_CONTENT; page `event:event gia tri:d677c42110e6fe5c5a6628e52feb583b1b2c438bc3507e3ca116f2eb246acbe2`; captures `20261024-064144-501128Z-bxh-shop.png`.

### Index 11 / Smile

| Reward | Actual result | Journal / claim | Dispatched this run | Error / reason |
|---|---|---|---|---|
| idle-reward | BLOCKED | HISTORICAL_ACTION_LOCKED | False | AMBIGUOUS: historical Idle disk association remains locked. |
| vip-upper-gift | BLOCKED | NONE | False | SafetyError: Initial recovery blocked: ADB_ERROR |
| vip-daily | SAFETY_BLOCKED | NONE | False | SafetyError: Initial recovery blocked: ADB_ERROR |
| ranking-chest | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| shop-daily-gift | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| shop-weekly-card-gift | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| shop-permanent-privilege-gift | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| shop-monthly-privilege-gift | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| guild-relic | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| guild-gifts-loot | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| guild-gifts-member | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| guild-technology | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| mail-war | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| mail-guild | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| mail-system | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| mail-reports | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| mail-collection | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |
| dynamic-event-exploration | NOT_RUN_TARGET_BLOCKED | NONE | False | ADB_ERROR |

Cleanup: SUCCESS; selection restored: True.

Recovery **ADB_ERROR**: LDPlayer xác định ADB emulator-5576 cho #11, nhưng target không sẵn sàng; stage=TARGET_TRANSPORT_UNAVAILABLE; indexed_boot=False; transports={'emulator-5576': 'ABSENT'}

Source: `C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\recovery\11-581931b1a11a623da1f7b29bdf132f3399e00636bb1252e663a4b678d7b319dd\20261024-063329-203174Z\report.json`.

## Confirmed causes and changes

1. **VIP daily 883/885:** receipt followed by a clean VIP screen and disabled clock (20:02:43 /20:01:44), yet immediate postcondition UNKNOWN. Exact Windows OCR reproduction: 2x returns empty, 3x reads the clock. A bounded alternate rendering of all identical glyphs with additional white padding must agree exactly. Conflicting/nonempty invalid reads remain UNKNOWN; page, disabled rectangle, absent claim controls and unique matching requirements remain. Existing 883/885 stay POSSIBLE: this task does not retrospectively rewrite their journals.
2. **Monthly daily index10:** exact compact “Đã Nhận” label is visible beside VND renewal, with owned daily row/checks, while old received template scores .759657. Add a small reusable .995 label variant, associated with selected Monthly page, independent daily heading, Back and absent free claim control. Duplicate/conflicting labels fail closed. Paid renewal never grants action permission. Actual run result remains BLOCKED; offline reclassification is not a new runtime success.
3. **Event scroll rejection:** index2/5 task-grid held rows retain completed-fraction/free-label proof but old POSSIBLE/caption ambiguity denies their claim. Fresh navigation rejected the qualified card-disjoint gutter solely because journal blockers were present; index9 also reports navigation rejection. Permit only navigation with independently qualified current scroll geometry, same current identity, no popup, all visible green actions accounted for, and ONLY known held-reward blockers. Unreadable/omitted card, ambiguous task caption, unknown label, extra blocker, page/runtime change still deny. Rows remain UNKNOWN and claim eligibility is unchanged. Full bounded traversal/coverage remains required.
4. **Repeated initial tabs:** index2 Equipment Trials first selected tab (capture061211), second tab061221, same first tab061236. The explorer remembered only clicked tabs, not the already inspected initial highlighted tab. Record current qualified selected-tab regions as local denial-only visit evidence; suppress re-opening that inspected slot. No reward/journal identity uses coordinates. Independent tabs, event roots and nested scopes remain independent. All content blockers remain visible.
5. **Repeated static metadata I/O:** offline profiling of the ORIGINAL Run20 personal-task frame observed86 JSON reads and118 opens in one recovery classification; recurring helper calls reload unchanged anchor metadata. Cache only immutable metadata keyed by the complete current JSON file set + fresh mtime/size; additions/removals/changes invalidate it, malformed changes fail. All screenshots, actual matches, competing states, thresholds and fresh ADB/session safety checks still run. Offline timings do not establish faster real runtime.
6. **Launch evidence gap:** index3 shows ANDROID_HOME twice, one launch, verified emulator-5560/boot and no observed loading. Exact application/package-launch failure cause cannot be established because package-launch stdout was discarded; the correlated app log does confirm one launch and unchanged Android Home. Persist the existing one-shot launch transport result/error and elapsed time into its recovery report. No relaunch/retry, guessed activity or increased timeout. Transport success never proves Home.

## Remaining blockers — no invented fixes or unlocks

- Index8 emulator-5570 and index11 emulator-5576: nine bounded resolver samples each show exact serial ABSENT plus no indexed boot despite Android-ready inventory. No screenshots could be captured. Transport/config cause is not proven by this evidence; no ADB restart/config write/timeout increase.
- Historical Idle locks: indexes2/5/8/10/11 historical disk association;3/9 original empty accumulation proof missing. Index4 had an unverified boot read before Idle action; later Home does not retroactively prove that read. No safe new accumulation/journal identity evidence means no unlock.
- Guild old VERIFIED batches with invalid original causal proof remain JOURNAL_PROOF_REVIEW_REQUIRED; old POSSIBLE Relic/Mail/Technology remain held. Donation current cost is STONE (not authorized) on2/4/5/9: no WOOD-only rule bypass.
- Event personal-task and grid green Nhận controls were seen but uncertain saved identities remain locked. This repair improves independent traversal, not claim permission. No Event claim was dispatched in Run20.
- Equipment-resource tasks, Guild trial store purchases, Wishing Box, castle-skin VND bundles, dart/event passes and collaboration artwork retain unsupported content/entitlement blockers. Green “Nhận Nhanh” on a pass is not proven genuinely free by this evidence alone. Collaboration pages and paid modals need separate qualified contracts; no blind taps or broad new-feature work.
- Home notification geometry ambiguity, changed/vanished root reacquisition, unexpected Event exits and unvisited candidates remain explicitly blocked in the inventory above. They are not converted to exhausted/NOT_AVAILABLE.
- Package-launch stdout was omitted from both the Run20 general log and recovery report. Added one-shot launch evidence addresses this specific diagnostic gap without treating transport return as successful navigation. General app logging itself is present; no logging redesign is justified.

## Validation and delivery contract

- Local targeted regression: **179 passed in72.12s**, plus185 recovery/Shop/vision/reconciliation regressions passed in238.06s across Run20, dynamic Event traversal, VIP countdown/fleet/visual profiles, Run19 guards and Event geometry. Ruff affected files PASS; diff whitespace check PASS. Full lint/pytest/portable build/GUI smoke/artifact upload in fresh GitHub Actions.
- First full gate40085034225:2153 passed,26 skipped,2 failed. Both failures were existing negative scroll tests with deliberately incomplete port objects: the new blocker helper accessed missing rows instead of returning a fail-closed rejection. Narrow fix uses empty evidence when rows are absent; existing SafetyError/no-input expectations are preserved. Exact failing suites + Run20 + traversal: **125 passed in20.13s**; Ruff PASS. Require a fresh full gate before Desktop delivery.
- Self-review: no journal writes, eligibility reset, claim retry, global timeout increase, account-coordinate routing, identity fallback, Protected mutation, lifecycle command or new phase.
- Qualify/upload only the saved game UI fixtures and compact received-label runtime asset. They contain game UI only, no credentials or unrelated private files.
- Replace Desktop app only after exact-commit CI passes; verify artifact/run/commit/hashes and retain no more than two verified portable versions. Preserve all diagnostics and journals.
- No gameplay was run for this repair. USER performs the next normal application Start. Phase8 remains PARTIAL; Phase9 not started.
