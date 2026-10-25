---
name: windows-hybrid-run
description: Run and observe the real Top Heroes Auto Manager on the user's Windows PC using Computer Use for the desktop/app UI and the app's own verified LDPlayer-index + ADB path for the game. Use only when the user explicitly authorizes a real run AND this session actually has Windows Computer Use or a native Windows shell.
---

# Hybrid Windows run (Computer Use for the desktop, verified ADB for the game)

## 0. Prove capability first — never pretend
- `python tools/dev.py env`: `windows_paths` must be true for the app, logs and LDPlayer. Check that Computer Use tools
  (`mcp__computer-use__*` or `mcp__remote-devices__computer_*`) are actually listed. If either is missing: stop, say exactly what is
  missing, and fall back to "user runs the app, sends the diagnostic zip" (`/analyze-run`). Do not retry inaccessible paths.

## 1. Controllers (one per target, never mixed)
- **Computer Use** may only: open the production exe, read its version card, open LDPlayer Multi to look, read unexpected Windows/Android
  dialogs, press the app's own Start/Stop/Export buttons. It never clicks inside an emulator window while the app owns that target.
- **Gameplay** is performed only by the production app (its Start button) through `Manager`: Multi index → live Protection → stored
  non-name disk identity → LDPlayer-indexed serial → boot-id equality on the transport → fresh screenshot → classification → input →
  fresh post-condition → journal. No hand-written ADB tap scripts, no guessed serials/ports, no `adb kill-server`, no config edits.

## 2. Before Start (read-only)
1. Note the app version card (version · commit · release date); compare with `git rev-parse HEAD` / latest CI artifact.
2. `TopHeroesAutoManager.exe diagnostic list` — live inventory, Protection, identity state (names are informational only).
3. For each intended target: `TopHeroesAutoManager.exe diagnostic verify-target --index N` — read-only identity + indexed ADB + one
   screenshot + classification + timings. A `PROTECTED_TARGET` / `TARGET_IDENTITY_AMBIGUOUS` / `ADB_UNAVAILABLE` result excludes that target
   only; record the reason and continue with others. Never launch, select, protect, rename or "fix" anything to make it pass.

## 3. Run
- In the app: scope + concurrency 2 (two distinct eligible non-Protected targets), press **Bắt đầu tự động**, record the run ID from the dashboard.
- While it runs, Computer Use only observes (dashboard, warning banner, live progress). Use the app's **Dừng tự động** if a safety issue appears.
  Do not touch other instances; the user may still use them.

## 4. Evidence and repair
- After the run: press **Xuất gói chẩn đoán** (or `diagnostic-export --run <id> --screenshots`), then `/analyze-run` on that zip, then
  `/fix-regression` per confirmed defect, then `/release-app`. Never repeat an uncertain (POSSIBLE) claim to "re-test" it; a verification
  run is allowed only within the same authorization and journal locks.
- Report the exact run ID, accounts processed, VERIFIED vs dispatched-unverified, blocked reasons, per-stage timings and worker overlap.
  Phase 8 is PASS only with every enabled route terminal and verified on the real app.
