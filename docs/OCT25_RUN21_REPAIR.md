# October25 normal application run21 — diagnosis and repair

## Evidence (read, not inferred)

- Run **21**, origin `normal-ui-start`, two workers, eight frozen targets (2,3,4,5,8,9,10,11).
- 2026-10-25 09:27:06–10:15:21 UTC (16:27–17:15 Vietnam). Result **PARTIAL**.
- Executable `C:\Users\ADMIN\Desktop\app\TopHeroesAutoManager\TopHeroesAutoManager.exe`,
  commit `8c89e9a4485cf984c96721ef182aadf3e39b099f`, CI `40088053262`,
  SHA256 `592f285a64570abae3171409f2fc1962e85d417d052f1ee37f5f7ab339223b27`.
- Report root: `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\tasks\automation\20261025-092706-217684Z-de1b2b62\`
  (`fleet-report.json` plus `<index>/account-report.json`, flow reports, 654 screenshots).
- `logs/app.log`: 697 lines tagged `run=21` (16:27:06–17:15:21 VN). Protected state/flags unchanged,
  names unchanged, 0 LDPlayer name-write attempts, all selections restored.
- Journal was only READ through a copy; no production journal row was changed by this repair.

| Index | Label | Worker s | Startup/Home s | New claims | Outcome |
|---|---|---:|---:|---:|---|
| 2 | Emmmm | 1020.7 | 151.1 | 12 | PARTIAL |
| 3 | Queen con | 1053.1 | 109.8 | 12 | PARTIAL |
| 4 | 3-Chíp | 975.8 | 95.3 | 13 | PARTIAL |
| 5 | 4-Em Pé | 1044.2 | 137.3 | 13 | PARTIAL |
| 8 | soup | 59.0 | 54.7 | 0 | **target blocked (ADB transport ABSENT)** |
| 9 | Mini Queen | 88.9 | 83.1 | 0 | **target blocked (one screencap timeout)** |
| 10 | HiHi | 791.6 | 106.7 | 13 | PARTIAL |
| 11 | Smile | 56.9 | 52.2 | 0 | **target blocked (ADB transport ABSENT)** |

Every dispatched claim that was not an aggregate parent has a VERIFIED journal row; there is no
dispatched-without-post-condition claim in run21. Aggregate Monthly parents carry journal NONE by design
(their independent children carry VERIFIED).

## Defects and root causes

### D1 — #9 whole target blocked by one read-only screencap timeout (FIXED)
- Evidence: `app.log` 17:02:50 `adb -s emulator-5572 exec-out screencap -p` timed out after 20s while the
  game was in `GAME_LOADING`; `capture_verified` re-raised, Recovery returned `ADB_ERROR`, VIP/idle blocked and
  every later flow became `NOT_RUN_TARGET_BLOCKED` (≈ 16 flows lost). #10 loaded for ~70s with 2 workers and succeeded.
- Root cause: `Manager.capture_verified` ([service.py](../src/top_heroes_auto/app/service.py)) made exactly one
  screencap attempt; a read-only command failure was terminal for the account.
- Fix: `Manager._capture_png` retries a `CommandError` once (`CAPTURE_ATTEMPTS=2`). Before the retry it checks Stop,
  waits, re-verifies the SAME runtime (pid/vbox/stable id/selection/protection) and the transport boot id. Any
  change fails closed; no input or lifecycle command exists on this path.

### D2 — #8 and #11 blocked: indexed ADB transport "ABSENT" for the whole 34s window (FIXED, window only)
- Evidence: recovery report `…/recovery/8-0f7d…/20261025-100029-176872Z/report.json`: nine samples 3–34s, all
  `transports={'emulator-5570': 'ABSENT'}`, `indexed_boot_available=false`; Android was reported started.
  Same signature in run20 (8/11 at ~53s startup). Historical fleet reports show the same two instances resolving
  successfully on other runs with startup 114–149s, i.e. registration is slow, not absent.
- Root cause: `ADB_RESOLVE_TIMEOUT = 30s` was shorter than the real cold registration time seen in other runs.
- Fix: window raised to 90s on the SAME unchanged runtime. `_resolve` now also honours user Stop on every poll.
  Still no ADB restart, no `connect` beyond the serial LDPlayer itself reported, no lifecycle retry.
- Not proven: whether #8/#11 will register inside 90s on the next run. The reports contain no sample after 34s.
  If they still fail, the next evidence to collect is a >90s sample series, not a larger blind timeout.

### D3 — Events: rewards visibly available but skipped (NOT FIXED; needs a user/live decision)
- Treasure Hunt personal-task page on #2, #4, #5: three green "Nhận" rows were visible (screenshot
  `2/events/20261025-094230-586545Z-bxh-shop.png`) but blocked `UNRESOLVED_SAVED_REWARD_IDENTITY` +
  `COMPLETED_MISSION_NOT_COLLECTED`.
- Root cause (journal read): old **POSSIBLE** event claims remain unresolved — #2 ids 429/533/596, #5 ids
  241/243/244/311/367 (Oct 9–16). `bind_saved_rewards` ([event_claim_reconciliation.py](../src/top_heroes_auto/app/event_claim_reconciliation.py))
  marks any AVAILABLE row UNKNOWN when a POSSIBLE claim exists and the row caption cannot be uniquely tied to
  a known sibling. That is the intended "never retry an ambiguous claim" lock; the three visible rows cannot be
  distinguished from the ambiguous earlier claim without new original-action evidence.
- No threshold was lowered and no locked claim was reconciled. Options (user decision): keep locks, or authorise a
  live evidence session that observes the original cards before/after a claim for these POSSIBLE ids.

### D4 — Home badges with unqualified geometry (NOT FIXED; needs more real evidence)
- Two candidates per account (`UNQUALIFIED_NOTIFICATION_GEOMETRY`), visible on `2/events/…094221-866534Z-bxh-shop.png`:
  a small numberless red dot on the timed chest icon (rim .59, no unique white-outlined icon owner) and a red gift
  ribbon (rim .056, decorative). The ribbon is correctly rejected; the chest dot is a real badge whose icon shape
  `discover_events` does not model. A calibrated rule needs several clean captures of that chest across accounts.

### D5 — #5 Monthly upper "quick collect" BLOCKED (NOT FIXED)
- `monthly-gift` entry is not matched; the screenshot shows its disabled (forbidden-ad) variant. The independent
  daily row was claimed and VERIFIED (claim 966). Treating an unknown entry state as exhausted would hide work, so
  it stays BLOCKED until the disabled-variant meaning is proven.

### D6 — Measured time (analysis only; no guard weakened)
- #2 (1020s): recovery recognition 227s/107 calls (2.1s each), other detection 242s/79 calls (3.1s), inventory
  `list2` 157s/720 calls (0.22s), identity commands 132s/609 calls, OCR 54s/85 calls (251 cache hits), capture 77s/110,
  deliberate waits 71s/44.
- Offline profile of `RecoveryScreenDetector.detect` on a real Home frame: 0.97s, 14 unique anchors, **no duplicated
  anchor search** in one detect (28 `matchTemplate` calls = 0.85s). There is therefore no equivalence-preserving
  memoisation win in a single frame; remaining cost is template search with 2 workers contending for CPU. Reducing
  it needs a verified coarse pre-filter, which was not attempted without live regression frames.
- Inventory/identity query volume is the per-action guard (`_check`, `_same_runtime`, boot reads) and is retained.

## Regression tests

`tests/test_run21_repairs.py` (10 tests; all 10 fail on the pre-fix `service.py`):
single screencap timeout retries the same verified target; persistent failure bounded at two attempts; pid / disk /
selection / boot change between attempts fails closed after exactly one screencap; Stop during retry prevents the
second capture; transport registration at ~55s now resolves; Stop interrupts the transport wait without lifecycle
or `connect`; default window ≥ 90s.

## Preserved

All VERIFIED and POSSIBLE journal rows, Protected Queen, names, selections, external running instances. No
gameplay, no LDPlayer start/stop, no ADB device command was issued during this repair.
