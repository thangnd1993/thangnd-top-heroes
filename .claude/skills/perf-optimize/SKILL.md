---
name: perf-optimize
description: Measure and reduce Top Heroes Auto Manager run time from real evidence - per-account/per-flow timing, redundant captures, OCR, inventory/identity commands, navigation and waits - without weakening guards. Use when the user asks to speed the app up.
---

# Performance work

1. Baseline from the newest run (`/analyze-run`): `account-report.json` -> `timing_seconds` (startup, per flow, cleanup) and `operation_metrics` / `transport_metrics`
   (calls + seconds + exclusive_seconds per category: command_inventory, command_identity_or_other, command_capture, recovery_detection, detection, ocr,
   ocr_cache_hit, deliberate_wait). Inclusive stages nest - rank by `exclusive_seconds`.
2. Reproduce offline: profile with `cProfile` on saved frames (`tests/fixtures/...`, run screenshots) using `RecoveryScreenDetector().detect(ScreenshotService(...).take(...))`.
   Count duplicate work first (same anchor/region searched twice in one frame) before inventing a cache; a cache that does not move total time is not kept.
3. Acceptable: skipping provably redundant identical reads, reusing results within one frame, ordering cheap checks before expensive ones, replacing fixed sleeps with
   state polling, removing repeated feature entry. Not acceptable: global timeout/threshold cuts, skipping identity/Protection/postcondition checks, blind waits shortened without evidence.
4. Keep bounded retries and fail-closed behaviour. Add a test asserting the saved work (command counts or call counts) and that the guard sequence is unchanged.
5. Report before/after numbers with their source (real run seconds vs offline benchmark). Offline numbers are not wall-clock claims.
