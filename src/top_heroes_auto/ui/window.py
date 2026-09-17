import logging
import os
import sqlite3
from pathlib import Path

from PySide6.QtCore import QByteArray, QDateTime, QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from top_heroes_auto.app.process import Process
from top_heroes_auto.app.service import Manager
from top_heroes_auto.ldplayer.client import LDPlayer, discover, inspect_folder
from top_heroes_auto.ui.theme import STYLE


class Worker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.result.emit(self.function())
        except Exception as exc:
            logging.getLogger("top_heroes_auto").exception("Thao tác thất bại")
            self.failed.emit(str(exc))


class LogBridge(QObject):
    message = Signal(str)


class UILogHandler(logging.Handler):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))

    def emit(self, record):
        self.bridge.message.emit(self.format(record))


class Window(QMainWindow):
    def __init__(self, store, data_dir):
        super().__init__()
        self.store, self.data_dir = store, data_dir
        self.manager = None
        self.instances = ()
        self.worker = None
        self.mode = ""
        self.setWindowTitle("Top Heroes Auto Manager — V0.1.0")
        self.resize(1440, 920)
        self.setMinimumSize(1080, 740)
        self.setStyleSheet(STYLE)
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 12, 0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(16, 25, 16, 20)
        brand = QLabel("TOP HEROES\nAuto Manager")
        brand.setObjectName("brand")
        nav.addWidget(brand)
        nav.addSpacing(30)
        for title in ("Trang chủ", "Danh sách giả lập", "Hồ sơ tác vụ", "Lịch chạy", "Nhật ký", "Cài đặt"):
            button = QPushButton(title)
            nav.addWidget(button)
            if title in ("Hồ sơ tác vụ", "Lịch chạy"):
                button.setEnabled(False)
                button.setToolTip("Chưa triển khai trong Phase 1")
            elif title == "Cài đặt":
                button.clicked.connect(self.settings)
            elif title == "Nhật ký":
                button.clicked.connect(lambda: self.logs.setFocus())
            else:
                button.clicked.connect(lambda: self.table.setFocus())
        nav.addStretch()
        credit = QLabel("V0.1.0 · Phase 1\n\nPhát triển bởi\nThang Nguyen")
        credit.setObjectName("muted")
        nav.addWidget(credit)
        root.addWidget(sidebar)
        self.content = QWidget()
        layout = QVBoxLayout(self.content)
        root.addWidget(self.content, 1)
        top = QHBoxLayout()
        heading = QLabel("Quản lý giả lập")
        heading.setObjectName("heading")
        top.addWidget(heading)
        top.addStretch()
        self.button(top, "Cài đặt", self.settings)
        self.button(top, "Giới thiệu", self.about)
        layout.addLayout(top)
        tip = QLabel("Chỉ thao tác giả lập đã chọn · Giả lập được bảo vệ luôn bị chặn")
        tip.setObjectName("muted")
        layout.addWidget(tip)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 8, 0, 0)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm tên giả lập / tài khoản…")
        self.search.textChanged.connect(self.render)
        self.filter = QComboBox()
        self.filter.addItems(["Tất cả trạng thái", "Đang chạy", "Đã dừng"])
        self.filter.currentIndexChanged.connect(self.render)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.filter)
        left_layout.addLayout(search_row)
        toolbar = QHBoxLayout()
        self.button(toolbar, "Chọn hiển thị", lambda: self.select_visible(True))
        self.button(toolbar, "Bỏ chọn hiển thị", lambda: self.select_visible(False))
        self.button(toolbar, "Làm mới", self.refresh)
        left_layout.addLayout(toolbar)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Chọn",
                "#",
                "Tên giả lập (Tài khoản)",
                "Trạng thái",
                "Game",
                "Độ phân giải",
                "Bảo vệ",
                "Tự động",
                "Thao tác",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        left_layout.addWidget(self.table, 1)
        self.summary = QLabel("Chưa đọc danh sách LDPlayer")
        left_layout.addWidget(self.summary)
        splitter.addWidget(left)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(320)
        right = QWidget()
        panels = QVBoxLayout(right)
        status = self.group(panels, "Trạng thái LDPlayer")
        self.ld_status = QLabel("Đang kiểm tra…")
        self.ld_status.setWordWrap(True)
        self.ld_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        status.addWidget(self.ld_status)
        self.button(status, "Kiểm tra lại", self.discover_ld)
        self.button(status, "Chọn thư mục LDPlayer", self.pick_folder)
        auto = self.group(panels, "Điều khiển tự động")
        self.auto_start = self.button(auto, "Bắt đầu tự động (0)", lambda: None)
        for button in (
            self.auto_start,
            self.button(auto, "Dừng tất cả", lambda: None),
            self.button(auto, "Tạm dừng", lambda: None),
        ):
            button.setEnabled(False)
            button.setToolTip("Phase 1 chưa có gameplay automation; không gửi lệnh toàn cục.")
        actions = self.group(panels, "Thao tác với giả lập đã chọn")
        self.target = QComboBox()
        self.target.currentIndexChanged.connect(self.target_changed)
        actions.addWidget(self.target)
        self.target_status = QLabel("Chưa chọn giả lập")
        actions.addWidget(self.target_status)
        self.action_buttons = []
        for title, action in (("Khởi động", "launch"), ("Dừng", "quit"), ("Khởi động lại", "reboot")):
            self.action_buttons.append(self.button(actions, title, lambda _, a=action: self.action(a)))
        adb = self.group(panels, "ADB & Game")
        self.adb_status = QLabel("Chưa xác minh ADB")
        self.adb_status.setWordWrap(True)
        adb.addWidget(self.adb_status)
        self.action_buttons.append(self.button(adb, "Kết nối / xác minh ADB", lambda: self.action("verify")))
        self.package = QLineEdit(self.store.get("package"))
        self.package.setPlaceholderText("Tên gói game (chưa cấu hình)")
        adb.addWidget(self.package)
        self.button(adb, "Lưu tên gói", self.save_package)
        for title, action in (
            ("Liệt kê ứng dụng", "packages"),
            ("Mở game", "open_game"),
            ("Đóng game", "close_game"),
            ("Chụp màn hình Android", "screenshot"),
        ):
            self.action_buttons.append(self.button(adb, title, lambda _, a=action: self.action(a)))
        options = self.group(panels, "Tùy chọn thực thi")
        options.addWidget(QLabel("Chưa áp dụng trong Phase 1"))
        for title in ("Số giả lập chạy đồng thời", "Thời gian chờ giữa các tác vụ (giây)"):
            options.addWidget(QLabel(title))
            spin = QSpinBox()
            spin.setMinimum(1)
            spin.setEnabled(False)
            options.addWidget(spin)
        for title in ("Tự động đóng game sau khi xong", "Tự động tắt giả lập sau khi xong"):
            check = QCheckBox(title)
            check.setEnabled(False)
            options.addWidget(check)
        panels.addStretch()
        scroll.setWidget(right)
        splitter.addWidget(scroll)
        splitter.setSizes([850, 330])
        layout.addWidget(QLabel("Nhật ký hoạt động"))
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(1500)
        self.logs.setMaximumHeight(155)
        layout.addWidget(self.logs)
        self.bridge = LogBridge(self)
        self.bridge.message.connect(self.logs.appendPlainText)
        self.log_handler = UILogHandler(self.bridge)
        logging.getLogger("top_heroes_auto").addHandler(self.log_handler)
        self.clock = QLabel()
        self.statusBar().addPermanentWidget(self.clock)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()
        geometry = self.store.get("window_geometry")
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        self.target_changed()
        QTimer.singleShot(0, self.discover_ld)

    @staticmethod
    def button(layout, title, callback):
        button = QPushButton(title)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    @staticmethod
    def group(layout, title):
        group = QGroupBox(title)
        inner = QVBoxLayout(group)
        layout.addWidget(group)
        return inner

    def tick(self):
        self.clock.setText(
            QDateTime.currentDateTime().toString("dd/MM/yyyy HH:mm:ss") + "  ·  Phát triển bởi Thang Nguyen"
        )

    def run_job(self, mode, function):
        if self.worker is not None:
            return
        self.mode = mode
        self.content.setEnabled(False)
        self.statusBar().showMessage("Đang xử lý…")
        self.worker = Worker(function, self)
        self.worker.result.connect(self.job_result)
        self.worker.failed.connect(self.job_error)
        self.worker.finished.connect(self.job_finished)
        self.worker.start()

    @Slot()
    def job_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.content.setEnabled(True)
        self.statusBar().showMessage("Sẵn sàng")
        if self.mode in {"launch", "quit", "reboot"}:
            QTimer.singleShot(0, self.refresh)

    @Slot(str)
    def job_error(self, message):
        self.adb_status.setText("Chưa xác minh / thao tác bị chặn")
        if self.mode in ("discover", "refresh"):
            self.instances = ()
            self.render()
        QMessageBox.warning(self, "Không thực hiện được", message)

    @Slot(object)
    def job_result(self, result):
        if self.mode == "discover":
            self.manager, self.instances = result
            if self.manager:
                install = self.manager.ld.installation
                self.ld_status.setText(f"Đã phát hiện LDPlayer\n{install.console}\nADB: {install.adb}")
                self.store.set("ldplayer_folder", str(install.console.parent))
                self.store.set("adb_path", str(install.adb))
            else:
                self.ld_status.setText(
                    "Chưa phát hiện LDPlayer. Chọn thư mục cài đặt trên Windows."
                    if os.name == "nt"
                    else "Chế độ kiểm tra giao diện trên macOS/Linux. LDPlayer cần Windows."
                )
            self.render()
        elif self.mode == "refresh":
            self.instances = result
            self.render()
        elif self.mode in {"verify", "launch", "reboot"}:
            self.adb_status.setText(str(result))
            self.logs.appendPlainText(str(result))
        elif self.mode == "screenshot":
            self.show_capture(result)
        elif self.mode == "packages":
            dialog = QDialog(self)
            dialog.setWindowTitle("Ứng dụng đã cài trên giả lập đã chọn")
            dialog.resize(680, 500)
            box = QVBoxLayout(dialog)
            text = QPlainTextEdit(str(result))
            text.setReadOnly(True)
            box.addWidget(text)
            dialog.exec()
        else:
            self.logs.appendPlainText(str(result) or "Đã gửi lệnh.")
            self.adb_status.setText("Cần xác minh lại trước thao tác tiếp theo")

    def discover_ld(self):
        if self.worker:
            return
        saved = self.store.get("ldplayer_folder")

        def work():
            installation = discover(saved)
            manager = (
                Manager(LDPlayer(installation, Process()), self.store, self.data_dir)
                if installation
                else None
            )
            return manager, manager.refresh() if manager else ()

        self.run_job("discover", work)

    def pick_folder(self):
        if self.worker:
            return
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa ldconsole.exe và adb.exe")
        if folder:
            if not inspect_folder(Path(folder)):
                QMessageBox.warning(
                    self, "Thư mục không hợp lệ", "Cần ldconsole.exe hoặc dnconsole.exe và adb.exe."
                )
                return
            self.store.set("ldplayer_folder", folder)
            self.discover_ld()

    def refresh(self):
        if self.manager:
            self.run_job("refresh", self.manager.refresh)
        else:
            self.discover_ld()

    def visible_instances(self):
        query, state = self.search.text().casefold(), self.filter.currentIndex()
        return [
            i
            for i in self.instances
            if query in i.name.casefold()
            and (state == 0 or (state == 1 and i.running) or (state == 2 and not i.running))
        ]

    def render(self):
        if not hasattr(self, "table"):
            return
        self.table.setRowCount(0)
        previous = self.target.currentData()
        self.target.blockSignals(True)
        self.target.clear()
        count = 0
        if self.manager:
            for instance in self.instances:
                meta = self.store.metadata(self.manager.namespace, instance.index)
                if meta.selected and not meta.protected:
                    self.target.addItem(f"#{instance.index} · {instance.name}", instance.index)
                    count += 1
            for row, instance in enumerate(self.visible_instances()):
                self.table.insertRow(row)
                meta = self.store.metadata(self.manager.namespace, instance.index)
                check = QCheckBox()
                check.setChecked(meta.selected)
                check.setEnabled(not meta.protected)
                check.toggled.connect(lambda value, i=instance.index: self.set_selection(i, value))
                self.table.setCellWidget(row, 0, check)
                values = {
                    1: str(instance.index),
                    2: instance.name,
                    3: "Đang chạy" if instance.running else "Đã dừng",
                    4: "Chưa kiểm tra",
                    5: "Chưa đọc",
                    7: "Chưa triển khai",
                }
                for column, text in values.items():
                    self.table.setItem(row, column, QTableWidgetItem(text))
                protect = QCheckBox("Có" if meta.protected else "Không")
                protect.setChecked(meta.protected)
                protect.toggled.connect(lambda value, i=instance.index: self.set_protection(i, value))
                self.table.setCellWidget(row, 6, protect)
                focus = QPushButton("Xem")
                focus.setEnabled(meta.selected and not meta.protected)
                focus.clicked.connect(
                    lambda _, i=instance.index: self.target.setCurrentIndex(self.target.findData(i))
                )
                self.table.setCellWidget(row, 8, focus)
        if previous is not None:
            self.target.setCurrentIndex(self.target.findData(previous))
        self.target.blockSignals(False)
        self.summary.setText(f"{len(self.instances)} giả lập · {count} được chọn · Giả lập mới luôn bỏ chọn")
        self.auto_start.setText(f"Bắt đầu tự động ({count})")
        self.target_changed()

    def target_changed(self):
        if not hasattr(self, "action_buttons"):
            return
        index = self.target.currentData()
        instance = next((i for i in self.instances if i.index == index), None)
        self.target_status.setText(
            ("Đang chạy" if instance.running else "Đã dừng") if instance else "Chưa chọn giả lập"
        )
        self.adb_status.setText("Chưa xác minh ADB cho thao tác tiếp theo")
        for button in self.action_buttons:
            button.setEnabled(instance is not None)

    def set_selection(self, index, value):
        try:
            self.manager.select(index, value)
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Không lưu được lựa chọn", str(exc))
        self.render()

    def set_protection(self, index, value):
        try:
            self.manager.protect(index, value)
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Không lưu được bảo vệ", str(exc))
        self.render()

    def select_visible(self, value):
        if self.manager and not self.worker:
            for instance in self.visible_instances():
                if not self.store.metadata(self.manager.namespace, instance.index).protected:
                    self.manager.select(instance.index, value)
            self.render()

    def action(self, action):
        index = self.target.currentData()
        if index is not None and self.manager:
            package = self.package.text().strip()
            self.run_job(action, lambda: self.manager.execute(index, action, package))

    def save_package(self):
        from top_heroes_auto.adb.client import validate_package

        try:
            package = self.package.text().strip()
            if package:
                validate_package(package)
            self.store.set("package", package)
            self.logs.appendPlainText("Đã lưu tên gói game.")
        except ValueError as exc:
            QMessageBox.warning(self, "Tên gói không hợp lệ", str(exc))
        except RuntimeError as exc:
            QMessageBox.warning(self, "Tên gói không hợp lệ", str(exc))

    def show_capture(self, path):
        dialog = QDialog(self)
        dialog.setWindowTitle("Ảnh màn hình Android từ ADB")
        layout = QVBoxLayout(dialog)
        label = QLabel()
        pixmap = QPixmap(str(path))
        label.setPixmap(
            pixmap.scaled(
                800, 650, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        layout.addWidget(label)
        location = QLabel(str(path))
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(location)
        dialog.exec()

    def settings(self):
        if not self.worker:
            self.pick_folder()

    def about(self):
        QMessageBox.information(
            self,
            "Giới thiệu",
            "Top Heroes Auto Manager\nV0.1.0 — Phase 1\n"
            "Phát triển bởi Thang Nguyen\n\nMột giả lập = một tài khoản.\n"
            "Chưa triển khai gameplay automation.\n\nDữ liệu: " + str(self.data_dir),
        )

    def closeEvent(self, event: QCloseEvent):
        if self.worker is not None:
            self.statusBar().showMessage("Vui lòng chờ thao tác hiện tại kết thúc trước khi đóng.")
            event.ignore()
            return
        self.store.set("window_geometry", bytes(self.saveGeometry().toBase64()).decode("ascii"))
        logging.getLogger("top_heroes_auto").removeHandler(self.log_handler)
        event.accept()
