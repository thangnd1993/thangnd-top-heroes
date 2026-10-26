---
name: analyze-run
description: Analyze the newest real Top Heroes Auto Manager run (diagnostic zip, fleet report, logs, journal) and rank missed rewards, navigation failures, slow stages, ADB/startup failures and wrong verification with evidence. Use when the user says they ran the app, or asks why rewards were missed or the run was slow.
---

# Analyze the newest run

1. **Locate evidence (never assume).** Run `python tools/dev.py env`. Look in this order: a diagnostic zip the user attached or placed in the
   repo/scratchpad (`diagnostics-run<N>-*.zip`); `%LOCALAPPDATA%\TopHeroesAutoManager\{logs,diagnostics\tasks\automation,exports}` if reachable;
   committed fixtures/docs. If only Linux/cloud is available and nothing was provided, STOP and give the user the exact command:
   `TopHeroesAutoManager.exe diagnostic-export --screenshots` (or button "Xuất gói chẩn đoán") and ask for the zip. Do not fabricate.
2. **Identify the run.** Run ID, origin, start/end time, worker count, exact exe build: `manifest.json` → `version` (commit, release_date, ci_run);
   compare with `git log` and the latest CI (`gh run list`). If the run's commit ≠ the newest delivered build, say so. Never substitute an older
   run without labelling it older, and match by run ID / `run=N` log tags, not by file modification time.
3. **Read** `reports/fleet-report.json`, each `reports/<index>/account-report.json` (flows, rewards, transitions, blockers, `timing_seconds`,
   `operation_metrics`, `transport_metrics`), `logs/app-run<N>.log`, `timings.json` (per-stage % of wall, real worker overlap) and
   `journal-snapshot.json`. Open blocked-evidence screenshots (`screenshots/`) with the Read tool.
4. **Build the defect table:** `Index | Feature | Evidence (file+field/line/capture) | Failure | Root-cause hypothesis | Impact | Recurrence`.
   Check: menus with badges never entered; eligible `NHẬN`/`MIỄN PHÍ` seen but not dispatched; dispatched-but-unverified (POSSIBLE);
   verification that rests only on a popup; startup/ADB failures (`TransportResolutionError`, ABSENT serial); repeated entries of one feature;
   independent flows skipped after a recoverable error; stage time share (recovery recognition, OCR, inventory, identity, waits); two-worker overlap.
5. **Rank** by impact (rewards lost, then time lost) and recurrence across accounts. Distinguish *code defect* from *safety lock working as designed*
   (POSSIBLE/VERIFIED locks, WOOD-only, Protected) — locks are not defects.
6. **Report** concisely, in plain language, with evidence links. Offer `/fix-regression` for each confirmed defect. Do not change code in this skill.
