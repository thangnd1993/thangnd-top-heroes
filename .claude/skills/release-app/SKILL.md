---
name: release-app
description: Prepare and verify a Windows release of Top Heroes Auto Manager - clean tree, tests, CI artifact, packaged version metadata, and (only when the Windows Desktop is actually reachable) replacement of the Desktop exe while keeping the previous build until the new one passes. Use when the user asks to build, deliver or ship the app.
---

# Release the app

1. **Preconditions.** `python tools/dev.py env`; `git status` must be clean (commit first, designated branch only); `python tools/dev.py check`.
2. **Gates.** Windows validation is GitHub Actions only (a Linux/cloud build never validates the Windows exe):
   `gh workflow run windows.yml --ref <branch>` (if not auto-triggered), then wait with `gh run watch <id>` / `gh run view <id> --json status,conclusion,headSha`.
   Require: conclusion `success` AND `headSha` == `git rev-parse HEAD` AND steps lint, pytest, PyInstaller, smoke test, "Verify packaged version metadata" all green.
3. **Metadata.** The CI log line `Packaged: <version> <commit> <date> CI Release` must show the full HEAD commit and today's UTC date. If missing/unknown, not releasable.
4. **Artifact.** `gh run download <id> -n TopHeroesAutoManager-Windows-x64 -D <scratch>`; record artifact id, zip SHA-256 (`digest` in `gh api repos/{owner}/{repo}/actions/runs/<id>/artifacts`), file count.
5. **Desktop delivery — only if `C:\Users\ADMIN\Desktop\app` is reachable** (`env` shows true; otherwise say "not delivered" and give the user the artifact link
   + manual steps). Keep the previous build until the new exe starts (`TopHeroesAutoManager.exe --version-file <tmp>` matches HEAD). Then, inside that exact folder
   only, remove older Top Heroes builds/ZIPs so at most two newest verified versions remain (prefer one). Resolve paths before any recursive delete; preserve
   unrelated files, user data, journals, diagnostics, screenshots, checkpoints.
6. **Label honestly.** Release = "CI-validated build". Real-game acceptance stays PARTIAL until the user runs it and `/analyze-run` confirms; never write PASS/ACCEPTED from CI alone.
7. **Report:** commit, run URL + conclusion, artifact id + SHA-256, displayed version/commit/release date, delivery status (done / not reachable), remaining limits.
