# Tiến độ

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
