# Thiết kế an toàn Phase 1

## Luồng thực thi

UI → Manager.execute → refresh list2 → snapshot một instance → kiểm tra quyền hiện hành →
CLI indexed ADB get-serialno → CLI indexed Android boot ID → adb devices → adb -s SERIAL đọc boot ID →
đối chiếu boot ID lần nữa → kiểm tra quyền → gửi đúng một lệnh có target rõ ràng → xóa snapshot.

Chỉ các probe nhận dạng read-only được phép thực hiện trong quá trình xác minh trước khi có
ADB đã xác minh. Probe CLI có index rõ ràng và chỉ chạy sau whitelist/queue guard;
probe adb chỉ dùng serial chính CLI trả về. Không quét các thiết bị khác để tìm boot ID.
`adb devices` và `list2` chỉ liệt kê. Không chụp screenshot để dò target.

Mọi lệnh tác động thiết bị, bao gồm screenshot, đều đi qua Manager. Các phương thức có `_`
trong transport là chi tiết nội bộ, UI không gọi trực tiếp. Python không phải sandbox chống plugin
độc hại; Phase 1 không hỗ trợ plugin/script tùy ý. `ADB.connect` chỉ hỗ trợ endpoint loopback rõ ràng;
UI dùng resolver CLI của LDPlayer, không tự tính port hoặc fallback connect ngầm.

## Sáu điều kiện

1. Index tồn tại duy nhất trong list2 hiện tại.
2. Cặp index/tên trong snapshot của thao tác đang thực thi.
3. SQLite vẫn selected.
4. SQLite không protected.
5. Index/tên trùng khớp, cùng namespace bản cài LDPlayer.
6. ADB explicit serial online, boot ID trùng CLI index, không thay đổi khi verify lại.

Sai bất kỳ điều kiện nào: hủy instance và log lỗi, không thử index/serial khác.
Mỗi thao tác xác minh mới; không cache quyền ADB qua reboot. Timeout process là 20 giây mỗi lệnh.
Nếu lệnh điều khiển timeout, kết quả có thể chưa rõ: không retry tự động; refresh để kiểm tra.

## Khởi động khi đang tắt

Theo nguyên tắc tuyệt đối đã yêu cầu, cold start hiện bị chặn do không có Android/ADB để verify.
Không tự ý áp dụng ngoại lệ cho lệnh launch. Có thể khởi động thủ công bằng LDPlayer Multi trước.
Đây là mâu thuẫn giữa yêu cầu cold start và điều kiện ADB bắt buộc; cần quyết định rõ của chủ dự án.

## Trạng thái thay đổi

Snapshot bất biến: thay đổi checkbox không tự thêm thành viên. Thu hồi selection/protection được
kiểm tra lại trước dispatch. Trong một process, UI khóa các điều khiển khi worker đang chạy và Manager
dùng RLock. SQLite constraint không cho selected và protected đồng thời.

Đổi tên hoặc reappearance sau refresh hủy selection; protection vẫn giữ. Không phân biệt được trường hợp
xóa rồi tạo lại một instance với cùng index và tên giữa hai lần đọc vì list2 không cung cấp UUID bền vững.
Không xóa/tạo/đổi tên instance trong LDPlayer Multi khi thao tác đang chạy. CLI bên ngoài và OS có thể
thay đổi target ngay sau lần verify; không thể khóa giao dịch nguyên tử xuyên LDPlayer/ADB bằng list2.
Phiên bản LDPlayer không hỗ trợ `adb --index N --command get-serialno` hoặc không cho đọc boot ID
sẽ bị chặn. Cần dữ liệu thực tế trước khi bổ sung adapter cho biến thể đó; không suy đoán.

## Không thuộc Phase 1

Không task gameplay, không scheduler, không tự tắt sau tác vụ, không chạy đồng thời nhiều giả lập.
Các guard tiêu kim cương/vật phẩm sẽ được thiết kế cùng state recognition trong phase tương lai.
