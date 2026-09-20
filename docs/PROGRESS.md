# Tiến độ

## Phase 5 — Idle Reward — COMPLETE

- Trạng thái: **COMPLETE**. Real Windows acceptance pass ngày 2026-09-20 trên duy nhất
  `4 / 3-Chíp`, explicit ADB `emulator-5562`; `0 / Queen` vẫn Protected/unselected và không nhận
  mutation. Không dùng `5 / 4-Em Pé` và không bắt đầu Phase 6.
- Final portable: CI run `35469961859`, commit `43e3458`, artifact `10592886746`, SHA-256
  `67f648a2d0b41f466cde9049ee6177c29d9092396b755c4b347a1590cb695936`; lint, full pytest,
  PyInstaller build, executable smoke và artifact upload đều pass.
- Real claim evidence (task Run ID `5`, fresh CI artifact của `ee83c23`): verified `GAME_HOME` →
  Adventure entry → `Thưởng Treo Máy`; Claim được dispatch đúng một lần, popup `Chúc Mừng Nhận`
  và `Nhấn để tiếp tục` đều được verify. Không có claim retry.
- Lỗi cleanup thực tế sau Claim đã được sửa: popup có thể trở lại panel thay vì Home. Detector mới
  nhận riêng thông điệp không có thưởng và gray start của accumulation bar; cleanup chỉ dùng Back
  sau evidence mới, qua Adventure rồi verify `GAME_HOME`.
- Final no-double-claim/cleanup evidence (task Run ID `7`, final artifact): `NOT_AVAILABLE`,
  `claim_dispatched=false`, `cleanup_succeeded=true`, final state `GAME_HOME`, ADB
  `emulator-5562`, `isolation_changed_indices=[]`. Run history và report path đọc lại được từ SQLite
  sau process exit.
- Claimability gate là chest Adventure có glow xanh + red dot. Nút `Nhận` một mình không đủ vì vẫn
  xuất hiện sau Claim; hourglass `6/6` không có action anchor vì có thể dùng stamina. Partial bar có cả
  xanh và xám, nên gray-start detector bị giới hạn vùng và loại trừ với minimum green-fill detector.
- Đã sửa các integration bug thật: alternate open chest frame, portal flame animation, bar-state
  conflict, task-specific recovery từ panel/Adventure và hai biến thể post-claim. Threshold action
  anchors vẫn `0.9`; không nới safety guard hay cho phép click UNKNOWN.
- Task engine giữ exact snapshot, bounded observation, cancellation, một action/một screenshot mới,
  no-double-claim, `ACTION_RESULT_UNCERTAIN`, verified cleanup và machine-readable report. CLI:
  `TopHeroesAutoManager.exe task idle-reward --index 4 --name "3-Chíp"`; UI có **Thưởng treo máy** /
  **Chạy thử tác vụ**; SQLite persist `task_runs`.
- Portrait mapping đã được verify bằng action thật; stable portal core `(465,470)`, entry `(87,957)`,
  Claim `(362,915)`, popup continue `(360,1015)` theo device coordinates.
- Local targeted final: 66 Phase 5/vision/recovery tests pass; Ruff và diff check pass. Final state giữ
  `3-Chíp` running vì `started_by_run=false`; Queen stopped/Protected, các instance khác giữ nguyên
  baseline, kể cả index 1 và 7 đang chạy từ trước.
- Branch: `codex/phase5-idle-reward`. Phase 6 chưa bắt đầu.

## Phase 4 — Popup Handling + Safe Home Recovery — COMPLETE

- Trạng thái: **COMPLETE**. Real Windows acceptance: **PASSED** ngày 2026-09-19 trên duy nhất
  `4 / 3-Chíp`; `0 / Queen` vẫn Protected, unselected và không nhận mutation.
- Fresh portable: CI run `35444434273`, commit `097e155`, artifact `10584592524`, SHA-256
  `794a460ca253c40e2dee35d16bcf99d193806871486afec2b15faba39b091b9a`.
- Recovery engine giữ snapshot exact index/name, verified explicit ADB target, một screenshot mỗi step,
  action có precondition, postcondition bằng ảnh mới, cancellation và giới hạn 30 steps/120 giây.
  Loading/launch transition giới hạn 90 giây, poll 5 giây; không click trong loading.
- Scenario A (stopped): `ANDROID_HOME → launch_game → GAME_LOADING/UNKNOWN transition → GAME_HOME`,
  `SUCCESS`, ADB `emulator-5562`, `started_by_run=true`, cleanup đúng index 4.
