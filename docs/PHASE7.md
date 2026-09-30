# Phase 7 — Guild and Mail

Status: PARTIAL; latest2026-09-30 resume has7/8 COMPLETE. Only Mini Quin external bounty screen remains blocked. See PHASE7-CONTINUATION-20260930.md.
Branch: `codex/phase7-guild-mail`, based on Phase 6 completion `c4309fe`.
The user's 2026-09-27 request explicitly starts Phase 7; Phase 8 is excluded.

## Authorized scope

One agent; the existing instance-first registry owns lifecycle. Guild and Mail
register features, not fleet passes. Finish all eligible sub-rewards in each
feature visit. Never restart an instance between features or after an external stop.

- Guild: Territory → Relics gift; Gifts → loot and member tabs; Technology →
  the uniquely like-marked technology → green wood donation only.
- Mail: numbered red-badge tabs → Quick Read. No delete action.
- Trial Hall, purchases, diamonds, upgrades, relocation and other resource
  actions are forbidden. The explicitly approved green technology donation
  is a narrow exception for its visually proven wood cost, not general spending.
- Unknown/partial/conflicting UI gets no input. Popups require qualified current
  evidence before the existing bottom-left dismissal; capture again afterward.

## Journals

User confirmed Relics reset daily at 09:00 Vietnam (02:00 UTC).
Gift batches and mail contents do not inherit that reset. Every dispatch is
reserved first and marked POSSIBLE before transport. A new action requires
independent progress and a verified prior action. Unresolved actions stay locked.
Technology needs a current count, the green wood control, and an independently
changed count/progress after each input. A notice/receipt alone cannot verify.

## Evidence and gates

Ten annotated references are in `C:\Users\ADMIN\Desktop\demo`. Annotations
describe intent, never runtime tap coordinates. Runtime anchors use only clean
UI cores, matched afresh with page/geometry checks. No account-specific routes.
Windows OCR is local and reads counters only; it supplies no confidence score.
Ambiguous/inconsistent numbers fail closed.

Targeted tests + Ruff + self-review precede commit/push and the full Windows CI
gate. Deliver and verify the fresh portable artifact at the fixed Desktop app
folder. Only then select a random live non-Protected account for the bound test,
followed by all current non-Protected targets sequentially. Preserve prior
selections, names, Protection, external running ownership and historical journals.

At the initial offline checkpoint, no Phase7 reward had been dispatched.
The current action122 state is recorded in the latest section below.

## Offline implementation checkpoint

Registered Guild and Mail after the existing VIP/ranking/Shop features; the
outer scheduler remains generic. Added per-action batch count reporting and
current-frame geometry evidence. No changes to Phase 6 journal/claim policies.

Initial targeted regression gate: 92 passed (Guild/Mail, instance pipeline,
Phase 6 fixed-flow regressions). Ruff passed for affected Python files.
Self-review: no lifecycle in feature adapters; navigation edges are allowlisted;
no Trial Hall/delete/diamond path; count or receipt ambiguity stays locked;
loops are bounded; no names/config writes or fixed-account coordinates.
The final dimmed-parent regression also passed. Three badge/disabled-control
checks and twelve journal/identity/period checks passed again after self-review.

Reference-image qualification is not real acceptance. At that checkpoint there was no Phase7 emulator
activity. The next gates were: full CI, verified Desktop artifact, random bound acceptance,
then all non-Protected targets only after that feature acceptance is safe.


## First live random acceptance — 2026-09-27

Build `00f131f`, CI36312719887 passed: lint,930pytest tests(26skipped), portable
build, executable smoke and artifact upload. Artifact10930191411 was verified
against its run/commit and all590 delivered files at the fixed Desktop app path.

Random selection used secrets.choice over live eligible indexes2,4,5,8,9,10,11;
selected11/Nấm đùi gà, explicit ADB emulator-5576. Report:
`diagnostics/tasks/automation/20260927-110519-852460Z/fleet-report.json`.
Seven current-period Phase6 rewards were VERIFIED (journals115–121). All98 earlier
journal rows remained identical. Guild and Mail stayed BLOCKED at Home entry,
with ZERO Phase7 inputs/reward dispatches. Cleanup and selection restoration
succeeded. Protected0/1/6/7 stayed stopped/unselected; external index2 stayed running.

Concrete blocker: the correct Home icons score .960/.952 with the original
three scales; reference/live raster resampling differs slightly. The repair
adds the evidenced1.02 scale and a common3x3 sigma.5 antialias filter ONLY to the
Home entry cores. The .97 threshold, global uniqueness and destination guards
are retained. Per-capture anchor evidence is now persisted. Offline regression
uses the saved live frame plus duplicate and unrelated-icon negatives.
No fleet has run yet; Phase7 acceptance remains incomplete.

Entry repair gate:56 targeted Guild/Mail tests passed; Ruff and diff whitespace
checks passed. Self-review kept dispatch, journals, paid exclusions, Protection,
identity and lifecycle unchanged. Home image contains game UI only; PNG has no
ancillary/private metadata.


