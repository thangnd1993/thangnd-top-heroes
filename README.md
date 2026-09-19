# Top Heroes Auto Manager

Ứng dụng desktop **Windows**, Python 3.12 + PySide6, quản lý LDPlayer theo nguyên tắc
**một instance = một tài khoản**. Phát triển bởi Thang Nguyen.

Phase 1 và Phase 2 đã nghiệm thu trên LDPlayer thật. Phase 3 bổ sung pipeline screenshot Android
qua ADB target đã xác minh và nhận diện màn hình fail-closed bằng OpenCV. Chưa có gameplay automation.

## Nhận diện màn hình Phase 3

- Một chu kỳ dùng đúng một ảnh chụp từ explicit ADB target; không phụ thuộc vị trí cửa sổ emulator.
- PNG được kiểm tra decode/kích thước/blank, chuẩn hóa về không gian tham chiếu 1280x720 và giữ
  scale để ánh xạ bounding box về tọa độ thiết bị.
- Các trạng thái typed hiện có: `UNKNOWN`, `ANDROID_HOME`, `GAME_LOADING`, `GAME_HOME`,
  `POPUP_GENERIC`, `CONNECTION_ERROR`, `UPDATE_NOTICE`.
- Detector dùng các anchor crop thật trong `assets/templates/`, ROI chuẩn hóa, threshold và vai trò
  required/optional. Thiếu anchor bắt buộc hoặc có hai state gần ngang nhau sẽ trả `UNKNOWN`.
- UI có nút **Nhận diện màn hình** và hiển thị trạng thái/độ tin cậy cơ bản.

Diagnostic headless an toàn:

```powershell
TopHeroesAutoManager.exe vision capture --index 4 --name "3-Chíp" --tag sample
TopHeroesAutoManager.exe vision detect --index 4 --name "3-Chíp" --tag check --debug
```

