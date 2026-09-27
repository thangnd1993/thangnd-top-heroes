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
