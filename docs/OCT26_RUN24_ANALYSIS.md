# October26 normal application run24 — analysis and repair (build 3713003)

## Evidence
- Run **24**, `normal-ui-start`, concurrency 2 (peak 2), targets #2 Emmmm and #3 Queen con; 2026-10-26 11:30:33–11:47:04 UTC
  (18:30–18:47 Vietnam), result PARTIAL. Exe SHA-256 `8c2e5598…5fd63`, commit `3713003979012094681ed2744657b17625227dc4`, CI 40307972895.
- Report `diagnostics\tasks\automation\20261026-113033-281177Z-26e88d55\`; exports `diagnostics-run24-*.zip`. Protected/names/selections
  unchanged, 0 name writes, selections restored. Same game day as runs 22/23 (daily reset 02:00 UTC), so daily rewards were already VERIFIED.

## Proven in real gameplay by run24
| Repair | Evidence |
|---|---|
| R23-1 splash grace | #3 startup 121 s, reached GAME_HOME (run23: ACTION_FAILED after 14 s) |
| R23-2 stable gallery page key | #2 and #3 visited 2–4 gallery cards each (run23: 1) |
| R23-3 single-digit count | #2 Technology `6/20` read; 1 ordinary + 1 quick contribution, counter 6→5→0, journals 1013/1014 VERIFIED |
| R22-2 un-owned Monthly | #3 `shop-monthly-daily` NOT_AVAILABLE, parent SUCCESS (run22: UNKNOWN/BLOCKED) |
| R22-1 Back-only exit | used once per account, then traversal continued |

## Claims in run24
| Index | Dispatched → result |
|---|---|
| 2 | guild-technology VERIFIED (1013, 1014); mail-guild VERIFIED (1016); mail-reports VERIFIED (1017, 23→0); Event inline objective **POSSIBLE** (1019) |
| 3 | mail-guild VERIFIED; Event task-grid reward VERIFIED (1018); one Event reward ALREADY_ATTEMPTED (old lock 365) |

## Defects and repairs
| ID | Evidence | Root cause | Fix / status |
|---|---|---|---|
| R24-1 | #3 `events/…114538`: Event `7a78543a` paid pack "Gói Quân Trang Phe" → UNKNOWN, recovery UNKNOWN_SCREEN, Event `5ecd5502` never visited (visits=0). Same modal on #2 (`…114612`, "Gói Bí Bảo") qualified. | `event_paid_modal._match` requires ≥.995 binary-mask match; this frame's red close X scored .932 and VND .935 (different raster) | **Fixed**: real-frame raster variants `close-red-core-raster2`, `vnd-word-raster`; threshold, uniqueness and positional agreement unchanged; navigation-only close, page BLOCKED. No other fixture qualifies. |
| R24-2 | #2 claim 1019 on `…114257`/`…114311` (inline objective "Hoàn thành 1 lần thu thập Mỏ Sa Thạch 1/1"); after the tap (`…114320`) the row disappeared and a floating receipt ("Gia Tốc 1p x5", "Kim Cương x20") appeared | `inline_objective_rows` only qualifies rows with a green `Nhận`; after the claim the remaining rows are "Chưa đạt", so the page key changed and `_claim_postcondition` refused to verify | **Not fixed (safe)**: claim stays POSSIBLE and is never repeated. A removed row must be proven claimed (not scrolled away) before VERIFIED; fixtures `run24-inline-114257/114320` kept for that work. |

## Speed (measured)
Run24 #2 exclusive cost (990 s wall): recognition 507 s (51 %), command start-ups 313 s (32 %: inventory 96, identity 127, capture 76, input 14),
OCR 79 s / 131 calls (8 %), deliberate waits 68 s (7 %). #3 (930 s): OCR 122 s / 195 calls.

| Change | Measured on this PC | Expected effect per account |
|---|---|---|
| Persistent OCR reader (`assets/tools/ocr-server.ps1`, one per worker thread, one-shot fallback) | 0.503 → 0.044 s per call; 42/42 crops identical | −60 s (#2) … −90 s (#3) |
| Idle-adventure prefilter (`idle_panel_recovery.adventure_back_evidence`): reject when no required `idle-entry-*` anchor matches | Shop frame 5.13 → 4.00 s; identical result on all 210 fixtures | −0.6–1.1 s per feature frame (~100 frames) |
| Fixed-reward anchor searches in a shared pool (titles first, results/order identical) | 3.26 → 2.96 s per frame | −0.3 s per Shop/VIP frame |
Real wall-clock gain must be confirmed by the next run; the target of a few minutes per account is **not** reached by these alone —
remaining cost is per-page specialised searches (sub-pixel tab alignment 1.5 s, gift pose 0.8 s) and ~1000 guarded command spawns.

## Not changed
Event content pages that are not qualified stay BLOCKED (never exhausted); old POSSIBLE/RESERVED locks unchanged; Phase 8 remains PARTIAL.
