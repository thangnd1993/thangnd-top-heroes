# Nghiệm thu trên Windows thật

## Phase 6 — guarded checkpoint, acceptance pending

UI Phase 6 and bounded shop-discovery primitives were added after the
previous passing artifact. The current code has 109 focused local tests
including offscreen UI and remains fail-closed for missing receipt/zero-cost
evidence. A fresh CI artifact and real task acceptance of this new code
are still required; the earlier artifact below cannot certify these edits.

The prior session collected real free VIP, daily gift and recruit evidence on
`4 / 3-Chíp`. These are manual collection results, not acceptance of production
Phase 6 task commands. The resume preserved them without repeating claims.

The current authorized Phase 6 test clone is only `2 / 5-Emmmmm`; index 4 is
revoked and Queen remains Protected. Index 2's newer survey checked the left
shop-tab boundary, growth-fund upper boundary and diamond-shop lower boundary
with fresh same-account screenshots. No reward, recruit, purchase or resource
action was taken; the owned start was stopped afterward.

CLI task/sequence scaffolding, guarded navigation, reward journal and reporting
now have targeted regressions. Production claims remain blocked because index 2
has no verified VIP/Recruit post-claim anchor and the daily gift has no independent
zero-cost proof. Checkpoint `b8be92a` passed full Windows CI run
`35629610052` with fresh artifact `10654057686`; that artifact has not
been used for real Phase 6 task acceptance. UI controls, production nested
traversal and real per-task acceptance remain open. No Phase 6 completion is claimed. See
[PHASE6_RESUME.md](PHASE6_RESUME.md) and [PHASE6_SURVEY.md](PHASE6_SURVEY.md).

## Phase 5 — Idle Reward result

Real Windows Phase 5 acceptance: **PASSED** (2026-09-20).

- Scope: only `4 / 3-Chíp`, explicit ADB `emulator-5562`; `0 / Queen` remained Protected and
  unselected. `5 / 4-Em Pé` and all other instances received no mutation.
- Final artifact: CI run `35469961859`, commit `43e3458`, artifact `10592886746`; verified SHA-256
  `67f648a2d0b41f466cde9049ee6177c29d9092396b755c4b347a1590cb695936`.
- Claim run ID `5`: exact route and visual preconditions passed, Claim was dispatched once, reward
  popup and continuation were verified, and no retry was sent. A real post-claim panel cleanup issue
  was then fixed with new regression coverage and a new CI artifact.
- Final run ID `7`: `NOT_AVAILABLE`, `claim_dispatched=false`, `cleanup_succeeded=true`, final state
  `GAME_HOME`, `isolation_changed_indices=[]`. This proves the second run does not double-claim and
  that the final artifact closes the verified post-claim panel and returns Home.
- Run IDs `5` and `7`, statuses and report paths persisted in `%LOCALAPPDATA%\TopHeroesAutoManager\config.sqlite3`
  and were read back after each portable process exited.
- Home action uses the stable core of blue `Cấp 4` Adventure portal. Claimability uses the Adventure
  chest glow/red dot plus verified panel title/button/minimum green fill. Post-claim variants require
  either the unique no-reward message or the gray *start* of the bar in a tightly bounded region.
- The adjacent hourglass `6/6` remains forbidden and has no action anchor. Unknown/ambiguous screens
  do not receive input; each action requires a newly captured verified state.
- Final lifecycle ownership: `3-Chíp` was already running, so the task left it running. Queen stayed
  stopped/Protected; index 1 and 7 remained in their pre-run running state; every other instance kept
  its baseline state.
- Local targeted final: 66 tests passed and Ruff passed. CI lint, full pytest, PyInstaller portable,
  executable smoke and artifact upload all passed.

Portable diagnostic command:

```powershell
TopHeroesAutoManager.exe task idle-reward --index 4 --name "3-Chíp"
```