## Bound resume and text-rendering repair — 2026-09-27

Build fb29e04 / CI36316009950 passed lint,934pytest(26skipped), build, smoke,
artifact upload. Artifact10931047895 and590 Desktop files were verified.
The original random target11 was resumed from its fixed snapshot. Report:
`diagnostics/tasks/automation/20260927-120442-167061Z/fleet-report.json`.
The Home Guild entry correctly opened Guild. No reward inputs were dispatched;
Phase6 journals115–121 were skipped. Guild outlined-text scores remained below
.97 because the resized reference glyphs have softer edges than the live renderer.
All claims stayed locked/intact. Owned cleanup and original selections succeeded;
Protected states and names were unchanged. No full fleet yet.

The repair applies a fixed5x5 sigma1.3 rendering normalization to outlined text,
with a bounded eight-pair scale grid; icons and numerical glyphs retain their
separate strict qualification. Confidence thresholds are unchanged. All page
titles still participate in conflict detection; controls are searched only for
matched page families to limit processing time. Page pairs must also be undimmed.
Duplicate evidence in EITHER template variant cannot be rescued by another crop.
Current Guild labels qualify at .979–.994 from the saved clean screenshot.

Local:61 targeted Guild/Mail tests passed; Ruff and diff whitespace checks passed.
Regression includes live/reference text, duplicate and unrelated regions, dimmed
parents, missing page evidence and secondary-variant conflicts. Phase7 remains
INCOMPLETE pending the fresh full CI artifact and bound real continuation.


## Original member action122 and remaining concrete UI gaps

Build15d6ab3 / CI36320338679:939passed,26skipped; lint/build/smoke/upload passed.
Artifact10932860270 delivered and590 files verified. Bound resume report:
`diagnostics/tasks/automation/20260927-144934-534222Z/fleet-report.json`.
Guild and Mail each entered once, Home return/cleanup/restoration succeeded,
Protected states and names unchanged. ZERO replay of Phase6 rewards115–121.

One real member Quick Claim was dispatched:journal122 RESERVED/POSSIBLE.
Before:12. Original post frames145252 and145301 show no badge, four received
check rows, and no green individual claim; Quick Claim itself remains green.
DO NOT redispatch122. The new offline qualifier reproduced AVAILABLE12→
NOT_AVAILABLE0 on both ORIGINAL post frames using read-only SQLite. The live
journal has NOT been changed yet; reconcile only through the fresh passing
artifact. Original task, identity, timestamps, one transport input, geometry and
two independent post frames are mandatory. No device transport in reconciliation.

Additional repairs from this same evidence:
- Territory title settled before its tab. Up to2 fresh navigation observations;
  no replay of entry and no input if the page changes/UNKNOWN.
- Loot badge196 and Mail4/10/60: bounded OCR crops agree or fail closed; a complete
  local badge4 is the only new single-glyph fallback. No numeric substitutions.
- Mail selected System/Reports variants use clean text cores, excluding badges.
- Technology like marker is present; its brown node is connected to graph lines.
  Associate the unique marker with a current edge rectangle and brown interior,
  merge only nested edges of the same node; never select another tree item.
- Received rows + absent Quick Claim badge are positive unavailable evidence;
  a remaining green row or conflicting evidence still blocks verification.
- Small-icon antialiasing retains strict thresholds and uniqueness; numerical
  badge templates and receipt checks retain exact pixel qualification.

Current local gates:70 targeted Guild/Mail tests plus7 reconciliation tests
passed; mixed received/claimable regression and final review follow. Full fleet
has NOT run. Phase7 is still PARTIAL, and Phase8 remains excluded.

Final local gate:78 targeted tests passed;7 reconciliation cases rechecked after
adding task/protection binding. Ruff/diff checks passed. Self-review preserved
fixed routes, original one-shot journal locks, bounded waits and paid exclusions.
All14 new game PNGs were reviewed; only PNG image chunks, no private payloads.


## Receipt/background repair after dd52fe7 — 2026-09-28 Vietnam

CI36334422519 passed lint,956pytest(26skipped), build, smoke and upload.
Artifact10936394421 matched dd52fe7 and all595 Desktop files. Original member
claim122 was reconciled VERIFIED by the fresh portable without device input.
The bound random target11 resumed from its existing snapshot; report:
`diagnostics/tasks/automation/20260927-171830-193499Z/fleet-report.json`.
Owned cleanup/selection restoration succeeded. Protected0/1/6/7 and names are
unchanged. Index2 was already stopped at this run's preflight and stayed stopped;
this run issued no command to it. The earlier externally running state is not
restored by automation.

