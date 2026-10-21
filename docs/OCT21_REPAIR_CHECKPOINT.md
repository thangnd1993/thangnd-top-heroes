# October 21 production repair checkpoint

## Latest follow-up and journal incident — read first

The later random development sample from2/3/4 chose2 and4, on clean source
b5b72c8, with one lease/two workers. This was NOT the user's final normal UI run.
Source and full hashes: `artifacts/oct21-followup-manifest.json`.
Report: `diagnostics/tasks/automation/20261021-085558-471001Z-2390bba5/fleet-report.json`.
2:55.304s, no claim; launch_game left Android Home unchanged in the20s sample,
explicit emulator-5558.4:832.604s, developer safety cancellation, not a completed
full-plan account. Both scoped cleanup SUCCESS and selections restored.
Protected/running/name states unchanged. Final normal-UI Start remains USER-only.

**Incident:** existing production fresh-batch reconciliation upgraded old579
RESERVED/POSSIBLE→VERIFIED without input, using an original October16 receipt
plus October21 empty-member frames/new boot. This is insufficient causal proof.
Only579 changed among the pre-task journals (status/verified_at/after_evidence).
Do NOT claim every old journal remained unchanged across this second check.
Original row is preserved in both journal baseline files; do not silently roll
it back, downgrade it or erase the reconciliation sidecar. No579 reward tap occurred.
The safety cancellation stopped before any Mail reward input; Events not run on4.

Repair: fresh-batch reconciliation requires the ORIGINAL boot and two fresh
postframes within180s of original action, with original receipt within60s.
Later empty pages, expiration, resets and a newly verified boot cannot prove
old consumption. Existing raw VERIFIED rows with invalid legacy observed-batch
proof are kept unchanged but production refuses new eligibility for that reward,
reporting JOURNAL_PROOF_REVIEW_REQUIRED. Held IDs:
124,358,359,448,505,575,577,578,579. No schema/config/identity redesign or journal reset.
`artifacts/oct21-final-journal-audit.json` records the exact incident and holds.

Other concrete follow-up repairs:
-4 reached the Technology modal through the stable-node guard, and only WOOD
  was qualified before input. Ordinary747 consumed20→19. Quick748 was dispatched
  ONCE. OCR omitted zero afterward. Strict complete current0/20 footprint now
  proves zero without O→0 guessing or accepting a substring inside10/20.
  Production original-file qualification found two ORIGINAL0/20 postframes at
  09:08:16.196506/09:08:23.429782 UTC, before09:08:02.159797, same boot.
  Production reconcile_saved_guild_mail upgraded748 with NO redispatch.
  Proof: `artifacts/oct21-748-qualified.json`, `artifacts/oct21-748-reconciled.json`.
  Next visible contribution cost is STONE; no further contribution is authorized.
  732 lacks two original zero frames and stays RESERVED/POSSIBLE.
-4 Monthly upper quick744 VERIFIED; independent lower daily remained UNKNOWN
  during the run and was NOT tapped. Its owned-label raster scored.962708 below
  .98. Existing strict subpixel matcher scores.988250, with the same paired
  Monthly title/daily heading/current green bbox/paid exclusion. Offline repair
  retains threshold.98, ambiguity rejection and separate lower journal.
-4 member empty label is positively matched (.999524), but its historical579
  auto-reconciliation exposed the incident above; do not call that a new claim.

Totals after saved-file748 proof:39 NEW journals710–748,38 VERIFIED and732 POSSIBLE.
These comprise30 reward operations (VIP6/BXH3/Shop14/Guild7),4 Mail read batches,
3 WOOD operations (two ordinary plus one quick;21 contributions total),
and1 expedition mission send.579 is NOT included as a new verified operation.
56 total RESERVED/POSSIBLE rows remain locked, plus9 raw VERIFIED proof-review holds.
The earlier counts below describe the first8/10 development run only.

Final code is subject to one completed full CI/Windows build/smoke gate after
this batch. Earlier39570566455/39572491362 were canceled before completion when
additional concrete defects were found; neither is delivery evidence.
Final related regression batch:219 passed in527.95s, including target inventory,
Guild/Mail/WOOD, original-action reconciliation, Monthly and Book candidate guards.
Earlier60 Book/Event proof tests also PASS (overlap; do not sum test batches).
Ruff and diff checks PASS. No game worker remains active.
No further real developer reward run is planned before the user's independent Start.

