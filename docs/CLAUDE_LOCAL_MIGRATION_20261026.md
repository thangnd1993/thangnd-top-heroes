# Claude Cloud → Local migration audit (2026-10-26)

Local Claude Code session on the user's Windows PC. No gameplay, no LDPlayer start/stop/selection change, no claim, no ADB device command, no Desktop replacement.

## 1. State before any change (re-verified, not assumed)

| Item | Value |
|---|---|
| Branch / HEAD | `codex/phase8-dynamic-events` @ `8c89e9a4485cf984c96721ef182aadf3e39b099f`, equal to `origin/codex/phase8-dynamic-events` (0/0) |
| Modified (user WIP, preserved, not staged) | `.github/workflows/windows.yml`, `src/top_heroes_auto/app/build_identity.py`, `src/top_heroes_auto/ui/window.py` (the three are CRLF on disk, LF in git, so `git diff` looks like a whole-file rewrite; `--ignore-space-at-eol` shows the real change) |
| Untracked (user WIP, preserved) | `src/top_heroes_auto/app/release_metadata.py` |
| Stash | `stash@{0}` "On codex/phase6-vip-pack-recruit: paused shop period reconciliation before no-rename safety task" — untouched |
| Journals, logs, diagnostics, screenshots, settings, existing skills | untouched (user Claude dir has no skills; project memory dir empty) |

Changes made by this session (all uncommitted): `service.py` (run21 repair, from the previous task), `tests/test_run21_repairs.py`, `docs/OCT25_RUN21_REPAIR.md`,
two Ruff import fixes in the user's `window.py` (unused `QFrame`, import order), and the migration files in section 6. `git fetch origin --prune` was run (read-only).

## 2. Cloud material actually recovered

Cloud conversations are private and **not accessible** from this session; they cannot be read through Git. What *is* accessible is what the Cloud session pushed.