New one-shot claims123(loot) and124(Mail System) remain RESERVED/POSSIBLE.
Never redispatch them. Original123 evidence independently shows67→0, two received
post frames, and exactly one known bottom-left receipt dismissal. The normal90s
window was exceeded by slow receipt recognition. Saved reconciliation can qualify
this specific original chain within180s ONLY with an immediate paired receipt,
a single proven safe dismissal, and two post states within30s of that dismissal.
No global runtime timeout changed. Read-only qualification of123 succeeded;
the real journal must be reconciled only through the next passing artifact.
124 needs its original receipt plus two fresh positively exhausted System-tab
observations on the same persistent target. A receipt alone cannot verify it.

Concrete repairs:
- Same continuation text over different blurred backgrounds: fixed high-pass
  glyph detail, strict.98 and unique match, paired with independent receipt title.
  No dynamic artwork template, threshold reduction or receipt-only verification.
- Territory navigation: at most2 fresh observations while the original page is
  unchanged; never replay the navigation. UNKNOWN/unexpected pages fail closed.
- Current green donation label excludes changing cost. Orange paid button edges
  remain measurable when its color mask joins the modal border; require the
  separate diamond inside that forbidden rectangle before any wood donation.
- Selected Mail badge4 changes its surrounding background; full-badge detail at
  .98 remains bound to the local red container. No reading6 from60 or OCR guesses.
- Original evidence preparation precedes fresh reconciliation captures, so slow
  offline verification cannot make a valid newly captured post-state stale.

Phase7 is PARTIAL. No full fleet yet. No Phase8. Seven Phase6 claims115–121 and
all98 baseline rows remain protected from replay or downgrade.

Local gate:139 targeted Guild/Mail, receipt and overlay tests passed. The final
reconciliation changes were rechecked separately:24 passed. Ruff and diff-check
passed. Self-review covered duplicate dispatch, original/fresh receipt ownership,
identity/Protection, bounded waiting, paid-region separation and no phase expansion.
All five new PNGs were visually reviewed as game UI; only IHDR/IDAT/IEND chunks.
All105 prior journal rows compare exactly unchanged (98 original +7 Phase6).


## Bound acceptance of3c6065d — actual post-states and resource boundary

CI36340020970 passed lint,986pytest(26skipped), portable build, smoke and upload.
Artifact10939017553 matched commit3c6065d;323 runtime assets and596 Desktop files
verified. Saved loot123 is now VERIFIED from its original67→0 evidence; zero input.
Resume report: `diagnostics/tasks/automation/20260927-185302-499390Z/fleet-report.json`.
Only original random target11 started. Four new inputs:125Relic(POSSIBLE),126new
loot batch(VERIFIED),127Mail Guild(VERIFIED),128Mail Reports(VERIFIED). Original124
System Mail was NOT redispatched and remains POSSIBLE. All105 earlier rows are
identical; among108 pre-build rows only the justified123 verification changed.

Owned cleanup and selection restoration succeeded. Protected0/1/6/7 and all
names unchanged. Pre/post externally running1,2,4,5,7 were preserved; never stop
or restore those instances as part of target11's cleanup. No full fleet yet.

Relic125's original fresh post frames positively show a GRAY gift + countdown.
The former active-gift core no longer matches. A clean gray icon core now gives
strict.98 positive unavailable evidence, paired with the real Relic page; duplicate,
missing, active/conflicting cores remain UNKNOWN. Original before→two after
qualification succeeded OFFLINE, read-only. Reconcile125 through a fresh passing
artifact; never send that claim again. A current-period verified Relic completion
hook allows the generic registry to skip it before lifecycle/navigation.

System Mail decreased10→1. Its one-digit badge was unreadable to OCR, so navigation
failed closed. Added the whole local badge1 at.98, never a digit inside10. Original
receipt plus two fresh, agreeing, lower counts on the same persistent target can
prove the original batch's progress. Counter change alone and receipt alone cannot.
Only after verification may the ordinary batch loop consider the remaining free
content; every new action still needs its own reservation and changed post-state.

Input timing audit: an action bound to an immediate receipt happens AFTER that
capture, even though PNG metadata precedes CapturedScreen timestamp by milliseconds.
Only one positively qualified bottom-left receipt dismissal is allowed there;
other/duplicate input before the independent receipt is rejected.

Technology sent ZERO donation input. Guild technology advanced from level3 to4
externally; the current green button costs5804 STONE, not the approved wood icon.
The guard correctly blocked it. A user clarification is pending for whether the
resource exception includes ordinary stone as well as wood. Until answered, retain
the wood-only rule; no stone/diamond/resource spending is authorized by this repair.
No Phase8.

Local repair gate:111 visual/flow checks passed in the combined targeted run.
One new test imported a feature before bootstrapping the public registry; its
setup was corrected to use production_registry. All36 final hook/reconciliation/
registry checks then passed, including receipt-bound safe dismissal and remaining
batch continuation. Ruff/diff-check passed. Self-review: original claim proofs,
no same-period replay, explicit current-target geometry, no changed spending
scope, and no lifecycle/selection changes. Six new game-only PNGs have no private
ancillary chunks. No emulator input was used to qualify the offline125 repair.


## Original receipt animation — bound c4481fb acceptance

