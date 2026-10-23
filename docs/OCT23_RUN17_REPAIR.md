# Run17 diagnosis and offline repair — October 23

## Exact independently started application run

- DB run **17**, origin `normal-ui-start`, two workers, all selected non-Protected
  indexes 2/3/4/5/8/9/10/11. No new gameplay run is authorized in this repair.
- Build `6927a8471fd9aaaecfd273710357a0973ae9a15d`, CI `39586666118`, standalone
  `C:\Users\ADMIN\Desktop\app\TopHeroesAutoManager\TopHeroesAutoManager.exe`.
  Recorded EXE SHA256 `ee18f66af6459f4855e1d6356ce4c9559aa0847a7d360772901a1d5adaff5383`.
- UTC 2026-10-22 08:40:37–09:49:26 (15:40–16:49 Vietnam), PARTIAL; DB aggregate
  FAILED means incomplete accounts, not zero rewards. Latest DB run is17.
- Authoritative report under `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\tasks\automation\`
  `20261022-084037-045516Z-5e12db49\fleet-report.json` (base directory below).
- The requested `logs/app.log` and `.1` end on October18 and do NOT describe this
  run. Attribution is independently corroborated by DB run/account timestamps,
  report origin/build/hash, indexed runtime records and screenshot timestamps.
- Report shows Protected unchanged, selections restored, no name writes; all
  eight owned cleanups SUCCESS. This investigation invokes no LDPlayer or ADB.

## Actual coverage and results

| Index | Active seconds | Actual coverage / limitation |
| --- | ---: | --- |
| 2 | 1469.674 | All seven flows evaluated; Idle/history, relic487, Guild proof holds, System425 locked; Events incomplete |
| 3 | 1032.026 | VIP/BXH/relic verified; all four Shop routes inspected; Mail ticker incorrectly dismissed; rank notice blocked Events |
| 4 | 1254.575 | All seven flows evaluated; Monthly upper and lower verified; System9 unread badge ambiguous; Events incomplete |
| 5 | 1287.100 | All seven flows evaluated; supported Shop routes processed; historical locks and Event content blockers remain |
| 8 | 1374.682 | All seven flows evaluated; Event802 dispatched once, receipt unrecognized, POSSIBLE retained |
| 9 | 57.787 | Explicit emulator-5572 verified; launch_game left Android Home unchanged at0/20s; downstream target-blocked |
| 10 | 1308.726 | All seven flows evaluated; Monthly upper/lower verified; WOOD732 remains locked; Event roots incomplete |
| 11 | 58.780 | Android ready; exact emulator-5576 ABSENT/indexed boot unavailable through33.344s; ADB_ERROR, no game input |

New journal IDs749–805: **56 VERIFIED, one RESERVED/POSSIBLE802**. Of the verified
operations, **46 are reward claims**, ten are Mail read batches. No contribution
or mission-send journal was added in this user run. A receipt alone does not
verify802. No historical POSSIBLE is reopened by this repair.

## Confirmed defects and focused fixes

All rows refer to **run17** and paths relative to the report base directory.

| Index | Feature / original evidence | Confirmed cause | Fix | Regression |
| --- | --- | --- | --- | --- |
| 3 | Mail `3/mail/20261022-085517-989823Z-guild-mail.png`, evidence JSON, actions.json | World ticker covers tab labels; sharp Mail title/close/read/delete remain. HOME_OVERLAY fallback sent bottom-left, then siblings failed `Feature already entered` | Qualified Mail modal suppresses generic dismissal while tabs are obscured. Bounded fresh captures, still UNKNOWN/no input until full tab evidence returns; no re-entry bypass | Original ticker fixture; capture-only transition; persistent ticker bounded/no input |
| 4 | Mail `4/mail/20261022-091348-795245Z-guild-mail.png` | System badge **9** present but Windows two-render OCR omitted it; no qualified9 glyph in assets | Strict full-badge9 glyph fallback using existing association/uniqueness checks; OCR disagreement still rejects. Reports42 remains UNKNOWN when unqualified | Original9 at two positions; conflicting OCR cannot use fallback |
| 8 | Tầm Bảo `8/events/20261022-093736-923550Z-bxh-shop.png`, actions.json, postframes093745/093751/093755 | Exactly one collection802, then a report receipt remains UNKNOWN. Default title score.267, but the existing large title qualifies; its continuation raw score.956 fails over the changed blurred background. No dismissal/post-state images; journal remains POSSIBLE | Reuse the existing large title and strict continuation glyph-detail matcher (.988>=.98), preserving duplicate and relative-layout guards. Future claims still need independent underlying state change; never retry802 | Original receipt; partial/reversed anchors rejected; receipt-only postcondition remains unverified/no repeat; old large/report receipt and removal-effect regressions |
| 3 | Events `3/events/` UNKNOWN frame retained in fixture `rank-notice.png` | Informational `Xin Chúc Mừng` guild rank notice not recognized, blocking remaining roots | Three stable title/body/blank-dismiss anchors plus layout qualify bottom-left as EVENT_PROMO, explicitly NOT REWARD_RECEIPT | Actual notice; missing anchor rejects; never receipt |
| 2/4/5/8/10 | Collaboration root, e.g. `2/events/20261022-090434-356222Z-bxh-shop.png` | Existing preview/training/collection glyph scores .994859/.963236/.994077 below unchanged .995; hub became UNKNOWN | Three small clean caption raster variants, same global search/strict threshold and cross-variant uniqueness; only currently indicated children | Original current hub detects treasure/training-rewards; duplicate/missing labels reject; previous hub tests retained |
| 2/3/4/5/8/10 | Guild/Mail repeated captures; open_reward returns a qualified fresh frame, process immediately captured again without intervening input | Redundant capture, target scans and detector passes | Pass the exact unconsumed navigation frame once to opportunity; stale/consumed frame rejected. Every input still verifies identity, every post-action observation is fresh | Navigation-frame reuse/consumption, no extra capture, stale frame rejection, existing uncertain-journal tests |

The collaboration frame is the `UNKNOWN_SCREEN` record for index2 in the original
fleet report, also preserved in local `artifacts/oct23-evidence-index.json`.
The complete fixture is `tests/fixtures/run17/collaboration-hub.png`.

## Correct exclusions versus unproven work

- Technology current resource is STONE on every account that reached donation,
  score approximately.99828. No WOOD control was available in this run; sending
  zero contributions is correct. Ordinary/quick proof guards remain unchanged.
  Existing600/732 uncertainty also blocks those actions independently.
- Idle historical identity/empty-accumulation evidence remains unproven. No date,
  new screenshot, or new run releases those locks. Journal138 exception stays locked.
- All six reached accounts inspected daily/weekly/permanent/monthly supported Shop
  routes. Monthly children independently record upper/lower outcomes, including
  successful lower claims759/770/779/800. Group `journal:NONE` is an aggregate,
  not evidence that children were omitted; inspect `children` rather than inventing
  a missing reward. Actual unavailable3/8 do not authorize extra taps.
- Tầm Bảo completed rows coexist with Gửi Nhanh. Collection and dispatch remain
  separately typed. Historical identity/occurrence uncertainty blocks collection
  on2/4/5/10; unresolved completed rewards prohibit dispatch. Existing production
  collect-before-send and uncertain-send tests remain required. No new period is
  invented and no historical claim is reclassified.
- Book completed fraction + green Nhận still does not prove free entitlement;
  original paid reminder evidence remains authoritative. No threshold lowering.
- Notification geometry, unqualified Event content, nested leaves and mission
  scroll-end evidence remain real blockers. Discovering a red dot does not prove
  a free reward or exhausted coverage. Improved hub navigation is NOT blanket
  authorization for its children or proof those rewards exist.
- Index9 launch failure and11 transport failure are confirmed, but the saved
  evidence does not establish a safe launch retry/config repair. No config change,
  emulator trial, restart, timeout increase or guessing is performed.

## Measured cost and bounded optimization

On six feature-reaching accounts, per-account exclusive inventory cost is roughly
201–267s; recovery recognition206–313s; feature detection268–374s. Deliberate waits
are only55–67s. Do not sum inclusive and exclusive nested metrics.
The single current-frame handoff removes one capture/detection sequence per
Guild/Mail reward opening, with no intervening input, and avoids redundant target
scans associated with it. Immutable reference masks may be cached; runtime pixels,
availability, permissions and target identities are never cached by this change.
This structural improvement is tested; no end-to-end speedup is claimed without
another user run. Global timeouts, safety thresholds and Stop bounds are unchanged.

## Validation and delivery contract

Run only targeted local tests, Ruff and diff checks; full lint/pytest/portable
Windows/smoke/artifact upload belong to CI. Five new fixtures and small anchors
contain game UI only, no credentials/tokens/cookies/unrelated private files.
Local diagnosis summary: `artifacts/oct23-run17-summary.json`; immutable read-only
task-start journal snapshot: `artifacts/oct23-journal-baseline.json`.
Final CI/provenance/Desktop hash manifest will be recorded in local artifacts.
Keep at most two verified local caches and only the latest Desktop app. Preserve
all diagnostics, journals and unrelated files. Do not Start the delivered app.

Targeted related suite: **331 passed in722.22s**; Ruff all and diff check PASS.
The first local batch had a new test's incorrect geometry-call arguments and
an existing import-order-sensitive registry assertion; the corrected targeted
suite uses the production registry's ordinary initialization order. No scheduler
or flow-order production change was made for that test-order artifact.

CI39913333616 exposed7 receipt/removal-effect regressions (2107 passed,26 skipped):
the first added compact receipt group overlapped the existing large group and
could rescue a duplicate large title. It was NOT delivered. Remove those four
overlapping assets and instead reuse the existing large title with the existing
strict continuation glyph-detail matcher, only when the title is unique and the
raw continuation is below threshold (never a duplicate). All81 focused tests for
the failed receipt/removal-effect paths, run17 and overlay dismissal now PASS in
213.51s; Ruff/diff checks PASS. Require a fresh full CI gate for this correction.

**Phase8 remains PARTIAL. No Phase9. No real gameplay/claim in this repair.**
Fresh user-run evidence is still required for the repaired ticker/receipt/hub,
safe independent continuation and actual speed. Missing postframes for802 cannot
be manufactured by rerunning it.
