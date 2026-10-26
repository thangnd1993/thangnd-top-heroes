---
name: fix-regression
description: Fix one confirmed Top Heroes Auto Manager defect safely - trace the code, write a regression test that reproduces it, make the smallest coherent fix, and verify Protected isolation, journal locks, verification rules and performance. Use after /analyze-run or when the user reports a concrete failure.
---

# Fix a confirmed defect

Precondition: a defect with evidence (log line, report field, screenshot, fixture). If there is none, run `/analyze-run` first.

1. `git status`, `git log -3`; read `CLAUDE.md` safety rules and the matching checkpoint in `docs/` (e.g. latest `OCT*_*REPAIR.md`).
2. **Trace** the production path (Grep → Read only the relevant functions). Name the root cause, not the symptom.
3. **Reproduce** with a failing test that recreates the original condition, preferably from saved fixtures (`tests/fixtures/run*/`) or the report
   JSON. Run it and confirm it FAILS for the right reason: `python tools/dev.py test tests/test_<name>.py`.
4. **Fix minimally.** Forbidden: global threshold/timeout increases, blind coordinates, weakening duplicate prevention, converting UNKNOWN/BLOCKED
   into NOT_AVAILABLE, rewriting journals, name-based identity, touching Protected handling or LDPlayer config writers without an explicit reason.
5. **Verify:** the new test passes; related suites (`python tools/dev.py test` with no args picks tests that mention the changed modules);
   confirm explicitly: Protected isolation intact, POSSIBLE/VERIFIED locks intact, dispatched≠verified preserved, no extra inventory/capture/sleep
   added on the hot path. Run `python tools/dev.py check`.
6. Batch related fixes; run `python tools/dev.py full` (compare failures to the known Linux-only list in CLAUDE.md) before pushing; push only to the
   designated branch; check real CI with `gh run list`/`gh run view`. Never claim the gameplay defect is fixed — only that the code path and test are.
7. **Summarize:** defect, root cause, files changed, test added (and that it failed before), checks run with results, what still needs a user run.