CI36345068912 passed lint,1004pytest(26skipped), portable build, smoke and upload.
Artifact10941261183 matched c4481fb;325 runtime assets and598 Desktop files verified.
Saved Relic125 is VERIFIED with zero input. Bound resume report:
`diagnostics/tasks/automation/20260927-202040-598213Z/fleet-report.json`.
No new claim input. Technology stayed blocked on stone,20 remaining; no donation.
System Mail124 remained POSSIBLE; independent current badge1 qualified, but the
original immediate receipt had a star animation across its title. Recognition
correctly stayed UNKNOWN. Cleanup/selection succeeded; pre/post inventory identical,
including externally running1,2,4,5,7. All105 earlier rows are unchanged; only125
changed among the112 pre-build rows. No full fleet/Phase8.

The next ORIGINAL saved frame,18seconds after the original claim, has a clean
paired receipt: title1.0, continuation.996483. No input intervened. Reconciliation
may inspect at most5 following original capture sidecars within the SAME60-second
original-action window, with exact task/image/index/name/ADB/boot binding and no
intervening input. A known different screen or weak/absent receipt fails closed.
No template/threshold/runtime wait changes. The animated frame stays UNKNOWN.
Receipt alone still cannot verify: two fresh independent agreeing lower-count
frames on the same persistent account remain required. Only then may ordinary
batch processing consider the separate remaining content.124 must never replay.

The new fixture is the exact game-only initial receipt animation, visually checked;
PNG contains only IHDR/IDAT/IEND. Tests cover stabilization, input interruptions,
late frames, missing anchors, target/sidecar ownership, intervening known screen,
frame limit and unchanged post-state. Resource scope remains wood-only pending
the user's answer; no stone authorization is inferred.

Local gate:53 targeted reconciliation/live-evidence tests passed in216.68s;
Ruff and diff-check passed. Self-review covered one-shot preservation, unchanged
60s evidence bound, maximum5 saved frames, input/identity/sidecar rejection,
receipt-only rejection and paid/resource scope. No production detector changed.


## Latest accepted bound run —14e5ad6 /2026-09-28 Vietnam

CI36349076581 passed lint,1015pytest(26skipped,1487.59s), Windows portable build,
GUI smoke and artifact upload10941694353. The artifact's repository/branch/run/
full commit were verified, all325 runtime assets compared, and all598 Desktop
files hash-verified after replacing only the previously verified Top Heroes build.
Desktop EXE SHA256:
`ff053c4a74809e12493da15901bf228b2b73a5528736810e9b64ef2306c72252`.
The checkpoint update below is documentation only; tested app source remains14e5ad6.

Resumed ONLY the original random-bound11 / Nấm đùi gà, explicit ADB emulator-5576.
Original eligible random set[2,4,5,8,9,10,11], method secrets.choice; no new target
selection or scope expansion. Final report:
`diagnostics/tasks/automation/20260927-211615-066061Z/fleet-report.json`.

- Prior seven Phase6 rewards115-121 stayed completed, with no navigation/replay.
- Relic125 was skipped as current-period VERIFIED; no second gift input.
- Guild member122 and loot123/126 remain VERIFIED; completed subflows skipped.
- Technology still UNKNOWN/blocked,20remaining, ZERO donation input. The current
  green control costs stone; no authorization is inferred from the pending answer.
- System Mail124 reconciled VERIFIED from its original one-shot action, the
  original clean receipt after animation(.996483), and two fresh independent
  agreeing lower-count frames.124 was NOT redispatched.
- Exactly ONE new QuickRead129 handled the separate remaining System Mail1→0;
  independently VERIFIED by the unread count change; no reward popup appeared.
- Mail Guild127 and Reports128 remain VERIFIED. War/Collection had no eligible
  numbered badges. Mail SUCCESS and Home return SUCCESS.
- Overall PARTIAL solely because Technology remains unresolved. No full fleet yet.

All8 Phase7 journal rows122-129 are VERIFIED. Among112 pre-build rows only124
changed, plus new129. All105 earlier rows(98baseline+7Phase6) remain identical.
No VERIFIED downgrade or uncertain-action replay. Audit:
`artifacts/phase7-14e5ad6-final-audit.json`.

Owned target11 cleanup SUCCESS, selected=false restored. Pre/post full inventory
identical: running1/2/4/5/7 stayed running;0/3/6/8/9/10/11 stopped. All12 selections
false, Protected0/1/6/7 unchanged, no name/config changes. No Protected ADB/input/
lifecycle command, no paid/diamond input, no resource donation, no Phase8.

NEXT: wait for the user's pending resource-scope answer (ordinary stone as well
as wood, or wood only). Do not spend stone or launch the full fleet before that
scope is resolved and Technology is appropriately qualified. Preserve all journals.


## Confirmed wood-only boundary and final-fleet authorization —2026-09-28

