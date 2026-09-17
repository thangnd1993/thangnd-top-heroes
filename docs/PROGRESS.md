# Tiến độ

## Phase 1 — Windows Foundation + LDPlayer Multi

- Trạng thái: code foundation và tests đã triển khai; đang chờ Windows CI build và nghiệm thu LDPlayer thật.
- Phạm vi hoàn thành: GUI PySide6 tiếng Việt, discovery, list2 typed parser, tìm kiếm/lọc,
  selected/protected SQLite, snapshot thao tác, guard execution, indexed CLI + ADB boot ID verification,
  screenshot PNG, packages/game control, logs, docs và portable build workflow.
- Kiểm thử: **75 passed** trên macOS / Python 3.12.14; `ruff check .` pass.
  Có GUI offscreen; subprocess/LDPlayer/ADB được mock. Không diễn giải mock thành kết quả thiết bị thật.
- Manual verification: chưa chạy LDPlayer; máy làm việc macOS không cài giả lập. Người dùng sẽ test Windows sau.
- UI preview: `docs/phase1-ui.png` là ảnh widget của GUI, không phải ảnh Android hoặc bằng chứng test ADB.
- LDPlayer path / CLI / ADB / instances: chưa phát hiện trong môi trường macOS.
- Screenshot thật và ADB verification thật: chưa thực hiện; unit tests pass.
- Windows portable: workflow đã thêm, sẽ cập nhật kết quả sau CI.
- Known limitations: cold start bị chặn vì chính sách cần ADB đã verify; chưa chấp thuận ngoại lệ.
  Không đoán resolution/package/serial; các biến thể CLI cần test trên LDPlayer thật.
  Không nhận biết delete/recreate cùng index+tên giữa hai refresh; xem SAFETY.md.
- Commit khởi tạo: `d755209` — đã push `origin/main`.
- Commit implementation: `dbb1953340b0e8b5e54415365d73573fd3c03b27` — đã push `origin/main`.
- Cập nhật kiểm thử: phủ toàn bộ protected actions, input abstraction, cold-start policy và
  transport đổi trước dispatch. Đóng SQLite connection rõ ràng sau mỗi transaction (quan trọng trên Windows).
- Bước tiếp: hoàn tất CI và bàn giao portable + checklist; dừng Phase 1.
- Phase kế tiếp (chưa làm): Phase 2 — queue/concurrency/account lifecycle, chỉ khi người dùng yêu cầu.