| # | Source | What | Status |
|---|---|---|---|
| 1 | `origin/claude/vibrant-dirac-clye1a` (5 commits, 2026-10-25, author "Claude", base = `8c89e9a`) | `CLAUDE.md`, 4 skills (`analyze-run`, `fix-regression`, `release-app`, `windows-hybrid-run`), `.claude/settings.json` hooks, `tools/dev.py`, `tools/write_build_info.py`, `version_info.py`, dashboard/run-progress UI, diagnostics export, `diagnostic verify-target`, adjacent-inventory coalescing, `docs/OCT25_DASHBOARD_PERF_REPAIR.md` + 7 tests files | **Recovered and inspected; NOT merged** (see 4) |
| 2 | Same branch, `.claude/skills/*` | 4 skills inspected: benign instructions only | Recovered; **adapted** (not copied) into local skills |
| 3 | Same branch, `.claude/settings.json` + `tools/dev.py hook` | PostToolUse ruff on edited `.py`, PreToolUse `git commit` secret/whitespace scan; local-only, no network | Inspected, benign. **Not activated** (arrives with the branch merge; copying would make a later merge refuse untracked files) |
| 4 | Desktop app `C:\Users\ADMIN\Desktop\app\TopHeroesAutoManager\` | exe sha256 `0780b169…8d42`, packaged `build-info.json`: commit `493bd39c…1d`, ci_run `40216208278`, release_date 2026-10-25, channel `ci-release` | Recovered and verified (see 5): the installed app is the **Cloud branch build**, not `8c89e9a` |
| 5 | Same folder `provenance.json` | still says run `40088053262`, commit `8c89e9a`, exe `592f285a…` | **Conflicting/obsolete** — stale, does not match the installed exe. Left untouched |
| 6 | `C:\Users\ADMIN\Downloads\TopHeroesAutoManager-Windows-x64.zip` | sha256 `e4d40561…fc25` = GitHub digest of artifact `12608573673` (run 40216208278); its exe equals the installed exe | Recovered and verified. (Also an extracted folder with the same name; not inspected further) |
| 7 | `C:\Users\ADMIN\Downloads\top_heroes_complete_repair_prompt.txt` (30 KB, 2026-10-16, Codex-era) | an older repair prompt (Guild Technology, Monthly Nhận, delays). Treated as **data**; nothing copied | Present locally; obsolete (these items are covered by `docs/OCT21…OCT24` checkpoints) |
| 8 | `AGENTS.md`, `docs/*.md` (PHASE8, SAFETY, PROGRESS, OCT21/23/24/25 repairs, codex-agent-workflow) | project decisions | Already present locally |
| 9 | Cloud-only: private chat history, any claude.ai Project instructions or custom skills not pushed to Git | — | **Missing; requires manual export** (see 9) |

## 3. Skills

| Skill | Status |
|---|---|
| `continue-project`, `reward-automation`, `perf-optimize`, `runtime-acceptance` | **new** in `.claude/skills/` (no Cloud equivalent for the first three; `runtime-acceptance` splits the acceptance rules of `analyze-run`) |
| `analyze-run`, `fix-regression`, `release-app`, `windows-hybrid-run` | **adapted** from the Cloud versions: Cloud-only assumptions removed (`tools/dev.py`, `diagnostic-export`, Linux notes), local run-21 facts and the delivery script added |
| User-level skills (`~/.claude/skills`) | none existed; none installed; no duplicates |
| Session-provided generic skills (`code-review`, `run`, plugins) | available, not project-specific; unchanged |

## 4. Conflicts (not silently resolved)

1. **Two release-metadata implementations.** Working tree: uncommitted `release_metadata.py` (+ `window.py`/`build_identity.py`/`windows.yml` edits; expects `built_at`, `channel: "CI Release"`).
   Cloud branch: `version_info.py` + `tools/write_build_info.py` (writes `release_date`, `release_timezone`, `channel: "ci-release"`). The installed build's `build-info.json` uses the Cloud
   schema, so the local `release_metadata.py` would display **UNKNOWN** for it. Overlapping files with the Cloud branch: `windows.yml`, `build_identity.py`, `service.py`, `window.py`.
   `git merge-tree` of committed HEAD vs the branch is conflict-free; the conflict is with the uncommitted work. **Decision needed from the user** (recommended: keep the Cloud schema, drop or port the local WIP).
2. `AGENTS.md` "one Codex agent" vs Claude Code doing the work — same step sequence applies; recorded in `CLAUDE.md`.
3. `AGENTS.md` "leave only the newest app in the Desktop folder" vs rollback requirement — resolved by moving the old build to `%LOCALAPPDATA%\TopHeroesAutoManager\release-backups\` (two kept), nothing deleted from Desktop beyond the replaced build.
4. Concurrency default one vs two (2026-10-14/19 authorisation) — two applies only to the final normal-UI Start.
5. `Protected`: AGENTS.md "never mutate" vs brief "automation must not act; user may open/close manually" — consistent (automation rule); wording recorded in `CLAUDE.md`.
6. Run evidence: the Cloud doc analysed **run 20** only; the newest real run is **run 21** (built from `8c89e9a`), analysed in `docs/OCT25_RUN21_REPAIR.md`. The installed app (493bd39) has not been run yet.

## 5. Verified capabilities (each actually tested here)

| Capability | Result |
|---|---|
| Local files + PowerShell + Git + `gh` (authenticated as `thangnd1993`) | verified |
| Python 3.12.10, `.venv`: pytest 9.1.1, Ruff 0.16.8, PySide6 6.11.2, NumPy 2.5.3, OpenCV 4.14.0, PyInstaller 6.22.3, project installed editable | verified (`pip check` clean) |
| CI/Windows build config | `windows.yml` present; CI run 40216208278 on the Cloud branch = success (lint, tests, PyInstaller, smoke) |
| LDPlayer read access | `ldconsole list2` listed 13 instances (none running) — verified in the earlier audit; not repeated |
| ADB | `adb.exe` 34.0.4 runs; `adb devices` empty, so **no verified indexed transport for any instance** |
| Computer use | tools exist, **no application granted** (`list_granted_applications` empty); not enabled, not tested |
| Authorization to send gameplay input | **not granted** in this task |
| Artifact verification | `scripts/deliver_desktop.ps1` dry run against run 40216208278 + the Downloads zip: run success, head SHA = expected, zip sha256 = artifact digest, packaged commit = head, `--smoke-test` exit 0, staged exe hash = installed exe hash. Desktop untouched |

Tests: Ruff clean; full suite (started in the run-21 repair task, tree = run-21 repair + the user's uncommitted files, before the migration files were added) **2185 passed, 6 skipped in 1953 s**; the 10 new run-21 tests are included. The migration files add no Python under `src/` or `tests/`. Not re-run for this migration. The PyInstaller build was not run locally (CI is the build gate).

## 6. Files added in this migration (nothing deleted, nothing overwritten)

- `CLAUDE.md` — imports `AGENTS.md`; local environment, consolidated permanent requirements, capability tiers, reported conflicts.
- `.claude/skills/{continue-project,analyze-run,fix-regression,reward-automation,perf-optimize,release-app,runtime-acceptance,windows-hybrid-run}/SKILL.md`.
- `scripts/deliver_desktop.ps1` — verified delivery with staging, checksum/provenance checks, smoke tests, rollback, two backups kept; dry run unless `-Apply`; never stops a running app.
- This report. `AGENTS.md` was **not** modified (newer, more specific project decisions stay authoritative).

## 7. Release workflow readiness

Ready: artifact identity/digest/commit/smoke verification and rollback script (dry run proven). Not ready: (a) a CI artifact for the *local* tree — requires commit+push, not authorised;
(b) the version-display decision (conflict 1); (c) `-Apply` has never been executed (deliberately, the installed build is already a verified CI artifact).

## 8. Outstanding tasks

1. Decide: merge/rebase `origin/claude/vibrant-dirac-clye1a` (brings dashboard, diagnostics export, `verify-target`, hooks, `tools/dev.py`) and what to do with the uncommitted `release_metadata.py` WIP.
2. Authorise commit/push of the run-21 repair (`service.py` + tests + docs) so CI can build it.
3. Grant computer use for Top Heroes Auto Manager / LDPlayer if hybrid observation is wanted.
4. Run the installed app yourself, then `/runtime-acceptance` on the new run; decide the Treasure Hunt POSSIBLE-claim locks (docs/OCT25_RUN21_REPAIR.md D3).
5. Fix or delete the stale `provenance.json` beside the installed exe (not touched here).

## 9. Cloud-only material that needs manual export

Private Cloud conversations, claude.ai Project knowledge/instructions, and any Cloud-side custom skills never pushed to Git. If you want them preserved, export them from claude.ai and place the files in a folder under the project; they will then be inspected as data before use.

## 10. Merge result (isolated worktree, 2026-10-26)

- Worktree `D:\Projects\thangnd-top-heroes-merge`, branch `claude/local-merge`, created from `8c89e9a`; `origin/claude/vibrant-dirac-clye1a` (5 commits `f3b78ad`, `1196104`, `2ae84a5`, `493bd39`, `0681cbf`) merged with `--no-ff`. Not pushed.
- The merge itself was conflict-free because the Local WIP is uncommitted in the original tree and was NOT carried over wholesale. Resolutions: `windows.yml` / `build_identity.py` / `window.py` = Cloud versions
  (`tools/write_build_info.py` + `version_info.py` + dashboard/version card); `service.py` = Cloud adjacent-inventory **plus** the Local run-21 repair (`ADB_RESOLVE_TIMEOUT` 90 s, Stop-aware transport wait, `_capture_png` retry).
- Not reapplied from the Local WIP (kept in the original tree and in `D:\Projects\thangnd-wip-backup-20261026`): `release_metadata.py` (superseded; its `built_at`/`"CI Release"` schema is not what the installed build writes) and the tab-based
  `window.py` layout (different design from the Cloud dashboard that 4 Cloud test files cover; can be revisited as a separate change).
- Skills: the 4 overlapping Cloud skills kept (they match the merged code) with `release-app` updated to use `scripts/deliver_desktop.ps1`; 4 new Local skills added. `CLAUDE.md` reconciled from both. Cloud originals remain in Git history.