User explicitly resolved the resource question: WOOD ONLY, including when the
button is green. Do not broaden SAFETY.md to stone. The original brown-log
reference qualifies as WOOD(.998551); the prior live wood variant also qualifies
(.982178). The saved level4 gray cost is a different stone icon(.998279), not a
mislabelled brown log. Existing wood threshold.97 is retained; stone diagnostic
anchor is.98 and can never authorize spending.

Resource matching is local to the CURRENT qualified green button. Require one
unique wood match, enabled green fill, positive independent remaining count and
separate paid diamond button. Unknown/mixed/duplicate/nonwood cost is excluded.
No absolute account coordinates, color-only permission or cached previous bbox.
Production dispatch independently requires current wood evidence. One wood input
must independently decrement the count by exactly one on two fresh observations.
If the following cost changes away from wood, verify the preceding input only
from that count change, report RESOURCE_NOT_AUTHORIZED and stop immediately.
The typed exclusion completes the authorized portion; it is not a reward success
and does not suppress other Guild/Mail work. Actual UNKNOWN pages or counters stay
blocked. Reports retain start/end counts, resource evidence and verified journal.

New regression evidence contains only the saved game donation page and its gray
stone icon crop. No credentials/private files. Previous journals122-129 must not
change. The user now authorizes final acceptance directly after targeted tests,
Ruff, self-review, commit/push, full CI and verified fresh Desktop delivery.
Use a fresh explicit snapshot of ALL live non-Protected targets sequentially;
all enabled registered flows per instance, one lifecycle/feature visit, owned
cleanup, original selection and external running preservation. No extra fixed
account trial, no Phase8.

Local gate:158 targeted Guild/Mail, reconciliation, wood-policy and instance
pipeline tests passed in226.34s. Ruff/diff checks passed. All16 final wood/stale-frame tests
also passed in24.83s. Self-review confirmed exact per-input wood evidence,
positive counter, enabled button, disjoint diamonds, bounded20 inputs, no replay
of POSSIBLE journals, no previous VERIFIED edits, and independent-flow continuation.
No emulator was launched during this implementation pass.

Final review refinement: only positively recognized forbidden costs complete
as RESOURCE_NOT_AUTHORIZED. An unrecognized/mixed icon retains overall UNKNOWN
with remaining_result=RESOURCE_NOT_AUTHORIZED, so it cannot falsely pass fleet
acceptance. Independent Guild/Mail work still continues. A strict same-page
counter decrement may verify the preceding authorized wood input even if the
next control becomes unqualified; it never authorizes another donation.

Final focused gate:25 wood/donation checks passed(65 unrelated cases deselected),
including unknown-cost reporting and preservation of independently verified count
progress. Ruff/diff-check passed. The superseded CI was cancelled before using any
artifact; the latest commit must pass the full gate before real mutation.


## Full wood-only fleet result —2026-09-28

Code99dd484135197b9ca700e35e507c8b49a79ffa27, branch codex/phase7-guild-mail.
CI36393326286 passed lint,1035pytest/26skip(1974.72s), Windows portable build,
GUI smoke and upload. Artifact10958880794, digest
`sha256:347a637b3411f6030691394705c29f89fa5843e1484f247d555620dfe1f9cae7`.
All326 runtime assets matched repository source; only the previously verified
Top Heroes build was removed from exact Desktop/app, then599 copied files were
hash-verified. EXE SHA256:
`4a9075389bfa29a1396f59d62542913b178cc1d08059050161a6f8b1fbfe60f5`.
Delivery proof:artifacts/desktop-phase7-99dd484-delivery.json. Post-run files still
match the delivered build. This checkpoint changes documentation only.

Final report:diagnostics/tasks/automation/20260928-082613-687829Z/fleet-report.json.
Fresh live snapshot2/3/4/5/8/9/10/11, max_concurrency1, all five registry flows
VIP/BXH/Shop/Guild/Mail enabled per instance. Eight owned starts/cleanups; no
feature-wide fleet pass. All12 instances were stopped/unselected at preflight
and final inventory. Protection0/1/6/7, names and original selections unchanged.

V=VERIFIED; U=UNKNOWN without input; B=BLOCKED without input; P=dispatched but
unverified/locked; N=NOT_AVAILABLE. Wood column shows remaining count, zero taps.
Verified columns count new actions, not individual reward items.

| Account | Relic | Loot | Member | Wood count / cost | Mail Guild | System | Reports | Other tabs | V Phase7 / all | Cleanup/name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|2 / 5-Emmmmm|B|B|B|not reached|B|B|B|B|0 / 0|SUCCESS/unchanged|
|3 / Queen con|V|P138|U|19→19 STONE|B|V|V|N|3 / 10|SUCCESS/unchanged|
|4 / 3-Chíp|V|U|U|19→19 STONE|B|U|V|N|2 / 8|SUCCESS/unchanged|
|5 / 4-Em Pé|B|B|B|not reached|B|B|B|B|0 / 0|SUCCESS/unchanged|
|8 / Soup|V|V|U|19→19 STONE|B|V|B|N|3 / 10|SUCCESS/unchanged|
|9 / Pooh5|V|V|U|17→17 STONE|B|U|B|N|2 / 7|SUCCESS/unchanged|
|10 / Nấm hương|V|V|U|17→17 STONE|B|U|B|N|2 / 8|SUCCESS/unchanged|
|11 / Nấm đùi gà|V|V|U|17→17 STONE|B|V|B|N|3 / 9|SUCCESS/unchanged|

