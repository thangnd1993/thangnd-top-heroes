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

No Phase 7 reward actions have been dispatched yet.

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

Reference-image qualification is not real acceptance. No Phase 7 emulator
activity yet. Next: full CI, verified Desktop artifact, random bound acceptance,
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