- Scenario B (đã ở game home): `ALREADY_HOME`, actions rỗng, confidence `0.998662`, không cleanup
  instance không do run sở hữu. Scenario C (Android Home): launch package đã verify rồi `SUCCESS`,
  GAME_HOME confidence `0.979019`, không gameplay click.
- Scenario D synthetic: `UNKNOWN` được chụp xác nhận hai lần rồi fail-closed; không input/mutation.
  Blank/cropped frames chỉ được wait trong launch/loading window đã xác nhận và vẫn chịu timeout.
- Safe input abstraction chỉ tap khi có đúng một detected anchor với bounding box đã map về device;
  UNKNOWN hoặc thiếu evidence trả `DO NOT TAP`. Popup framework đã sẵn sàng nhưng chưa đăng ký handler
  vì không có real popup xuất hiện tự nhiên: **No real popup fixture available**.
- Diagnostic: `TopHeroesAutoManager.exe recovery home --index 4 --name "3-Chíp"`; report/screenshots
  nằm dưới `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\recovery\` và không commit vào Git.
- Targeted local: 74 recovery/vision/lifecycle tests pass; Ruff pass. CI run `35444434273` lint,
  full pytest, Windows portable build và executable smoke đều pass.
- Isolation pass: Queen và các instance ngoài index 4 giữ nguyên; không default ADB, first-device/index-0
  fallback, `quitall`, global operation, blind click hoặc gameplay/daily-task automation.
- Branch: `codex/phase4-home-recovery`. Không bắt đầu Phase 5.

## Phase 3 — Screenshot Pipeline + Screen Recognition — COMPLETE

- Trạng thái: **COMPLETE**. Real Windows acceptance: **PASSED** ngày 2026-09-19 trên duy nhất
  `4 / 3-Chíp`; `0 / Queen` vẫn Protected, unselected và không nhận mutation.
- Fresh portable: CI run `35441526597`, commit `2fbaa46`, artifact `10583942593`, artifact SHA-256
  `62afeb1d0ca5ce6240ba1e6c35abb0e24457c9aed48b2be927675f9f90717c84`.
- Exact ADB target: `emulator-5562`; ảnh thật 1280x720, normalized 1280x720, scale 1.0/1.0.
- `ANDROID_HOME`: confidence `1.0`, 26.886 ms. `GAME_LOADING`: confidence `1.0`, 34.595 ms.
  `GAME_HOME`: confidence `0.998736`, 30.023 ms với required world-button và optional bottom-nav.
- `UNKNOWN` fail-closed, negative matching, threshold boundary và state conflict được regression-test
  bằng fixture synthetic; không tạo điều kiện game nguy hiểm chỉ để lấy ảnh.
- Template crop thật được version trong `assets/templates/{android,loading,home}`; full screenshots và
  debug overlays ở `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\vision`, không commit vào Git.
- Screenshot service validate PNG/dimensions/nonblank, normalize orientation/resolution, giữ original/
  normalized coordinates và chỉ dispatch tới verified explicit target. Một detection cycle dùng một ảnh.
- Detector tổng hợp required/optional anchors theo weight; thiếu required hoặc conflict trong margin 0.03
  trả `UNKNOWN`. Detection JSON giữ Unicode UTF-8 và overlay là tùy chọn.
- Cleanup/isolation pass: stop đúng package và index 4; cuối run cả 12 instance stopped như baseline.
  Không default ADB, first-device/index-0 fallback, global LDPlayer op hoặc gameplay clicks.
- Local: Ruff pass; 16 vision tests pass; 158 non-GUI tests pass. CI Windows lint, full pytest,
  PyInstaller portable và executable smoke: pass.
- Branch: `codex/phase3-screen-recognition`. Không merge main và không bắt đầu Phase 4.

## Phase 2 — Run Selected Queue + Concurrency — COMPLETE

- Trạng thái: **COMPLETE**. Real Windows concurrency acceptance: **PASSED** ngày 2026-09-19,
  dùng portable artifact đã được CI run `35430067613` xác minh (commit `e1db0ad`).
- Remediation môi trường duy nhất: `5 / 4-Em Pé` có `basicSettings.adbDebug=0`, trong khi
  `4 / 3-Chíp` là `1`. Đã sao lưu `leidian5.config.phase2-adb-backup` và chỉ đổi đúng field
  `basicSettings.adbDebug` thành `1`; sau đó single-account Run ID `3` PASS.
- Multi-instance Run ID `4`: immutable snapshot `[[4, "3-Chíp"], [5, "4-Em Pé"]]`,
  max concurrency `2`. Cả hai worker active đồng thời với target độc lập: `emulator-5562` và
  `emulator-5564`; harmless health check pass, retry=0, `started_by_run=true`, cleanup dừng đúng
  hai target.
- Persistence pass sau process exit: Run `4` = SUCCESS, completed=2, failed=0, cancelled=0;
  hai RunAccount đều SUCCESS và persisted trong SQLite.
- Isolation pass: Queen không mutation; instance ngoài 4/5 không có lifecycle mutation. Chicken đã
  running từ trước và được giữ nguyên running. Không gameplay automation và không dùng default ADB,
  first-device fallback, index-0 fallback hoặc global LDPlayer operation.

## Phase 1 — Windows Foundation + LDPlayer Multi — COMPLETE

- Trạng thái: **COMPLETE**. Real Windows LDPlayer integration: **PASSED** ngày 2026-09-18.
- LDPlayer version: `9.5.31.0`; path: `D:\LDPlayer\LDPlayer9`.
- Protected main: `0 / Queen` (`protected=true`, `selected=false`); không có lifecycle/ADB/game mutation.
- Test clone duy nhất: `4 / 3-Chíp`; discovery đủ 12 instance và giữ đúng tên Unicode.
- ADB mapping đã xác minh: LDPlayer-scoped serial `emulator-5562`; explicit endpoint
  `127.0.0.1:5563` có cùng Android boot ID trong phép kiểm tra recovery.
- Diagnostic thật pass: start, Android-ready (bao gồm transitional state 2), harmless shell,
  screenshot, package discovery, game launch/stop, restart, ADB re-verification, exact stop và isolation.
- App label `Thời Đại Anh Hùng` được đối chiếu bằng APK metadata; package xác định duy nhất:
  `com.greenmushroom.boomblitz.gp.vn`; launcher: `com.rivergame.gp.AppActivity`.
- Resolver giữ fail-closed: không first-device/index-0 fallback; ưu tiên serial đã đăng ký, sau đó
  indexed identity và explicit loopback connection có boot-ID verification. Shared ADB restart chỉ được
  phép khi không có device khác và không có LDPlayer instance khác chạy.
- CI branch run: [35347373605](https://github.com/thangnd1993/thangnd-top-heroes/actions/runs/35347373605) —
  lint pass, pytest pass, PyInstaller/portable build pass, executable smoke pass.
- Artifact: `TopHeroesAutoManager-Windows-x64` (`10547612861`); EXE SHA-256
  `7853e1f4ab5979b813238b811e2ac0f51205fa9600c607d6b9ea481b45a5c62f`.
- Diagnostic report: `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\reports\phase1-windows-acceptance.json`.
- Không chuyển sang Phase 2.

## Lịch sử sửa blocker lifecycle Start/Restart

- Trạng thái lịch sử: lifecycle fix đã được CI xác minh trước vòng nghiệm thu Windows thật.
- Root cause: execute gọi resolver ADB vô điều kiện trước khi phân loại lifecycle/ADB-dependent;
  cold start bị chặn và CLI reboot không bảo đảm đã chờ stop/start rồi verify transport mới.
- Fix: lifecycle index-first, selected/protected/snapshot guard giữ nguyên. Start → wait Android →
  resolve/verify. Restart → quit đúng index → wait stopped → launch cùng index → wait Android →
  resolve/verify mới. Stop/Query không phụ thuộc ADB. UI refresh read-only sau lifecycle.
- Startup timeout 120 giây, stop timeout 60 giây; polling kiểm tra lại quyền và identity.
  Resolver failure chỉ hủy thao tác của instance đó, không global cleanup hoặc chuyển target.
- Tests mới: 29 cases trong `tests/test_lifecycle.py`; thay test cold start bị chặn đã lỗi thời.
  Phủ đủ 9 yêu cầu: cold start không có ADB, thứ tự resolve, protected/unchecked, restart đổi serial/boot,
  failure isolation, exact index, không fallback 0, không quitall; thêm wait/timeout/revocation/identity changes.
- Local: `pytest -q` **103 passed**; `ruff check .` pass. LDPlayer thật: chưa test trên macOS.
- Windows CI: **103 passed in 16.39s** (Python 3.12, Windows x64), lint pass,
  PyInstaller build pass, `.exe --smoke-test` mở GUI và thoát sạch code 0.
- [GitHub Actions — success](https://github.com/thangnd1993/thangnd-top-heroes/actions/runs/35204186113).
- [Tải portable Windows đã sửa lifecycle](https://github.com/thangnd1993/thangnd-top-heroes/actions/runs/35204186113/artifacts/10489670505).
  Đăng nhập GitHub, tải ZIP, giải nén toàn bộ và chạy `TopHeroesAutoManager.exe` cạnh `_internal/`.
- Commit code/build: `637b3534c1720d4fb744bbe91582e9110367ba37`, đã push `origin/main`.
  Commit báo cáo kết quả build được push tiếp theo, chỉ thay tài liệu.
- Output CI: `dist/TopHeroesAutoManager/TopHeroesAutoManager.exe`.
  Bản tải local tách khỏi build cũ: `dist/phase1-lifecycle/TopHeroesAutoManager/`.
- Tài liệu: README, SAFETY, WINDOWS_TEST cập nhật theo lifecycle mới.
- Next: bàn giao lại Phase 1 để người dùng kiểm thử Windows thật, không làm Phase 2.

## Lịch sử bản bàn giao trước sửa lifecycle (đã thay thế)

## Phase 1 — Windows Foundation + LDPlayer Multi

- Trạng thái: đã bàn giao code foundation + portable Windows để thử nghiệm; **chưa nghiệm thu đầy đủ Phase 1**.
  Còn kiểm tra LDPlayer thật trên máy người dùng và quyết định ngoại lệ cold start.
- Phạm vi hoàn thành: GUI PySide6 tiếng Việt, discovery, list2 typed parser, tìm kiếm/lọc,
  selected/protected SQLite, snapshot thao tác, guard execution, indexed CLI + ADB boot ID verification,
  screenshot PNG, packages/game control, logs, docs và portable build workflow.
- Kiểm thử: **75 passed** trên macOS / Python 3.12.14; `ruff check .` pass.
  Có GUI offscreen; subprocess/LDPlayer/ADB được mock. Không diễn giải mock thành kết quả thiết bị thật.
- Windows CI (Windows Server 2025 x64, Python 3.12.10): **75 passed in 12.98s**; lint pass.
- Manual verification: chưa chạy LDPlayer; máy làm việc macOS không cài giả lập. Người dùng sẽ test Windows sau.
- UI preview: `docs/phase1-ui.png` là ảnh widget của GUI, không phải ảnh Android hoặc bằng chứng test ADB.
- LDPlayer path / CLI / ADB / instances: chưa phát hiện trong môi trường macOS.
- Screenshot thật và ADB verification thật: chưa thực hiện; unit tests pass.
- Windows portable: **build thành công**, smoke test executable mở GUI và thoát sạch với code 0.
  [CI run đã xác minh](https://github.com/thangnd1993/thangnd-top-heroes/actions/runs/35202851053).
  [Tải artifact portable](https://github.com/thangnd1993/thangnd-top-heroes/actions/runs/35202851053/artifacts/10489185027).
  Output: `dist/TopHeroesAutoManager/TopHeroesAutoManager.exe` và `_internal/`.
  Portable ZIP bàn giao local: `dist/TopHeroesAutoManager-Windows-x64.zip`.
  ZIP 48.0 MiB đã kiểm tra CRC; có Python DLL, Qt DLL và Windows platform plugin đi kèm.
  EXE SHA256: `4d9aabe6e49edba57ed5e3ee735d2524964bfa0e9d04fed27e135c648e5f0415`.
  ZIP SHA256: `def37ea4c700bfc116fe9082d9c6ee12bf4845cdc4a27af9ef58dc5720fa6523`.
- Known limitations: cold start bị chặn vì chính sách cần ADB đã verify; chưa chấp thuận ngoại lệ.
  Không đoán resolution/package/serial; các biến thể CLI cần test trên LDPlayer thật.
  Không nhận biết delete/recreate cùng index+tên giữa hai refresh; xem SAFETY.md.
- Commit khởi tạo: `d755209` — đã push `origin/main`.
- Commit implementation: `dbb1953340b0e8b5e54415365d73573fd3c03b27` — đã push `origin/main`.
- Cập nhật kiểm thử: phủ toàn bộ protected actions, input abstraction, cold-start policy và
  transport đổi trước dispatch. Đóng SQLite connection rõ ràng sau mỗi transaction (quan trọng trên Windows).
- Commit bổ sung guard tests/SQLite: `38d3964485b967f03f12a5f09378bb522bf65a95`.
- Commit code/build cuối: `0191fd941d2ddac4dfe298f0ff72db08c8c1be85` — đã push `origin/main` và CI pass.
- Commit báo cáo này chỉ thay đổi docs; hash xem `git log -1 --format=%H` sau checkout bản bàn giao.
- Push status: các commit code đã có trên `origin/main`; bản ghi bàn giao cũng được commit/push riêng.
- Bước tiếp: người dùng kiểm tra [WINDOWS_TEST.md](WINDOWS_TEST.md); dừng Phase 1.
- Phase kế tiếp (chưa làm): Phase 2 — queue/concurrency/account lifecycle, chỉ khi người dùng yêu cầu.