All six reached Technology pages were positively STONE and excluded as
RESOURCE_NOT_AUTHORIZED. Total wood/diamond/stone/other donations=0/0/0/0.
The fleet proves current forbidden-resource exclusion; no real WOOD sequence was
available to verify end-to-end. Do not claim live20→0 acceptance from offline tests.

Blockers retained, no thresholds lowered or production code changed mid-run:

- 2/5:initial recovery ACTION_FAILED, final POPUP_GENERIC, error No verified safe
 handler for POPUP_GENERIC. Explicit ADB emulator-5558/5564. No reward input.
- 3:loot138 dispatched once from236; saved post-frame visibly shows1 remaining,
 but the detector returns UNKNOWN, so RESERVED/POSSIBLE remains. Never replay138.
- 4:loot badge489 remained UNKNOWN before input. No loot journal/input.
- All six:Member page UNKNOWN; quick-member anchor approximately.9415-.9417
 below.98 despite generic quick anchor approximately.9818-.9820. No member input.
- Mail Guild badge is ambiguous on all six; System UNKNOWN on4/9/10; Reports
 ambiguous on8/9/10/11. War/Collection had no numbered eligible badges on six.
- Independent existing-flow gaps:Shop daily UNKNOWN on4; ADB/boot verification
 failures blocked VIP upper/BXH on9, Shop monthly on10 and Shop permanent on11.
 Later independent work continued only with fresh verified identity/evidence.

53 new journals130-182:52 VERIFIED(15 Guild/Mail+37 Phase6), only138 remains
RESERVED/POSSIBLE. No previous row changed:all113 baseline records, specifically
VERIFIED122-129, are identical. Read-only audit:
artifacts/phase7-final-fleet-audit.json.239 saved-action sources were bound to the
exact non-Protected target; no donation-control/Trial-Hall input in the audited
current-frame action evidence. No Protected journal, lifecycle/ADB/game action,
paid input, instance rename or persistent config modification. All selections
restored and8/8 cleanup SUCCESS. Fleet processed8/8 but all accounts remain
PARTIAL due to unresolved required flows. Phase7 is PARTIAL; Phase8 not started.

NEXT: diagnose the retained popup, quick-claim/button and numbered-badge evidence
offline; retain138 lock and every VERIFIED row. Any later code/runtime acceptance
must use its own passing artifact and bound unfinished scope. No blind fleet rerun.


## Unfinished-state repair and explicit exception — 2026-09-29

Continue checkpoint8d17ddc without replaying the accepted fleet. The user accepts
Phase7 PASS with historical journal138 preserved RESERVED/POSSIBLE as a named
safety exception. This does NOT verify138, reconcile it or release/retry its reward.
All other UNKNOWN/unprocessed required states still block PASS. Positive STONE
exclusion is a completed authorized scope; no real WOOD opportunity is required
when live pages offer none. WOOD-only code and regression coverage remain.

Saved evidence diagnosis and production repairs:

- Home assistance popup: POPUP_GENERIC previously bypassed paired covered-Home
  proof. The full saved frame has opposite Home HUD anchors .981414/.991949 at
  unchanged .98 thresholds. The popup-only crop has no Home proof and stays
  blocked. Home recovery persists these frames; after one approved bottom-left
  dismissal, the same positively proven Home overlay may receive one Back.
  Existing two-per-overlay/four-total bounds and fresh-frame verification remain.
- Gift/member and Mail failures share tiny-number reading problems. Isolate the
  CURRENT red badge from neighboring letters, preserve split three-digit fill,
  and require two OCR scales to agree. Strict isolated small glyph variants cover
  OCR-omitted single digits; unrelated/duplicate/conflicting evidence stays UNKNOWN.
  Member availability does not depend on gift row owners or changing row contents.
  Existing continuous loot/member and all-five-Mail-tab traversal is preserved.
- Shop daily saved frame: gift .990836 but rocking attention mark only .924312.
  Reuse bounded pose matching beside that current unique gift at >=.98; saved
  badge now .992284. No account coordinates, new routes or lowered thresholds.
- Read-only ADB identity probes have at most three short attempts. Recheck exact
  name/index, selection/Protection and PID/vbox PID before/after. Ambiguous serial,
  valid boot mismatch, changed serial/runtime immediately fail closed. Actual
  input is never retried; existing bounded exact-target reconnect is preserved.

Explicit CLI resume exception: `--resume-report PATH --preserve-possible 138`.
Validate original report reward/claim ID, namespace/name/index, persistent identity,
RESERVED/POSSIBLE state and live Protection. Record PRESERVED_POSSIBLE separately;
never treat it as VERIFIED. Require explicit retention on future resumes, skip
only that reward before calling its adapter, hash-check the original row unchanged.
New uncertain claims cannot inherit this exemption. No instance-number special case.

