# Top Heroes Auto Manager — Claude instructions

The user is a non-developer ("vibe coder"). Work autonomously, report in plain language, ask only for real
permission / credential / destructive-action decisions. `AGENTS.md` and `docs/SAFETY.md` remain authoritative for the detailed
safety history; this file is the short enforceable summary. Do not start Phase 9.
(Reconciled 2026-10-26 from the Cloud `CLAUDE.md` on `origin/claude/vibrant-dirac-clye1a` and the Local migration; see `docs/CLAUDE_LOCAL_MIGRATION_20261026.md`.)

## Environment facts (verify with `python tools/dev.py env`, never assume)
- **Local Windows mode (current):** `D:\Projects\thangnd-top-heroes`, `.venv` (Python 3.12, pytest, Ruff, PySide6, NumPy, OpenCV, PyInstaller, project installed editable),
  LDPlayer `D:\LDPlayer\LDPlayer9` (`ldconsole.exe`, bundled `adb.exe`), Desktop app `C:\Users\ADMIN\Desktop\app\TopHeroesAutoManager\`,
  app data `%LOCALAPPDATA%\TopHeroesAutoManager\{logs,diagnostics,artifacts,screenshots,exports,config.sqlite3}` (read-only for diagnosis; never delete).
- **Cloud/Linux sessions** cannot read those paths, cannot run LDPlayer and cannot validate the Windows exe. Say so; don't retry.
- The Windows build/smoke gate is GitHub Actions `windows.yml` (listed branches or `workflow_dispatch`, ~35-65 min). Use `gh` (authenticated); never print tokens.

## Commands (one each)
- Setup: `python tools/dev.py setup` · Targeted tests: `python tools/dev.py test tests/test_x.py` (no args = tests mentioning changed source files)
- Full suite: `python tools/dev.py full` (~20-35 min; run once at integration). On Linux ~15 tests fail only because they need Windows paths/OCR; Windows CI is the judge.
- Pre-commit gate: `python tools/dev.py check` (ruff, `git diff --check`, credential scan, guarded-file notice)
- Equivalent direct form: `.venv\Scripts\python.exe -m pytest <paths> -q` with `QT_QPA_PLATFORM=offscreen`.
- Real-run diagnostics: `TopHeroesAutoManager.exe diagnostic-export --screenshots` → zip in `%LOCALAPPDATA%\TopHeroesAutoManager\exports\`.
- Delivery to the Desktop: `scripts/deliver_desktop.ps1` (dry run by default; see `/release-app`).

## LDPlayer safety (never violate)
- Never rename an instance; never write/restore/normalize a display name or LDPlayer config. Names are display-only labels,
  never identity, protection, journal, ADB, lifecycle, ownership or resume keys.
- Identity = installation namespace + Multi index + verified non-name backing-file identity; explicit indexed ADB/boot/PID proves the runtime.
  No default / first-device / index-0 fallback; no `quitall`/broadcast/global operations.
- *Protected* (Queen) = automation must never act on that account; re-check before every consequential action. It does not stop the user opening/closing it manually.
- Unrelated instances starting/stopping/renaming must not interrupt a valid target; never restore another instance's state or selection.
  Scope ownership and cleanup to the run's own targets; external-running instances stay running.
- Free rewards only. Never spend money, diamonds, stones, tickets, premium items. Technology/Guild donation is WOOD only (prefer the authorized quick donation).
  Never enter Sảnh Thí Luyện unless explicitly authorized. `UNKNOWN` screen = no gameplay input; no blind coordinate gameplay.

## Reward correctness
- Discover red/numbered badges and enabled free `NHẬN`/`MIỄN PHÍ`/`NHẬN NHANH` controls (also without badges); inspect all tabs/submenus of a feature in ONE visit;
  prefer qualified bulk actions (Cống Hiến Nhanh, Đọc Nhanh, Gửi Nhanh).
- Tầm Bảo: collecting finished missions ≠ dispatching new ones (`Gửi Nhanh`).
- Dispatched ≠ verified (fresh screenshot + independent postcondition). Never repeat a POSSIBLE or VERIFIED claim. Never turn BLOCKED/UNKNOWN into NOT_AVAILABLE.
  Never delete/reset/rewrite journals or evidence; reconcile only with an auditable process.
- A failing feature must not skip independent safe features; stop input only when target identity, Protection, transport or screen safety is lost.
- Account-first orchestration: finish all enabled authorized flows for one account, then cleanup, then the next; stay in the current task's scope, do not replay unrelated flows.
  Two workers max, each owning exactly one target (two only for the user-run final normal-UI Start; default is one).
- A phase is not complete while supported eligible rewards remain uninspected or unresolved.

## Development discipline
- Reproduce before fixing when evidence exists; add a regression test that recreates the failure; smallest coherent fix. Don't lower thresholds/timeouts globally;
  don't add redundant inventory scans, screenshots or sleeps. Optimise from measured timings.
- Keep routine logs quiet; retain warnings, errors, decisions, claim dispatches and verification results. The UI shows version, commit and release date.
- Targeted tests while editing; full suite + CI once at integration. Check the real CI result (`gh run list`, `gh run view`) before saying "release-ready".
- Unit tests/CI are never real-game acceptance; runtime acceptance needs a user run, then `/analyze-run` and `/runtime-acceptance`.
- Never delete user data, logs, journals, screenshots, diagnostics. Never commit logs, `*.sqlite3`, screenshots, tokens.
- Commit/push only when authorized and only to the designated branch; no PR unless asked. Don't touch the Desktop app except through `scripts/deliver_desktop.ps1` with the user's go-ahead.
- Some working files on the user's PC are CRLF while git stores LF; do not normalise them.

## Capability tiers (state which one you actually have)
1. Local files + PowerShell. 2. Screenshots/UI control (`mcp__computer-use__*`, needs `request_access` per app). 3. LDPlayer Multi read access (`ldconsole list2`).
4. Verified indexed ADB transport for one instance. 5. Authorization to send gameplay input — only from the user's chat. A lower tier never implies a higher one.
Gameplay is performed by the production app, not by ad-hoc ADB scripts.

## Hybrid Windows workflow (only when computer use / native Windows is really available)
- Computer use = desktop and app UI only (launch exe, read the version card, look at LDPlayer Multi, dialogs, app Start/Stop/Export). Gameplay = the production app's verified
  index + ADB path only. One controller per target; never click inside an emulator the app is driving.
- Read-only preflight per target: `TopHeroesAutoManager.exe diagnostic verify-target --index N` (no input/lifecycle/selection/name writes). Procedure: `/windows-hybrid-run`.

## Skills (`.claude/skills/`)
`/continue-project` · `/analyze-run` · `/fix-regression` · `/reward-automation` · `/perf-optimize` · `/release-app` · `/runtime-acceptance` · `/windows-hybrid-run`.

## Hooks (`.claude/settings.json`, fast, local-only, no network)
- After editing a `.py` file: ruff on that file; reminder when a safety-critical file changed. Before `git commit`: blocks credential-shaped additions, private/runtime files, `git diff --check` errors.

## Recorded conflicts and the active rule
- `AGENTS.md` "one Codex agent" vs Claude Code doing the work: the same step sequence applies.
- `AGENTS.md` "leave only the newest app in the Desktop folder" vs rollback: Desktop keeps one build; the previous build is moved to
  `%LOCALAPPDATA%\TopHeroesAutoManager\release-backups\` (two newest kept) by `scripts/deliver_desktop.ps1`.
- Version display: the Cloud `version_info.py` + `tools/write_build_info.py` implementation is active (it is what the installed build uses). The uncommitted Local `release_metadata.py` was not carried over.
