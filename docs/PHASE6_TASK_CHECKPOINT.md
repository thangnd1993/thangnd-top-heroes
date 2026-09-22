# Phase 6 task ledger — audited 2026-09-22

## Fixed-flow injectable runtime — pending final review/CI

The seven annotated reference files are now present and normalized by filename,
SHA-256, flow and annotation meaning in
`assets/tasks/phase6/reference-manifest.json`. The manifest explicitly sets
`runtime_input=false`; annotated pixels are never templates or cost proof.

A bounded injectable runtime now models the complete VIP, Tiệm and
Avatar→BXH→chest sequences. Every action uses a unique target from a fresh
frame, verifies the next semantic destination, maintains exact account and
ADB/boot continuity, and requires a fresh final postcondition. A concrete
SQLite adapter uses the existing `RESERVED`/`VERIFIED` ledger with
account/reward/proven-cycle scope: reservation commits immediately before the
claim input, while uncertain input/capture/receipt leaves it permanently
non-retryable. Forbidden
evidence blocks only when it intersects the proposed target, so a paid offer
elsewhere on a valid page does not hide a separately proven free control.
Attention-only, missing evidence and stale frames remain `UNKNOWN`; only a
positive unavailable anchor returns `NOT_AVAILABLE`. Action results that throw
are uncertain and never retried. Bounds and persisted attempts stop before
observation/input.

`ranking-chest` is exposed through the Phase 6 task/CLI registry, but all three
packaged fixed flows remain qualification-gated. In particular, Avatar/BXH has
no clean index-2 runtime anchors, and none of the flows has complete independent
zero-cost/availability/postcondition evidence. Packaged execution therefore
returns `NOT_IMPLEMENTED` before recovery or gameplay dispatch. Local focused
gate at this checkpoint: **187 passed, 6 skipped**, changed-file Ruff passed.
No real device action accompanied this offline milestone.

## Fixed-flow safety correction CI — 2026-09-23

Commit `92d451c` adds the versioned semantic manifest for VIP, Tiệm and
Avatar/BXH; packaged reward activation remains fail-closed without qualified
zero-cost, availability and postcondition evidence. The corrected product
rule removes the now-forbidden daily-pack tab/page/route from the production
shop-survey registry. Reviewer final result: **APPROVED** for this gated
offline correction, not for real claim acceptance or Phase 6 completion.

Local focused gate: **145 passed, 6 skipped** (the skipped cases exercise the
superseded historical daily-pack production route); changed-file Ruff passed.
Windows Validation run `35764816940` passed full lint, tests, PyInstaller
build, executable smoke and artifact upload. Fresh executable from that run:
`artifacts/phase6-92d451c-run35764816940/TopHeroesAutoManager-Windows-x64/TopHeroesAutoManager.exe`,
SHA-256 `A080A53D3033B47EBB7EC3A61170D455B1B1CC2E94A6C5854D6A3FC7F86A517F`.

## 2026-09-23 exact index-2 launch — ADB blocked, no gameplay input

After the user explicitly required index 2 to be opened, a fresh elevated
`list2` identified the target exactly as `2 / 5-Emmmmm`, stopped. The manager
metadata still showed `0 / Queen` Protected and unselected, and index 2 not
Protected but unselected. Only the indexed `launch --index 2` command was
sent. A subsequent `list2` showed index 2 running under the expected name.

The explicit indexed ADB channel then resolved to `emulator-5558`, but that
transport was absent; the visible ADB transports belonged to other running
instances and were rejected. Unrelated instance state also changed during the
observation window, so no isolation claim is made and no cleanup was sent to
those instances. Windows visual control failed to initialize, so it was not
used as an unsafe fallback. Index 2 was left open as requested, but there was
**no screenshot, game launch/input, reward tap, claim, rename, or persistent
configuration edit**. Live acceptance remains blocked until the exact index-2
ADB transport is available without violating the current no-config-edit rule.

## Product correction received — fixed daily flows first

The latest user-supplied annotated references change the **current product
priority** to VIP daily free reward, Tiệm daily free reward, and
Avatar/Profile → BXH → top-left chest. Blue marks intended targets, red marks
forbidden paid/other regions (red wins on overlap), and yellow marks navigation
direction. These drawings are product references, **not runtime templates or
proof of zero cost**. Runtime must match clean current-account frames and
verify a fresh postcondition. A red attention marker nominates an inspection
candidate only. The mentioned Desktop files are now present and their hashes
are recorded in the reference manifest. Do not copy/crop their annotated
pixels into clean runtime assets or treat them as claim evidence.