Expected evidence is stored under
`%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\tasks\idle-reward\3-Chíp\<run-id>\`.

## Phase 4 — Safe home recovery result

Real Windows Phase 4 recovery acceptance: **PASSED** (2026-09-19).

- Fresh artifact: CI run `35444434273`, commit `097e155`, artifact `10584592524`; verified SHA-256
  `794a460ca253c40e2dee35d16bcf99d193806871486afec2b15faba39b091b9a`.
- Scope: only `4 / 3-Chíp`, explicit ADB `emulator-5562`; `0 / Queen` remained Protected and
  unselected. No lifecycle/ADB/game mutation was sent to another instance.
- Stopped scenario: recovery started index 4, launched only verified package
  `com.greenmushroom.boomblitz.gp.vn`, waited without input through loading/blank frames, reached
  `GAME_HOME`, returned `SUCCESS`, then cleaned up because the run owned the start.
- Already-home scenario: one fresh capture detected `GAME_HOME` at confidence `0.998662`, returned
  `ALREADY_HOME`, actions `[]`, and did not request cleanup.
- Android-home scenario: detected `ANDROID_HOME`, launched the verified package once, waited through
  bounded transition frames, reached `GAME_HOME` at confidence `0.979019`, and returned `SUCCESS`.
- Synthetic unrelated `UNKNOWN`: two confirmation captures, no input, then `UNKNOWN_SCREEN`.
- Limits: 30 steps, 120-second overall duration, 90-second loading/launch window, 5-second poll.
  Cancellation is checked before captures/actions and before further waits.
- No real popup appeared naturally, so no speculative popup template/action was added. The typed
  `PopupHandler` framework is ready for a future real, unambiguous safe fixture.

Headless recovery command:

```powershell
TopHeroesAutoManager.exe recovery home --index 4 --name "3-Chíp"
```

Each run writes UTF-8 JSON plus evidence under
`%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\recovery\<account>\<run-id>\`.

## Phase 3 — Screen recognition result

Real Windows Phase 3 visual acceptance: **PASSED** (2026-09-19).

- Fresh artifact: CI run `35441526597`, commit `2fbaa46`, artifact `10583942593`; verified SHA-256
  `62afeb1d0ca5ce6240ba1e6c35abb0e24457c9aed48b2be927675f9f90717c84`.
- Scope: only `4 / 3-Chíp`; exact ADB target `emulator-5562`. `0 / Queen` remained Protected and
  unselected. No other instance received lifecycle or ADB mutation.
- Android launcher: `ANDROID_HOME`, confidence `1.0`, 26.886 ms.
- Real HHGames startup screen: `GAME_LOADING`, confidence `1.0`, 34.595 ms.
- Real Thời Đại Anh Hùng home: `GAME_HOME`, confidence `0.998736`, 30.023 ms, both configured
  home anchors matched. No gameplay menu click was performed.
- Synthetic unrelated/corrupt/blank/conflicting inputs cover `UNKNOWN` and invalid fail-closed paths.
- Full screenshots, UTF-8 metadata/detection reports and debug overlays are under
  `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\vision\`.
- Cleanup: stopped exact package then exact index 4 because the test started it; all 12 instances
  were stopped afterward, matching the pre-run baseline.

Headless verification commands:

```powershell
TopHeroesAutoManager.exe vision capture --index 4 --name "3-Chíp" --tag sample
TopHeroesAutoManager.exe vision detect --index 4 --name "3-Chíp" --tag acceptance --debug
```

These commands fail closed unless exact identity, selection/protection rules, Queen protection and
explicit ADB verification all pass. Phase 3 does not close popups, press Back or automate gameplay.

## Phase 2 — Concurrency result

Real Windows Phase 2 concurrency acceptance: **PASSED** (2026-09-19).

- Artifact CI: run `35430067613`, commit `e1db0ad`, digest
  `9d30ab45a4e8ae156380cfe158bc5a9980dbf02f8ae12f0a9f88ad054b2bc839`.
- Remediation before acceptance: index 5 had `basicSettings.adbDebug=0`; its config was backed up
  and only that field was changed to `1`. Single-account Run ID `3` then passed.
- Immutable Run ID `4`: `4 / 3-Chíp` and `5 / 4-Em Pé` only; max concurrency `2`.
- Explicit ADB targets: `3-Chíp → emulator-5562`; `4-Em Pé → emulator-5564`. Both were active
  concurrently, verified separately, health-checked, and target-cleaned.
- Result/history: both SUCCESS, `started_by_run=true`, retry=0; run summary and both account rows
  persisted after process exit.
- Queen remained Protected with no mutation. Chicken was already running and remained untouched; no
  gameplay, default ADB selection, first-device fallback, index-0 fallback, or global operation.

## Kết quả Phase 1

Real Windows LDPlayer integration: **PASSED**

- Ngày: 2026-09-18
- LDPlayer version: `9.5.31.0`
- LDPlayer path: `D:\LDPlayer\LDPlayer9`
- Số instance phát hiện: 12
- Protected main: `0 / Queen` (`protected=true`, `selected=false`)
- Test clone: `4 / 3-Chíp`
- ADB target: `emulator-5562` (đã đối chiếu boot identity; không dùng default device)
- Screenshot trước game: `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\3-Chíp\instance-4-20260918-130633-484976Z.png`
- Screenshot sau launch: `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\3-Chíp\instance-4-20260918-130654-229291Z.png`
- App label: `Thời Đại Anh Hùng`
- Package: `com.greenmushroom.boomblitz.gp.vn`
- Launcher: `com.rivergame.gp.AppActivity`
- Start, Android ready, harmless shell, screenshot, package discovery, game launch/stop,
  restart, ADB re-verification, exact stop: **PASSED**
- Isolation: **PASSED**; mọi instance khác giữ nguyên và cuối cùng cả 12 instance đều stopped.
- Queen chỉ được kiểm tra persisted protection; không nhận lifecycle/ADB/game mutation.
- CI/artifact: run `35347373605`, artifact `10547612861`, lint/pytest/build/smoke đều pass.

## Checklist tham chiếu

Ghi lại Windows version, LDPlayer version, console path, ADB path, `list2` và thời gian chạy.
Đóng các phiên manager khác trước khi kiểm thử. Không xóa/đổi tên instance khi một lệnh đang chạy.

1. Giải nén portable lên máy không cài Python; mở exe; giao diện tiếng Việt xuất hiện.
2. Kiểm tra auto discovery, sau đó chọn thư mục thủ công nếu cần; đóng/mở app kiểm tra persistence.
3. So sánh toàn bộ index/tên/trạng thái trong bảng với LDPlayer Multi. Không có dữ liệu mẫu.
4. Đánh dấu Main-Thang Protected; thử Chọn hiển thị và checkbox; main không được chọn.
5. Tạo clone mới trong Multi, refresh: clone bỏ chọn. Refresh không bật/tắt emulator hoặc game.
6. Chọn một clone; search/filter; Bỏ chọn hiển thị không thay đổi các hàng bị ẩn.
7. Đóng/mở app: selected/protected và package vẫn đúng. Bỏ protection không tự chọn lại.
8. Giữ clone đang tắt (chưa có ADB), chọn đúng clone trong app rồi bấm Khởi động.
   Log phải ghi launch đúng index trước khi chờ Android và xác minh serial. Main và clone khác không đổi.
9. Chụp PNG: ảnh phải đúng clone, không phải desktop/main; ghi đường dẫn ảnh.
10. Liệt kê packages; nhập package Top Heroes thật; mở/đóng game clone và quan sát main không đổi.
11. Dừng clone, app refresh xác nhận dừng. Bấm Khởi động lại từ trạng thái tắt để kiểm tra cold start lần nữa.
12. Khi clone đang chạy, ghi serial hiện tại rồi bấm Khởi động lại. Phải thấy quit đúng index,
    chờ dừng, launch cùng index, chờ Android và resolve/verify mới. Serial có thể giữ nguyên nhưng boot ID
    phải được đọc và đối chiếu lại; không suy luận đã verify chỉ vì serial giống lần trước.
13. Tắt ADB hoặc bỏ quyền, rồi Start clone đang tắt: clone được launch nhưng bước xác minh phải báo lỗi.
    Không mở game/chụp ảnh tiếp, không chuyển target, không tắt các instance khác. Sau khi bật lại ADB,
    một thao tác xác minh mới phải dùng được. Screenshot/game khi Android đang tắt phải bị chặn, không autolaunch.
14. Mở nhiều clone; chụp/mở game một clone được chọn; xác nhận tất cả clone khác/main không đổi.
15. Kiểm tra `%LOCALAPPDATA%\TopHeroesAutoManager\logs\app.log` và screenshots.
16. Protected hoặc bỏ chọn một clone đang tắt: không được Start/Restart thông qua app. Chọn hiển thị
    vẫn bỏ qua Protected. Query/Refresh vẫn đọc được trạng thái mà không tác động thiết bị.
17. Nếu startup không tới Android-ready trong 120 giây hoặc stop không xong trong 60 giây,
    app báo timeout và chỉ hủy thao tác target đó. Có thể cộng tối đa 20 giây cho CLI đang xử lý.

Ghi kết quả từng mục, instance index/name/status, serial, ảnh và log vào PROGRESS trước khi tuyên bố
Phase 1 được nghiệm thu đầy đủ. Không đưa thông tin đăng nhập vào issue hoặc log.
