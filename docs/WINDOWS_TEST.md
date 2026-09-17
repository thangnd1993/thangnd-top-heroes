# Nghiệm thu trên Windows thật

Chưa thực hiện trên máy phát triển macOS. Các dòng dưới là checklist, không phải kết quả đã đạt.

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