Phase 8 remains **PARTIAL**. No Phase 9. Final normal-UI full-plan Start with
two workers belongs to the USER. Developer checks do not establish standalone PASS.
Normal-UI run16 / 600a70f remains the latest independently started application run.

## Actual focused production execution

One fleet lease, two application workers, random sample without replacement from
eligible indexes 2/3/4/8/10. Selected 8 (Soup) and 10 (HiHi); names are labels only.
Original source: 2146b5e plus the frozen hash manifest and diff in
`artifacts/oct21-focused-manifest.json`. Subsequent repairs below were offline.
This was a source development check, not a fresh packaged-artifact acceptance.

Report under the local application data directory:
`diagnostics/tasks/automation/20261021-074115-399431Z-52936f9e/fleet-report.json`.
Both workers began 07:41:16.381820 UTC. Worker10 ended08:07:37.715877;
worker8 ended08:08:33.552510. Peak concurrency2. Elapsed:8=1637.171s,
10=1581.334s, including startup and failures. Both PARTIAL, scoped cleanup SUCCESS.
All selections restored; every final instance stopped as before. Protected
0/1/6/7/12 unchanged, name/config writes0. All pre-run journal rows unchanged
(`artifacts/oct21-old-journal-audit.json`); no claims replayed for coverage.

28 new journal rows710–737:27 VERIFIED and one RESERVED/POSSIBLE (732).
Do not confuse these with27 newly dispatched reward operations in the fleet report:
737 is a separately journaled mission send, not a reward.

| Independently recorded operation | VERIFIED new journals |
| --- | ---: |
| VIP upper gift / daily | 4 |
| BXH | 2 |
| Shop daily / weekly / permanent / monthly quick / monthly lower | 10 |
| Guild relic / loot / member | 5 |
| WOOD ordinary contribution,13→12 | 1 |
| Mail guild / reports batches | 4 |
| Expedition send (mission, not reward) | 1 |

VIP710/711 image comparison confirms upper attention disappears and points
2926→2928; daily green Nhận changes to a gray countdown. This is stronger than
transport/popup success. Guild loot263→0 on8 and155→0 on10; member19→0 on8.
737 has two independently captured running-mission postframes.

## Measured bottlenecks

| Target | Inventory command | Recovery detector exclusive | Feature detector exclusive | Capture command | Deliberate wait |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8 |286.287s/1237 calls|355.730s|402.172s|108.619s|76.992s|
|10 |282.764s/1199 calls|346.057s|427.546s|91.006s|61.777s|

These are component measurements; do not sum nested inclusive timings.
The previous run16 healthy-account workload differs, so no end-to-end speedup
percentage is established. The few-minutes target is NOT met.
Saved-frame recovery benchmark retains identical classifications/confidences:
chapter2.414→1.555s, calendar2.290→1.333s, Home1.586→0.860s.
Two-worker OpenCV thread-count experiment showed no consistent benefit; unchanged.

## Cohesive repairs after execution

- Target reads still obtain fresh Multi inventory, backing identity, live flags,
  indexed serial/boot/PID. Only the bound target is merged; unrelated disks and
  journals are not revisited. Full refresh still revokes genuinely absent targets.
- Required recovery titles gate dependent searches; all competing groups remain
  checked. No confidence threshold reduction or stale screenshot cache.
- Phase6 entry/reward capture retains an explicit binding for fresh verification,
  avoiding global rediscovery. Same-frame duplicate classifier calls removed.
  Entry evidence is consumed before dispatch, including uncertain transport errors.
- Quà Hội member page positively matches stable “Hiện Trống” text together with
  qualified page/tab, no current claim label and no badge. Green quick button alone
  never proves availability or exhaustion. Conflicting empty/batch evidence UNKNOWN.
- Mail badge20 white digits overhang its red fill. Bounded current-badge crop
  extension retains two-render OCR consensus and rejects conflicting margins.
- Technology tree auto-scroll moved the node after entry on8. Require two fresh
  agreeing node boxes before its single navigation tap; bounded3 observations.
- Guild/Mail Stop propagates after journal persistence; no sibling actions,
  final audit captures or Home inputs after cancellation.
- Historical Event POSSIBLE rows are no longer seeded as this visit's pending
  actions. A later unavailable screen cannot upgrade an unrelated old action.