Ảnh, metadata UTF-8, detection JSON và overlay tùy chọn được lưu dưới
`%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\vision\`. Lệnh luôn kiểm tra exact index/name,
selection/protection, `Queen` Protected và explicit ADB target trước khi capture.

## Phạm vi Phase 1

- GUI tiếng Việt, giao diện xanh đậm, tìm kiếm/lọc, chọn hiển thị và bảo vệ từng instance.
- Tìm `ldconsole.exe` / `dnconsole.exe` và `adb.exe`: đường dẫn đã lưu, các thư mục LDPlayer
  phổ biến trên ổ C, PATH, Windows uninstall registry; có chọn thư mục thủ công.
- Đọc `list2` thực tế, không tạo tài khoản giả và không yêu cầu nhập danh sách account.
- Lưu SQLite: selected/protected, thư mục LDPlayer, ADB path, package, vị trí/kích thước cửa sổ.
- Xác minh ADB qua CLI theo index + Android boot ID; chụp PNG Android, liệt kê packages,
  mở/đóng game, dừng/khởi động lại instance qua lớp guard.
- Worker thread với timeout subprocess, log UI và file xoay vòng.
- pytest, kiểm thử GUI offscreen, PyInstaller portable và GitHub Actions Windows.

Không đăng nhập game, không lưu mật khẩu và không gameplay macro. Phase 2 đã có queue/concurrency
lifecycle; Phase 3 chỉ nhận diện hình ảnh, không click hoặc recovery tự động.

Bản sửa lifecycle Phase 1 hỗ trợ **Khởi động khi giả lập đang tắt, chưa có ADB**.
Start kiểm tra đúng index + snapshot + selected + không protected, gửi `launch --index N`,
chờ Android rồi mới resolve/verify ADB. Restart dùng `quit --index N` → chờ dừng →
`launch --index N` → chờ Android → resolve/verify ADB mới. Không dùng serial cũ qua restart.
Các thao tác ADB/game vẫn cần ADB đã xác minh. Chưa nghiệm thu LDPlayer thật.
**103 tests pass trên Windows và macOS**; Windows portable + GUI smoke test pass.
[Tải portable sửa lifecycle](https://github.com/thangnd1993/thangnd-top-heroes/actions/runs/35204186113/artifacts/10489670505).
Xem [tiến độ và kết quả build](docs/PROGRESS.md).

## Dùng bản portable trên Windows

1. Cài LDPlayer trên Windows 10/11 x64; mỗi instance đã cài game và đăng nhập riêng.
2. Trong cài đặt LDPlayer, bật ADB cục bộ cho instance cần quản lý (không cần ADB remote).
3. Tải artifact **TopHeroesAutoManager-Windows-x64** từ tab
   [Actions](https://github.com/thangnd1993/thangnd-top-heroes/actions/workflows/windows.yml).
4. Giải nén **toàn bộ** thư mục, giữ `TopHeroesAutoManager.exe` cạnh `_internal`.
5. Mở `.exe`. Không cần Python, pip, Git hoặc IDE trên máy người dùng cuối.
6. Nếu không tự tìm thấy LDPlayer, chọn thư mục chứa console và adb của **cùng bản cài đặt**.
7. Đánh dấu **Bảo vệ** cho acc chính trước; chọn riêng các clone cần thao tác.
8. Chọn clone đang tắt trong dropdown, bấm **Khởi động**. App chờ Android và tự xác minh ADB.
   Với clone đang chạy sẵn, bấm **Kết nối / xác minh ADB**.
9. Liệt kê ứng dụng để tìm đúng package game, nhập package rồi Lưu; ứng dụng không đoán tên gói.
10. Chụp màn hình và đối chiếu nội dung tài khoản trước khi kiểm tra các thao tác khác.

Bản thử nghiệm chưa ký code signing. macOS chỉ dùng phát triển/kiểm thử GUI; không hỗ trợ chạy LDPlayer.
Chưa được nghiệm thu với LDPlayer thật. Xem [checklist Windows](docs/WINDOWS_TEST.md).

## Quy tắc selected/protected

**Unchecked = không thao tác. Protected = luôn bị chặn.** Giả lập mới mặc định bỏ chọn.
Chọn hiển thị chỉ tác động các hàng khớp tìm kiếm/lọc, bỏ qua protected.
Đánh dấu bảo vệ tự bỏ chọn. Bỏ bảo vệ không tự chọn lại. Refresh chỉ chạy `list2` và merge metadata.
Nếu phát hiện đổi tên, biến mất hoặc xuất hiện lại, app thu hồi lựa chọn; không xóa protection.
Metadata tách theo đường dẫn bản cài LDPlayer để không nhầm index giữa hai bản cài.

Mỗi thao tác thủ công dùng snapshot bất biến cho đúng một instance, chỉ tồn tại trong lúc thao tác.
Execution layer kiểm tra lại whitelist hiện hành và danh sách thật trước lifecycle, trong mỗi lần
poll trạng thái và trước ADB dispatch. Query trạng thái chỉ đọc, không cần ADB hoặc selection.
Start/Stop/Restart trong UI vẫn yêu cầu selected + không protected. Không `quitall`, không default
ADB device, không fallback index 0, không đoán serial theo công thức cổng. Xem [SAFETY.md](docs/SAFETY.md).

Chờ Android tối đa 120 giây; chờ dừng tối đa 60 giây, cộng thời gian CLI đang xử lý (tối đa 20 giây/lệnh).
Nếu startup/ADB thất bại, chỉ thao tác của instance đó bị hủy. Không tự tắt instance đã khởi động,
không chuyển sang instance khác; xem log và làm mới trạng thái trước khi thử lại.

## Phát triển và kiểm thử

Chỉ nhà phát triển cần Python 3.12+ và Git:

```powershell
git clone https://github.com/thangnd1993/thangnd-top-heroes.git
cd thangnd-top-heroes
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python run_app.py
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
```

macOS: dùng `.venv/bin/python` thay đường dẫn Windows. UI khởi động được nhưng discovery/device
control dành cho Windows. Không dùng dữ liệu giả trong app để giả lập kết quả discovery.

## Build portable

Chạy **trên Windows**, không cross-compile `.exe` trên macOS:

```powershell
.\.venv\Scripts\python -m PyInstaller --clean --noconfirm TopHeroesAutoManager.spec
```

Kết quả: `dist/TopHeroesAutoManager/TopHeroesAutoManager.exe` và runtime trong `_internal/`.
CI chạy lint, tests, build và smoke test mở executable. Test này không thay thế nghiệm thu LDPlayer.
Không đóng gói LDPlayer/ADB của hãng vào ứng dụng.

## Dữ liệu và logs

Windows: `%LOCALAPPDATA%\TopHeroesAutoManager\`

- `config.sqlite3`: cấu hình và metadata, không thông tin đăng nhập.
- `logs/app.log`: DEBUG/INFO/WARNING/ERROR, tối đa 2 MB mỗi tệp, 3 bản lưu.
- `screenshots/instance-<index>-<UTC timestamp>.png`: màn hình Android từ ADB.
- `diagnostics/vision/<instance>/`: ảnh chụp, metadata và detection JSON Phase 3.
- `diagnostics/vision/debug/`: overlay anchor/confidence khi bật `--debug`.

Ảnh được giữ nguyên để đối chiếu, không tự xóa. Sao lưu cơ sở dữ liệu khi app đã đóng.
macOS development dùng `~/.local/share/TopHeroesAutoManager/`.

## Cấu trúc

`app/`: orchestration, process boundary, logging startup; `ui/`: Qt;
`ldplayer/`: discovery và parser; `adb/`: transport; `automation/`: safety guard/snapshot;
`storage/`: SQLite; `vision/`: capture, normalize, template matcher, detector, coordinate model,
debug overlay và stability helper.

Tài liệu CLI nguồn: [LDPlayer command line interface](https://www.ldplayer.net/support/introduction-to-ldplayer-command-line-interface.html).
`list2` có 7 trường: index, tên, 2 window handles, Android started, PID, VBox PID.
Không có resolution, DPI, serial hoặc trạng thái game; UI hiển thị **Chưa đọc/Chưa kiểm tra**.

Xem [tiến độ](docs/PROGRESS.md). Phase 3 dừng ở nền tảng nhận diện; chưa bắt đầu Phase 4.
