# Phase 7 — Guild and Mail

Status: implementation and offline qualification in progress. Not accepted yet.
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
