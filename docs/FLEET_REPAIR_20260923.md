# Post-trial repair — 2026-09-23

Scope: repair the first trial's journal/Idle/recovery blockers, starting at
`af5464c`. **No fleet rerun, no claim, no Phase 7.** Phase 6 remains PARTIAL.
Only `2 / 5-Emmmmm` was used for live debugging. Indices 4/5 were inspected
through existing files only; no configuration, names or account data changed.

## Journal

Old trial harness reserved the entire Idle task and retained its lock even on
pre-claim UNKNOWN or recovery timeout. Production also set its dispatch flag
only after the tap returned, losing uncertainty when transport raised.

New production Idle reservations explicitly begin `NOT_DISPATCHED`. After
current-frame/account/boot/selection/input validation, a durable `POSSIBLE`
marker commits immediately before claim transport. Pre-claim exits release
only `NOT_DISPATCHED` into an append-only audit. Dispatched uncertainty remains
RESERVED; verified postconditions remain VERIFIED. Legacy rows default UNKNOWN
and never auto-release. A crash does not imply no dispatch.

The one-shot offline audit matched the exact namespace/account/reservation,
outer and inner task IDs, completed production reports, explicit
`claim_dispatched=false`, empty action lists and pre-claim exit paths.
It released exactly IDs **1/2/3** (outer tasks **17/19/21**, inner **18/20/22**).
Original rows and SHA-256 evidence are retained in SQLite `reward_release_audit`.
No VERIFIED or uncertain dispatched claim was cleared.

- Backup: `diagnostics/fleet-repair-20260923/before-journal-repair.sqlite3`
- Audit result: `diagnostics/fleet-repair-20260923/journal-repair.json`
- Original fleet: `diagnostics/fleet-trial-20260923/live-report.json`

## Idle UNKNOWN: two demonstrated causes

1. Full-screen Stranger Things promo appeared after generic Home recovery.
   The old trial frame's portal score was **0.272747**. Production now reuses
   the existing qualified, cancellable, same-boot promo handler once on the
   initial frame, including an exact-promo-only timeout route. Other unknown
   popups receive no input. Post-claim observation never triggers this handler.
2. After one qualified Back, unobstructed Home still scored **0.764877** on the
   old portal template. That clean template included a changing progress ring
   and background. The stable blue portal core is now derived exactly from
   original template pixels `[27:67,22:62]`; the original asset remains intact.
   These are crop provenance, **not runtime tap coordinates**.

Production searches the entire current normalized frame, rejects multiple
portal matches and requires independent generic Home confirmation. Threshold
remains **0.9**. Two clean live frames taken three seconds apart qualify at
**0.942709 / 0.942707**; normalized bbox `(779,480,40,40)`, device bbox
`(480,461,40,40)` for this evidence only. Every runtime frame recomputes the box.

- Live report: `diagnostics/idle-repair-20260923-033741Z/report.json`
- Explicit serial: `emulator-5558`
- Boot: `795ab7d7-f412-480b-b487-f4a0b3addb6d`
- One qualified promo Back, zero reward/entry taps, zero claims.
- The live run correctly reported UNKNOWN before core qualification. The
  corrected production detector was then verified **offline on those clean
  live frames**, not represented as a second real gameplay/acceptance run.
- Before overlay/report: `diagnostics/fleet-repair-20260923/before-detection.json`
- After overlay/report: `diagnostics/fleet-repair-20260923/qualified-detection.json`
  and `qualified-0-overlay.png`, `qualified-1-overlay.png` in that directory.
- Owned index 2 stopped; selection restored; unrelated inventory unchanged.
  Protected 0/1/6/7 untouched. No lifecycle or ADB action on 4/5 or disabled clones.

## Recovery timeout

Saved final frames from index 4 and 5 show **Hỗ Trợ Dập Lửa Hội** (guild fire
assistance popup), not proven continued loading. No speculative close handler
was added. Recovery now persists bounded initial/10/20/40-second samples plus
a fresh final frame/state/per-anchor evidence on timeout; a failed final
capture is recorded without retry. Blank raw evidence is retained. The normal
observation cadence and existing timeout are unchanged.

The guild popup did **not** reproduce in this index-2 run: Android/loading/Home
recovery succeeded, followed by the separately verified promo. Consequently
the 4/5 popup remains an unsupported safe stop; do not use those accounts to
reproduce it without new explicit authorization.

- Existing index-4 final: AppData diagnostics/recovery/3-Chíp/
  `20260923-030020-216467Z/20260923-030219-823404Z-013-recovery.png`
- Existing index-5 final: AppData diagnostics/recovery/4-Em Pé/
  `20260923-030223-068254Z/20260923-030417-486729Z-011-recovery.png`
- New index-2 samples: AppData diagnostics/recovery/5-Emmmmm/
  `20260923-033741-498627Z/` (0/10/20/40 seconds; recovery SUCCESS).
- AppData diagnostics root is
  `%LOCALAPPDATA%/TopHeroesAutoManager/diagnostics/`.

## Validation and resume boundary

Targeted regressions cover release/audit, wrong run, legacy uncertainty,
dispatch exception, cancellation, safety block, exact three-row migration and
rollback/idempotence, promo cancellation/timeout, bounded final diagnostics,
movable/ambiguous/missing/stale portal and independent Home proof. No full local
suite/build was run. Full Windows lint/test/package/smoke is the branch CI gate;
its exact commit/run result is supplied in the completion handoff.

Reviewer: APPROVED, including the actual live-evidence-driven vision delta.
Developer child creation was unavailable (client thread limit); parent performed
implementation/validation and the configured reviewer provided independent review.

**Do not rerun fleet automatically.** No Phase 6 reward acceptance is implied.
Keep this evidence; no repeated VIP/Tiệm/BXH survey. The next multi-account
trial requires explicit user authorization. Unknown guild popup remains blocked.