Offline baseline:166 historical rows through182, all immutable (especially122-129
and138). Ten game-only saved screenshots and five tiny numbered badge assets are
qualified regressions, with no embedded PNG metadata, credentials or private files.
Only targeted tests locally; full suite/build/smoke/upload belongs to fresh CI.
After delivery, resume unfinished original snapshot2/3/4/5/8/9/10/11 sequentially,
one owned session per instance, all enabled registered flows, same selection and
external-running ownership. No Protected changes, rename, Trial Hall, stone/diamond
spending or Phase8. Acceptance remains pending until actual resumed results pass.


Local gate:367 targeted Guild/Mail/wood/reconciliation/fixed-flow/ADB/session tests
passed in778.70s; earlier62 saved-vision/Home-overlay checks passed in259.33s.
Additional focused Home Back checks2/2 and explicit exception/CLI checks11/11 pass.
Ruff for affected Python files and git diff-check pass. Self-review confirms no
claim retries, no journal writes in exception handling, bounded OCR/identity/
overlay attempts, unchanged exact-target protection, no resource policy changes,
and no feature-wide fleet orchestration. No emulator launched during repairs.


Fresh gate/delivery:00a9a0ec2c58cc619b3eb6e54a96362c133f6704 passed CI36548361084
(lint,1074 tests/26skip in1671.10s, portable build, smoke, upload).
Artifact11024254787 digest7cc0e187a693071becadfb91336989b640cf0e836bb5457dc17bd37b23f704a6;
331 runtime assets verified. Desktop/app old599-file build was removed only after
exact hash comparison;604 new files copied/verified. EXE SHA256:
8d9c80694ed4c927471fd5f7fa14e9e90b70edc0764cc0a0c7c0e378387543b4.

Before any emulator start, read-only live inventory found USER display-name edits:
3 Queen con→Queen Queen,9 Pooh5→Mini Quin,10 Nấm hương→HiHi,11 Nấm đùi gà→Smille.
All eight backing disk identities exactly match the original report; config names
match current list2. All12 stopped; Protected0/1/6/7 and all selections unchanged.
No lifecycle/gameplay input occurred. Names were never edited by automation.

Targeted continuation repair: a resumed target may adopt its fresh exact name
only after original persistent disk identity matches and live Protection passes.
Record observed name changes/history in the report. Historical Guild journals may
retain those verified old labels only with matching disk proof; the active snapshot
and every transport still use the CURRENT exact name. Replacement disks, ambiguous
inventory, Protected targets and mid-session name changes remain blocked. Historical
journal rows are never rewritten;138 remains the explicitly preserved exception.
This follow-up requires its own passing CI/artifact before real acceptance.


## Resumed acceptance and remaining evidence repair — 2026-09-30

Fresh eed3d4b / CI36556655255 passed lint,1078 tests/26skips, portable build,
smoke and artifact upload11028774395. All331 assets and604 Desktop files matched.
Resume `automation/20260929-120233-987168Z/fleet-report.json` processed8/8 and is
PARTIAL:25 new claims, all VERIFIED; no new POSSIBLE. All166 historical rows are
unchanged, including122–129 and138. Journal138 remains the explicitly preserved
RESERVED/POSSIBLE exception. No donation, Trial Hall or Protected action occurred.
All selections and current user-owned names were preserved.

| Current account | Remaining blocker | New VERIFIED | Cleanup |
| --- | --- | ---: | --- |
| 2 / 5-Emmmmm | Initial ADB resolution; no gameplay |0|OWNERSHIP_UNKNOWN |
| 3 / Queen Queen | Mail Guild small badge5 |1|SUCCESS |
| 4 / 3-Chíp | Mail Guild small badge6 |4|SUCCESS |
| 5 / 4-Em Pé | Permanent gift pose; monthly selected-tab rendering |11|SUCCESS |
| 8 / Soup | Member gift badge59 split red fill |1|SUCCESS |
| 9 / Mini Quin | HHGames splash/loading timeout; no gameplay |0|SUCCESS |
| 10 / HiHi | None; COMPLETE |5|SUCCESS |
| 11 / Smille | Mail Guild small badge5 |3|SUCCESS |

Index2 remains running after an unowned/uncertain launch. Do not infer ownership
or quit it to restore an old state. A later authorized session must freshly bind
it and preserve its pre-existing running state. All other instances ended stopped;
Protected0/1/6/7 remained stopped and unselected. No name/config edits.

Offline follow-up uses the saved current frames only:
- qualify entire small Mail5/6 badges at.98 inside current control bounds;
- a15px close reconnects red fill split by white59, still requiring two-scale
  agreed OCR counts and rejecting duplicates/conflicts;
- accept asynchronously registered INDEXED ADB serial during endpoint connect,
  retaining indexed boot equality, runtime and unexpected-device guards;
