# Tiến độ

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
