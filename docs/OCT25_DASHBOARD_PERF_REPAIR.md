# October25 — build metadata, dashboard, diagnostics export, measured performance

## Baseline (verified, not assumed)

- Branch `claude/vibrant-dirac-clye1a` fast-forwarded to `codex/phase8-dynamic-events` @ `8c89e9a`; clean tree, no stashes.
- CI for `8c89e9a`: run **40088053262 — success**. The two failures in run 40085034225 (`a15f8f6`, negative scroll tests with
  incomplete port doubles) are already fixed by `8c89e9a`.
- **Newest run available in this environment: run 20** (build `c2dac26`, 2026-10-24, see `OCT24_RUN20_REPAIR.md`).
  The user's newer Windows run is NOT available here; nothing below claims to fix a real gameplay failure from it.
- Phase 8 remains **PARTIAL**. No gameplay was run. Phase 9 not started.

## Changes

| Area | Change | Evidence / test |
|---|---|---|
| Build metadata | `tools/write_build_info.py` writes `assets/build-info.json` (version, 40-char commit, UTC `release_date`, channel, CI run). `app/version_info.py` validates and presents it; malformed/missing fields display `không rõ`, never invented. UI title, sidebar, dashboard card, run reports (`runtime.version_info`) use it. `--version-file` lets CI assert the packaged exe reports `GITHUB_SHA`. | `tests/test_version_info.py` |
| Dashboard | Version/commit/date, run id + elapsed, total/eligible/selected instances, active workers, finished accounts, VERIFIED claims since run start (`Store.run_dashboard`, read-only), warning banner for blocked items. Stop is a distinct red control. Advanced ADB/vision/trial tasks collapsed by default. | `tests/test_dashboard_and_bundle.py` |
| Live progress | Fleet `event()` log records now carry `ui_index/ui_flow/ui_state`; `OperationalLogHandler` forwards them; `RunProgress` shows real per-account flow state and done/blocked counts (no invented percentages). Structured error categories (`ui/run_progress.py`) align with the existing status model. | same |
| Logging | Main view still shows only warnings/operation outcomes with repeat-folding; full records stay in `logs/app.log`. | existing `test_complete_repair.py` |
| Diagnostics export | `diagnostic_bundle.export_bundle` / `diagnostic-export` CLI / "Xuất gói chẩn đoán" button: one zip with reports, run-tagged log lines, journal snapshot (read-only SQLite), per-account timing %, actual worker overlap, manifest with SHA-256 and declared missing evidence. Screenshots opt-in. Nothing deleted or rewritten. | same |
| Performance 1 | `Manager._target_inventory` reuses a read **only** when adjacent: same target, no command issued since (`Process.command_serial`), no deliberate wait since (`timing.wait_epoch`), < 250 ms. Selection/Protection are re-read by every guard. Transports that cannot count commands never coalesce. | `tests/test_adjacent_inventory.py` |

## Measurements (this Linux container; relative, NOT Windows wall-clock)

- **Command count, verified capture on the production guard path (FakeProcess with command counting):**
  24 commands / 16 `list2` → **16 commands / 8 `list2`**. Guarded tap: 3 → 2 `list2`. All non-inventory identity probes unchanged.
  Run20 attributed 181 s (inventory) + 151 s (identity) per account to these commands; the saving applies to the inventory share only.
- **Recognition profile on the saved Run20 frames** (`tests/fixtures/run20`): `cv2.matchTemplate` = 98 % of `RecoveryScreenDetector.detect`
  (157 calls, ≈77 ms each here); 36 % of it sits in `adventure_back_evidence` → `IdleRewardDetector.detect`. On busy frames 11–12 % of
  `matchTemplate` calls were exact duplicates (28/28 unique on one frame, 36/43 on three others).
- **Tried and reverted:** a per-frame memo of raw `matchTemplate` score maps. It removed 21 of 129 calls on three busy Run20 frames,
  but total `matchTemplate` time moved only 9.50 s → 9.39 s and a 4-frame end-to-end benchmark was 11.48/11.78 s (memo) vs 11.58/11.62 s
  (no memo), i.e. no measurable gain. Not kept: no demonstrated benefit for the added frame-identity invariant. The real recognition
  cost is the number of full-frame template scans per classification, which needs a vision-level redesign with real-frame validation.
- Wall-clock before/after on Windows is **not measured**. The "few minutes per healthy account" target is **not** claimed; run20 healthy
  accounts took 629–1225 s.

## Reviewed, deliberately not changed

- `DynamicEventExplorer.run` ends the whole traversal on an unrecoverable block or exception and marks remaining roots
  `GLOBAL_TRAVERSAL_BLOCKER`; run20 shows such roots with `visits=0` (e.g. index 5, 9). Recovery is limited to once per Event. Which exit
  caused each is not recoverable from the committed evidence, so no policy change was made blind. The new diagnostic bundle records the
  exact block sequence for the next cycle.
- Per-flow error isolation in `automation_fleet.execute_instance` already continues to the next independent flow after any `Exception`
  once `session.check()` passes.

## Files needed from the next Windows run

Run the new build, then `TopHeroesAutoManager.exe diagnostic-export --screenshots` (or the **Xuất gói chẩn đoán** button) and send the zip
from `%LOCALAPPDATA%\TopHeroesAutoManager\exports\`. It contains: `fleet-report.json` + every `account-report.json` and flow report,
`app.log` lines for that run, a read-only journal snapshot, `timings.json` (per-stage % of wall and real two-worker overlap),
BLOCKED-evidence screenshots, and `manifest.json` (build version/commit/date, SHA-256, missing evidence). If the zip is too large, send
without `--screenshots` first.