- keep Mini Quin loading timeout unchanged: evidence positively shows HHGames
  splash, not an overlay needing input;
- existing Shop pose/subpixel anchors use fixed3x3 sigma.5 normalization where
  current rendering requires it. Intact permanent gift precedes its associated
  badge; monthly navigation uses its stable video emblem plus attention, page,
  selected tab and forbidden-area proof. No paid control or route was added;
- coarse pose proposals recurse only once even for a large template. Retain
  bounded candidates and reject distinct qualified matches.

Next acceptance must resume the NEW report above with `--preserve-possible 138`,
so the25 newly VERIFIED actions and all prior completed rewards are skipped.
Only after focused checks, full CI and fresh Desktop artifact delivery. Phase8
is excluded. Do not label this partial result PASS before remaining work finishes.


Local gate:346 focused Guild/Mail/journal/wood/Shop/identity regressions passed;
55 new-evidence/lifecycle checks passed, plus29 saved badge/relic checks,27 Phase6
finalization checks and one duplicate-attention negative. Ruff and diff-check pass.
Self-review confirms current-frame bboxes, paid exclusions, immutable journals,
bounded matching/probes, untouched ownership rules and no new feature route.
Five full game fixtures and two small runtime badge crops have only image PNG
chunks (IHDR/IDAT/IEND), with no credentials or unrelated private files. No live
input was sent during this offline repair. Await fresh full CI/portable delivery.


## Next resumed result and final Home observation — 2026-09-30

Build9d7fae5 / CI36681995562 passed lint,1089 tests/26skips, Windows build,
smoke and upload11083756270.333 assets and606 Desktop files verified after
removing only the previous604-file app. Resume report:
`automation/20260930-075232-614988Z/fleet-report.json`.

Processed8/8.16 new actions, all VERIFIED, no new POSSIBLE. All191 prior rows
remain unchanged, including122–129 and138.2/4/5/10 are COMPLETE and must be skipped
on future resumes.3/8/9/11 remain PARTIAL. All original selections, Protection and
names were preserved; no donation/Trial-Hall/paid input occurred.

New live preflight differed from the prior run through external/manual changes:
Protected1/anh Ry and9/Mini Quin were running;2 was stopped. Final inventory
preserved exactly those running instances; all others stopped. Index9 was attached
without lifecycle ownership and received ZERO input because its current screen is
an unrelated bounty board (Treo Thuong). User was asked to return it to Home or
explicitly authorize one newly qualified Back edge; do not blind-dismiss UNKNOWN.

Remaining evidence:
-3:Loading timeout at100.703s, but the already-required final capture at103.782s
 positively showed GAME_HOME (.975192, paired HUD/world anchors). The CLI discarded
 this final observation. Repair consumes it once only for LOADING_TIMEOUT, matching
 explicit serial/boot, persisted image, no cancellation, and within existing120s
 total/30step bounds. No added wait/input, global timeout increase or promo detector
 changes. Other failures/overlays/late/identity-changed evidence stay blocked.
-8:Member batch now2, with two free rows and one received row. The new strict full
 small2 glyph qualifies the original live red badge; mixed rows cannot imply empty.
-11:Mail Guild now8. Add the entire small8 badge, kept distinct from25/12 and other
 red/partial evidence. No account-specific coordinates or lower thresholds.
-9:Bounty board remains outside the qualified recovery routes; preserve external
 running ownership while awaiting the user's navigation choice.

Next resume must use20260930-075232-614988Z and explicitly preserve138. Protect all
207 current journal rows (through223), including the16 newly VERIFIED actions.
Fresh code requires focused regressions, full CI and latest Desktop delivery first.


Offline gate for this narrow continuation:188 recovery/Guild/Mail/resume/exception
checks passed;34 final-capture and saved-visual checks passed after final review.
Affected-file Ruff and diff whitespace check passed. Self-review: only a current
positive Home observation with unchanged explicit identity can settle a loading
timeout; no new wait, input, retry or threshold change. Whole2/8 badge templates
remain current-control-bound and reject partial/conflicting counts. All207 journal
rows are untouched. The three fixtures and two runtime crops contain only game UI
and image PNG chunks; no credentials, private metadata or unrelated diagnostics.


## Latest acceptance checkpoint — 2026-09-30

See [full per-account continuation report](PHASE7-CONTINUATION-20260930.md).
Fresh b0e95d6 / CI36692428131 / artifact11088276400 delivered608 verified files.
Resume20260930-093554-154579Z processed8/8;7 COMPLETE,3 new VERIFIED224–226.
All207 previous rows unchanged;138 remains RESERVED/POSSIBLE as the explicit
accepted exception. Current journal baseline210 rows. Only Mini Quin remains
blocked on an externally opened non-Home bounty board; ZERO input sent.
The user's manual-Home/qualified-Back choice is still pending. Do not rerun
completed accounts or label Phase7 PASS. Preserve external1/9 running states,
all names and Protection; all selections restored. No Phase8.