- Repeated expedition viewport now reports NO_FURTHER_PROGRESS and
  MISSION_LIST_END_UNPROVEN, not COMPLETE. Independently qualified visible
  collection/send remains allowed; whole-list exhaustion remains blocked.
- Follow-up saved-frame review: Book Nhận caption raster alignment was .957 raw
  versus .996 with the existing strict subpixel matcher (threshold .995 unchanged).
  More importantly, original claim388 postframes193321/193335 on October13 show
  a season-card PURCHASE reminder, not a receipt. A completed fraction and green
  Nhận therefore do not independently prove free entitlement on this route.
  Book rows are explicitly UNKNOWN candidates / BOOK_FREE_ENTITLEMENT_UNPROVEN,
  never FREE controls, pending clean entitlement/postcondition qualification.
  Two additional game-only fixtures retain the current page and original reminder.
  No historical claim was unlocked, reclassified VERIFIED or redispatched.

Image additions contain game UI only: empty member page, stable empty text core,
and cropped System mail tab/badge. No credentials/tokens/cookies/private files.

## Exact outstanding work / do not replay

-732: HiHi WOOD quick dispatched once. Original frames show12→0→1→1;
  countdown00:00:21→00:00:10→00:29:39→00:29:29 supports a refill between
  postframes. The current proof requires two agreeing consumption frames; later
  single-digit OCR is unresolved. Keep732 RESERVED/POSSIBLE. Never resend it.
-8 Technology node stability repair is offline-qualified; no new live tap for proof.
-10 empty member page repair is offline-qualified; no new live action needed to
  prove the saved state. System badge repair likewise requires fresh runtime
  evidence on the user's next run before claiming standalone acceptance.
-8/10 Idle blocked by historical identity/journal continuity, not unavailable.
-Mail System badge20 was unprocessed;10 final tab audit lost its Mail page and
  therefore independent tab statuses remain CURRENT_BATCH_PENDING/UNKNOWN.
-Events8:6 discovered candidates; notification geometry, unqualified nested
  content, book milestones/controls, one ALREADY_ATTEMPTED lock, scroll bound,
  paid-modal content and final UNKNOWN remain unresolved.
-Events10:8 candidates; saved completed-mission identity unresolved, completed
  reward not collected, unqualified nested content/book controls, scroll bound,
  notification geometry, root reacquisition failures and UNKNOWN remain unresolved.
  Exact page identities and captures are retained in the original feature reports
  and compact `artifacts/oct21-event-outstanding.json`. No Event reward was verified.
-Mission full-list end is unproven;737 must never be resent for coverage.

57 uncertain journals remain locked:22,23,24,25,26,27,30,41,47,138,241,243,244,
259,270,282,293,309,311,315,318,334,345,365,366,367,374,388,390,425,428,429,
455,459,463,479,480,484,486,487,494,533,538,545,579,596,600,605,634,635,
656,658,662,682,707,709,732. Historical138 accepted exception remains locked.

## Index11 exact diagnosis

Oct21 controlled indexed startup and Android-ready succeeded. LDPlayer reported
emulator-5576; explicit ADB transport remained ABSENT, indexed boot unavailable.
Failure TARGET_TRANSPORT_UNAVAILABLE, not an assumed vision issue.
`basicSettings.adbDebug` absent, not proven equivalent to disabled. No persistent
setting changed or authorized. Owned cleanup restored previous states. Defer only11.
Evidence: `artifacts/oct21-index11-result.json` and its referenced recovery report.

## Gate and delivery

Targeted batches:111 passed before final additions,95 passed for Events/Stop/OCR,
45 passed for identity/navigation/Oct19 compatibility (overlap, not additive).
Ruff and diff check pass. Final CI/portable provenance and Desktop hash must be
recorded in `artifacts/oct21-ci-final.json`, `artifacts/oct21-delivery.json`.
Full pytest/build/smoke only in GitHub Actions. Deliver fresh passing portable
to `C:\Users\ADMIN\Desktop\app\TopHeroesAutoManager\TopHeroesAutoManager.exe`.
Retain at most2 verified build caches, no redundant ZIP. Preserve evidence/data.
Do not automatically Start the delivered app's full plan. Read the actual user's
next normal-UI run/build afterwards. Keep Phase8 PARTIAL until remaining routes
are exhausted or positively unavailable; no Phase9.