| Corrected flow | Annotated reference | Detector/template | Runtime integration | Targeted tests | Real claim acceptance |
| --- | --- | --- | --- | --- | --- |
| VIP daily free | `CAPTURED_HASHED` | `IMPLEMENTED` for existing index-2 entry/page/free button crops; semantic fixed-flow program added | Injectable sequence `TARGETED_TEST_PASS`; packaged claim stays `NOT_IMPLEMENTED` without independent receipt | Included in 164 focused passes; shifted/scaled, paid overlap, fresh destination/postcondition covered | `PENDING`; no index-2 production claim |
| Tiệm daily free | `CAPTURED_HASHED` | `PARTIAL`: semantic program implemented; clean daily navigation exists, but no proven zero-cost gift control | Injectable sequence `TARGETED_TEST_PASS`; forbidden daily-pack route remains removed; packaged claim fail-closed | Included in 164 focused passes; attention-only, paid-away/overlap and unavailable/unknown covered | `PENDING`; no index-2 gift claim |
| Avatar → BXH → chest | `CAPTURED_HASHED` product intent | Semantic program `IMPLEMENTED`; clean runtime page/target anchors `NOT_STARTED` | Injectable sequence and `ranking-chest` registry `TARGETED_TEST_PASS`; packaged execution `NOT_IMPLEMENTED` before device calls | Route/destination/identity/postcondition/bounds/no-repeat tests pass | `PENDING` |

Do not repeat completed VIP UI discovery or the historical shop run merely
because the product route changed. The new red exclusion restricts **future**
dispatch; it does not erase honest historical run-15 evidence. The fixed-flow
detector should be account-generalizable, while the current **real test
authorization** remains the exact `2 / 5-Emmmmm` record. The name now resolves
correctly again, but its exact indexed ADB transport is unavailable; that is a
stop condition, not a reason to edit persistent configuration, use another
transport, or weaken the guard. Broad speculative exploration is deferred
until the three annotated flows are safely addressed. No Phase 7.

Branch: `codex/phase6-vip-pack-recruit`, pre-audit HEAD `41b747d`; local and
remote HEAD matched and the worktree was clean before this checkpoint edit.
Phase 6 is **not complete**. Only
`2 / 5-Emmmmm` is authorized for future Phase 6 real work; `0 / Queen` is
Protected and `4 / 3-Chíp` is revoked. Historical evidence from index 4 is
preserved, never authority to mutate it or reuse its coordinates on index 2.

State refers to the **named milestone only**, not completion of its parent
reward task. `CI_PASS` does not imply a real claim. `REAL_ACCEPTANCE_PASS` below
is explicitly limited to the stated navigation route.

| Item | Audited state | Completed evidence and real mutations | Exact remaining work |
| --- | --- | --- | --- |
| VIP | `CI_PASS` — observation-only command; reward claim **not done** | Index-2 VIP Home→page→Home screenshots from 2026-09-20 and 2026-09-21 already show daily-free wording, green `Nhận`, and a separate paid offer. Five index-2 VIP templates exist. `41b747d` added a claim-free survey command, 44 focused tests passed, full Windows CI `35678890820` passed. Run 16 attempted an index-2 launch but stopped at identity mismatch before ADB/game screenshots/taps/claim. Historical index-4 manual VIP claim occurred once; do not repeat it. | Do **not** repeat VIP UI survey merely to rediscover the free label. Independent index-2 postclaim receipt and cycle proof are missing, so production reward task remains `NOT_IMPLEMENTED`; no claim or live retry. Identity now resolves correctly, but the explicit index-2 ADB transport remains unavailable and blocks live work. |
| Free Pack | `SURVEY_DONE` — inspected shop surfaces only; claim **not done** | Index-2 daily offer, help, daily-pack, weekly/monthly and adjacent shop evidence exists. Help mentions purchases/activation tickets; a red dot on the gift is not proof of zero cost. Historical index-4 manual gift yielded 20 diamonds; do not replay. Fail-closed task scaffolding in `108ea2b` passed CI `35676774563`. | Obtain independent current-account zero-cost, availability and postclaim evidence or retain `NOT_IMPLEMENTED`. Do not tap red-dot gift, paid pack or ticket control to test a hypothesis. No repeat of accepted daily-pack navigation for this item. |
| Free Recruit | `SURVEY_DONE` — page evidence only; claim **not done** | Index-2 Tavern-selected, Recruit-open and exit screenshots exist; free `3/3`, tickets 277 and diamonds 4114 were observed without recruit input. Five index-2 Recruit templates and fail-closed task scaffolding exist; `108ea2b` CI passed. Historical index-4 manual free recruit happened once; do not replay. Newer same-account selected-name/menu matches failed conservative gates, so no live Recruit survey was packaged. | Qualify a reliable current-account Tavern→Recruit route without lowering the `.97` Tavern threshold, then independent free-result/receipt, paid-alternative and cycle evidence. No free/x10 recruit tap while these are absent. |
| Free Reward Explorer | `CI_PASS` — safety foundation only; production integration **not done** | `63dfc86` introduced free-only guard and bounded explorer; `9db7a1c` CI `35525124909` passed. `b8be92a`, `53c2462` and `4a08d22` added/tested current-frame matching, paid/UNKNOWN diagnostics, bounded nested traversal, red-dot discovery, durable RESERVED/VERIFIED journal and fail-closed task scaffolding; their Windows CI runs passed. No explorer-driven real claim was accepted. | Bind only independently qualified account-specific screen adapters/receipts; prove recurrence/cycle instead of guessing reset. Integrate with reward tasks and test no premium/resource spending. Foundation tests/CI need not be repeated without a relevant code change or regression. |
| Shop Traversal | `REAL_ACCEPTANCE_PASS` — **bounded daily/help/daily-pack route only**; full Tiệm traversal **not done** | Manual index-2 survey already photographed multiple shop tabs and vertical/horizontal boundaries. Production run 9 accepted Home→daily→help→daily→Home; run 13 accepted the same bounded route; run 15 accepted Home→daily→help→daily→daily-pack→daily→Home with `claims=[]`, `journal_rows=0`, owned cleanup and identical before/after inventory. Run 15 report: `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\tasks\shop-survey\5-Emmmmm\20260922-014852-111006Z\report.json`. `108ea2b` CI `35676774563` passed. Run 14's identical route failed overall isolation and is **not** acceptance. | Qualify and integrate the remaining named tabs/nested menus and vertical/horizontal scroll boundaries with visited fingerprints and bounded stop conditions. Report PARTIAL until coverage is proven; do not rerun the already accepted daily-pack route just because another tab is unfinished. No reward claim authority follows from navigation acceptance. |

