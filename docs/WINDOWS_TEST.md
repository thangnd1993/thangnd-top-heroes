# Nghiệm thu trên Windows thật

## Phase 2 — Single-account result

Real Windows Phase 2 single-account lifecycle: **PASSED** (2026-09-19).

- Artifact CI: run `35429129052`, commit `2591e58`, concurrency `1`.
- Immutable snapshot: `4 / 3-Chíp` only; Run ID `1`.
- Lifecycle: start → Android ready → verified `emulator-5562` → harmless health check → target-only cleanup.
- Result/history: SUCCESS, `started_by_run=true`, persisted after process exit.
- Queen stayed Protected with no mutation. No gameplay and no multi-instance execution.
- Next acceptance requires explicitly authorized second clone for concurrency `2`.

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
