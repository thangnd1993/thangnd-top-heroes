# Top Heroes Auto Manager — Claude instructions

The user is a non-developer ("vibe coder"). Work autonomously, report in plain language, ask only for real
permission / credential / destructive-action decisions. `AGENTS.md` and `docs/SAFETY.md` remain authoritative for
the detailed safety history; this file is the short enforceable summary. Do not start Phase 9.

## Environment facts (verify with `python tools/dev.py env`, never assume)
- Windows paths in the docs (`D:\Projects\...`, `C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\logs`,
  `C:\Users\ADMIN\Desktop\app`, `D:\LDPlayer\LDPlayer9`) exist only on the user's PC. Cloud/Linux sessions cannot read
  them, cannot run LDPlayer, and cannot build or validate the Windows exe. Say so; don't retry.
- The Windows build/smoke gate is GitHub Actions `windows.yml` (push to listed branches, or `workflow_dispatch`). It takes ~35-65 min.
- GitHub: use `gh` (works via API token) or the GitHub MCP tools. Never print tokens.

## Commands (one each)
- Setup: `python tools/dev.py setup` (creates `.venv`, installs `-e .[dev]`)
- Targeted tests: `python tools/dev.py test tests/test_x.py [more]` (no args = tests mentioning changed source files)
- Full suite: `python tools/dev.py full` (~20 min on 4 cores, parallel). On Linux ~15 tests fail only because they
  need Windows paths/OCR (`test_foundation display_icon`, `test_optional_instance_metadata`, `test_stable_identity_plan
  disk_recreation`, `test_run20_repairs vip-disabled`, `test_vip_countdown`, `test_vip_saved_reconcile`); Windows CI is the judge.
- Pre-commit gate: `python tools/dev.py check` (ruff, `git diff --check`, credential scan, guarded-file notice)
- Diagnostics from a real run (on the user's PC): `TopHeroesAutoManager.exe diagnostic-export --screenshots`
  → zip in `%LOCALAPPDATA%\TopHeroesAutoManager\exports\`

## LDPlayer safety (never violate)
- Never rename an instance; never write/restore/normalize a display name or LDPlayer config. Names are display-only labels,
  never identity, protection, journal, ADB, lifecycle, ownership or resume keys.
- Identity = installation namespace + Multi index + verified non-name backing-file identity; explicit indexed ADB/boot/PID proves
  the runtime. No default / first-device / index-0 fallback; no `quitall`/broadcast/global operations.
- Never send input to a Protected instance (Queen is Protected). Re-check Protection before every consequential action.
- Unrelated instances starting/stopping/renaming must not interrupt a valid target; never restore another instance's state or selection.
  Scope ownership and cleanup to the run's own target; external-running instances stay running.
- Free rewards only. Never spend money, diamonds, tickets, premium items. Technology/Guild donation is WOOD only.
  Never enter Sảnh Thí Luyện. `UNKNOWN` screen = no gameplay input; no blind coordinate gameplay.

## Reward correctness
- Discover red/numbered badges and enabled free `NHẬN`/`MIỄN PHÍ`/`NHẬN NHANH` controls (also those without badges); inspect all
  tabs/submenus of a feature in ONE visit; prefer qualified bulk actions (e.g. Cống Hiến Nhanh, Đọc Nhanh, Gửi Nhanh).
- Tầm Bảo: collecting finished missions ≠ dispatching new ones (`Gửi Nhanh`).
- Dispatched ≠ verified. Never repeat a POSSIBLE or VERIFIED claim. Never turn BLOCKED/UNKNOWN into NOT_AVAILABLE.
  Never delete/reset/rewrite journals or evidence; reconcile with an auditable process.
- A failing feature must not skip independent safe features; stop input only when target identity, Protection, transport or screen safety is lost.
- Account-first orchestration: finish all enabled authorized flows for one account, then cleanup, then the next. Two workers max,
  each owning exactly one target.

## Development discipline
- Reproduce before fixing when evidence exists; add a regression test that recreates the failure; smallest coherent fix.
- Don't lower thresholds/timeouts globally to hide defects. Don't add redundant inventory scans, screenshots or sleeps.
- Targeted tests while editing; full suite + CI once at integration. Check the real CI result (`gh run list`, `gh run view`) before saying "release-ready".
- Unit tests/CI are never real-game acceptance; runtime acceptance needs a user run, then `/analyze-run`.
- Never delete user data, logs, journals, screenshots, diagnostics. Never commit logs, `*.sqlite3`, screenshots, tokens.
- Commit/push only to the designated branch; no PR unless asked. Don't touch the Desktop app unless the environment can actually reach it.

## Hybrid Windows workflow (only when Computer Use / native Windows is really available)
- Computer Use = desktop and app UI only (launch exe, read version, LDPlayer Multi, dialogs, app Start/Stop/Export). Gameplay = the production
  app's verified index + ADB path only. One controller per target; never click inside an emulator the app is driving.
- Read-only preflight per target: `TopHeroesAutoManager.exe diagnostic verify-target --index N` (no input/lifecycle/selection/name writes).
- Full procedure: `/windows-hybrid-run`.

## Skills (in `.claude/skills/`)
`/analyze-run` newest run → ranked defects with evidence · `/fix-regression` confirmed defect → test → fix · `/release-app` gates → artifact → Desktop
· `/windows-hybrid-run` real run with Computer Use + verified ADB.

## Hooks (`.claude/settings.json`, fast, local-only, no network)
- After editing a `.py` file: ruff on that file; reminder when a safety-critical file changed.
- Before `git commit`: blocks on credential-shaped additions, private/runtime files, or `git diff --check` errors.
