# October26 normal application run23 — analysis and repair (build 383afd9)

## Evidence
- Run **23**, `normal-ui-start`, concurrency 2 (peak 2), targets #2 Emmmm and #3 Queen con.
  2026-10-26 09:49:21–09:57:45 UTC (16:49–16:57 Vietnam), result PARTIAL.
- Exe SHA-256 `95819489…0189`, commit `383afd9de1d3e9af298807b9ae3acc6a53c3537b`, CI 40293815565, the delivered build.
- Report `diagnostics\tasks\automation\20261026-094921-092012Z-80a1942c\`. Protected/names/selections unchanged, 0 name writes.
- Same reset period as run22, so most daily rewards were already VERIFIED (ALREADY_VERIFIED, no replay). New claims: 0.

## Proven in real gameplay
- **R22-1 Back-only exit works.** #2: `event → child → (unqualified child page, Back) → …` then every Home Event root was visited
  (5/5, visits=1 each). Run22 stopped after the first page. No input other than that one Back was sent on the unknown page.
- R22-2 (un-owned Monthly) was not exercised: #3 never reached the Shop (below).

## Defects found and fixed
| ID | Account / feature | Evidence | Root cause | Fix |
|---|---|---|---|---|
| R23-1 | #3 startup, whole account | recovery `3-a828…/20261026-094922-114867Z`: `open_game` returned "Events injected: 1"; `sample-20s-raw.png` shows the publisher splash (HHGames) drawn **translucently over the launcher**; result ACTION_FAILED "Game launch did not change Android home" after one sample (~14 s) | `HomeRecoveryEngine` treats ANDROID_HOME right after launch as a failed launch | read-only `launch_home_grace` (45 s) after a launch while no loading was seen; never relaunch or tap; Stop honoured (`automation/recovery.py`). Same signature as run20 #3. |
| R23-2 | #2 Events gallery | `…095532` page key `…:a8843c…`, after Back `…095547` key `…:96ecdc…`, identical controls → PARENT_NOT_VERIFIED, gallery's second card + tab skipped | gold-header page key = //16-quantized hash of the selected-tab core; correlation of the two cores = 0.99999 but the hash flipped | `DynamicEventPort.stable_shell_page`: same Event + title + selected-tab box and a unique ≥.995 core match reuse the first key (run-local only; ambiguity keeps the raw key) |
| R23-3 | #2 Guild Technology | `guild/…095358` shows `Số lần cống hiến: 3/20` and a WOOD `Cống Hiến 6480` button; result UNKNOWN, no action | the count crop between label and suffix is one 14-px digit; Windows OCR returns nothing (or "99") | `local_ocr.fraction_line_counter`: read the whole anchored line, require exactly one `N/20` (OCR renders `/` as `1`: `3120`), two renderings agreeing; used only when the number crop is unreadable. All 7 existing donation fixtures read unchanged. |

## Not fixed (no reward lost)
- #2 Monthly: BLOCKED "Selected shop tab not independently verified" — the Shop sidebar was scrolled so the selected Monthly tab is cut at the
  edge (`shop/…095202`); the page shows `Đã Nhận` and the day's claims are already VERIFIED. Partial-tab qualification needs more evidence.
- Event content pages remain unqualified (`EVENT_CONTENT_REQUIRES_QUALIFICATION` on every root): recorded BLOCKED, never exhausted.
- Old POSSIBLE/RESERVED locks unchanged.

## Tests
`tests/test_run22_repairs.py` now 45 tests (fixtures `tests/fixtures/run22/run23-*`); the splash-grace, page-key and single-digit-counter tests fail on
the pre-fix code. `tests/test_recovery.py::test_failed_launch_postcondition_is_bounded` updated to the grace contract (still one launch, bounded).