Saved current-account evidence is under
`%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\vision\5-Emmmmm\`.
Notable VIP frames: `20260920-180241-073168Z-phase6-vip-open-after.png` and
`20260921-174132-284341Z-phase6-20260922-vip-current-after.png` (with
before/exit frames). Recruit frames: `20260920-180742-342934Z-phase6-recruit-open-before.png`,
`20260920-180746-889930Z-phase6-recruit-open-after.png`, and the
`20260920-181311-372913Z` / `181316-988122Z` exit pair. Versioned crops
are in `assets/tasks/phase6/{home,vip,recruit,shop}`. Existing tests include
`test_phase6_vip_survey*`, `test_phase6_visual.py`, `test_phase6_tasks.py`,
`test_phase6_shop*`, `test_free_rewards.py`, and `test_exploration_vision.py`.

## Historical run 16 identity/config incident

Fresh CI artifact `10673824670` from `41b747d` was used once for `vip-survey`
on index 2. Its task report is
`%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\tasks\vip-survey\5-Emmmmm\20260922-022543-065287Z\report.json`;
recovery report is
`%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\recovery\5-Emmmmm\20260922-022543-245559Z\report.json`.
The launch command was attempted, then the immutable-name guard saw index 2
as running `LDPlayer-2` instead of `5-Emmmmm` and stopped before explicit ADB
resolution, screenshot, gameplay input or reward action. Task result `ADB_ERROR`,
`survey=null`, `claims=[]`, `journal_rows=0`. The report's
`started_by_run=false` is **not proof no launch was dispatched**: current
recovery code sets it only after the entire launch/verification call returns.
No cleanup was attempted because ownership was unproven. A concurrent read-only
check found `leidian2.config` had only seven `propertySettings.*` keys rather
than the 84-key pre-ADB backup, with name/ADB settings missing. Later read-only
checks saw 13 keys and index 2 stopped, still named `LDPlayer-2`; external
state continued changing after the task and no agent cleanup was sent. The
reports establish the timing, **not the cause** of that rewrite. An old
pre-ADB backup exists but must not be blindly copied over current state.
At that historical audit check index 2 was stopped under the wrong name. The
2026-09-23 check now resolves the expected name, but indexed ADB remains
unavailable. No automatic rename, config restoration, ADB enabling, transport
substitution or live acceptance is permitted under the current no-config-edit
rule. Queen and index 4 received no task mutation.

Offline follow-up after this audit: commit `1c20bdf` fixed the run-16
launch-reporting gap without device access. The Manager now records indexed
launch dispatch and UNKNOWN ownership separately from confirmed ownership;
recovery and VIP task
reports retain that evidence. Account/name/selection/boot mismatches cannot
use the transport retry or an index-only cleanup. A reviewer found and the
developer fixed a P1 on the second transport attempt: after a later boot
mismatch, there is no additional quit/relaunch. The reviewer approved the
corrected diff. Parent ran 199 focused cross-boundary tests and Ruff; all
passed. Full Windows CI run `35706476751` passed lint, tests, build, smoke
and artifact upload. **No live acceptance follows from these checks.**

## No-repeat rule and next checkpoint

Mark a completed step reusable. Repeat only when its relevant production code
changed afterward, a regression failed, CI invalidated it, or the evidence is
genuinely insufficient for that **same** step. Record that reason and the
specific old/new evidence before a repeat. A new Codex session or an unfinished
different Phase 6 item is never a repeat reason. Never repeat an uncertain or
completed real claim to manufacture fixtures. Every account rediscovers a
target from its own current screenshot; no index-4 coordinate authority.

Current next exact action: keep gameplay input frozen while the explicit
index-2 ADB transport is unavailable. Preserve run-16 and 2026-09-23 evidence;
do not restart VIP survey or the accepted historical shop route. If ADB becomes
available without a persistent configuration edit, re-verify exact index/name,
selection/protection, explicit ADB/boot mapping and stable unrelated inventory
before considering only a genuinely unfinished real acceptance.
