import logging
import os
import sqlite3
import threading
from pathlib import Path

from PySide6.QtCore import QByteArray, QDateTime, Qt, QThread, QTimer, Signal, Slot
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

from top_heroes_auto.app.automation_controller import AutomationController
from top_heroes_auto.app.diagnostic_bundle import export_bundle
from top_heroes_auto.app.free_reward_tasks import (
    PHASE6_TARGET,
    run_free_reward_task,
)
from top_heroes_auto.app.phase6_runtime import promo_recovery_factory
from top_heroes_auto.app.phase6_shop_navigation_tasks import (
    SHOP_NAVIGATION_LABEL,
    SHOP_NAVIGATION_TASK,
    run_phase6_shop_navigation,
)
from top_heroes_auto.app.phase6_shop_survey_tasks import (
    SHOP_SURVEY_LABEL,
    SHOP_SURVEY_TASK,
    run_phase6_shop_survey,
)
from top_heroes_auto.app.phase6_vip_survey_tasks import (
    VIP_SURVEY_LABEL,
    VIP_SURVEY_TASK,
    run_phase6_vip_survey,
)
from top_heroes_auto.app.process import Process
from top_heroes_auto.app.recovery_cli import run_home_recovery
from top_heroes_auto.app.registered_tasks import run_registered_selected
from top_heroes_auto.app.service import Manager
from top_heroes_auto.app.task_cli import run_idle_reward_diagnostic
from top_heroes_auto.app.version_info import APP_NAME, load_version_info
from top_heroes_auto.ldplayer.client import LDPlayer, discover, inspect_folder
from top_heroes_auto.ldplayer.identity import runtime_key
from top_heroes_auto.storage.store import AccountStatus
from top_heroes_auto.ui.operational_log import OperationalLogHandler
from top_heroes_auto.ui.run_progress import RunProgress, format_elapsed
from top_heroes_auto.ui.theme import STYLE
from top_heroes_auto.vision.detector import ScreenDetector
from top_heroes_auto.vision.resources import template_folder
from top_heroes_auto.vision.screenshot import ScreenshotService


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


class Window(QMainWindow):
    run_progress = Signal(int, int, object, str)

    def __init__(self, store, data_dir):
        super().__init__()
        self.store, self.data_dir = store, data_dir
        self.manager = None
        self.instances = ()
        self.worker = None
        self.mode = ""
        self.phase6_cancelled = threading.Event()
        self.run_controller = None
        self.run_states = {}
        self.version = load_version_info()
        self.progress = RunProgress()
        self.setWindowTitle(f"{APP_NAME} — {self.version.summary}")
        self.resize(1440, 920)
        self.setMinimumSize(1180, 740)
        self.setStyleSheet(STYLE)
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 12, 0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(168)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(16, 25, 16, 20)
        brand = QLabel("TOP HEROES\nAuto Manager")
        brand.setObjectName("brand")
        nav.addWidget(brand)
        nav.addSpacing(30)
        for title in ("Trang chủ", "Danh sách giả lập", "Hồ sơ tác vụ", "Lịch chạy", "Nhật ký", "Cài đặt"):
            button = QPushButton(title)
            nav.addWidget(button)
            if title == "Lịch chạy":
                button.setEnabled(False)
                button.setToolTip("Chưa triển khai trong Phase 1")
            elif title == "Hồ sơ tác vụ":
                button.clicked.connect(lambda: self.idle_reward_enabled.setFocus())
            elif title == "Cài đặt":
                button.clicked.connect(self.settings)
            elif title == "Nhật ký":
                button.clicked.connect(lambda: self.logs.setFocus())
            else:
                button.clicked.connect(lambda: self.table.setFocus())
        nav.addStretch()
        credit = QLabel(f"V{self.version.version}\n{self.version.short_commit}\n{self.version.release_date}\n"
                        f"{self.version.channel}\n\nPhát triển bởi\nThang Nguyen")
        credit.setToolTip(f"Commit đầy đủ: {self.version.commit}\nCI run: {self.version.ci_run}")
        credit.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
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
        self.cards = {}
        cards = QHBoxLayout()
        for key, title in (("version", "Phiên bản"), ("run", "Lượt chạy"), ("fleet", "Giả lập"),
                           ("workers", "Worker hoạt động"), ("done", "Tài khoản hoàn tất"), ("verified", "Quà đã xác minh")):
            card = QFrame()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.setContentsMargins(12, 8, 12, 8)
            box.setSpacing(2)
            caption = QLabel(title)
            caption.setObjectName("cardTitle")
            value = QLabel("—")
            value.setObjectName("cardValue")
            value.setWordWrap(True)
            box.addWidget(caption)
            box.addWidget(value)
            cards.addWidget(card, 3 if key == "version" else 2 if key in {"fleet", "run"} else 1)
            self.cards[key] = value
        layout.addLayout(cards)
        self.warning_banner = QLabel()
        self.warning_banner.setObjectName("warning")
        self.warning_banner.setWordWrap(True)
        self.warning_banner.hide()
        layout.addWidget(self.warning_banner)
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
                "ID",
                "Tên hiển thị",
                "Trạng thái",
                "Kết quả gần nhất",
                "Android",
                "Bảo vệ",
                "Tiến độ tự động",
                "Thao tác",
            ]
        )
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        left_layout.addWidget(self.table, 1)
        self.summary = QLabel("Chưa đọc danh sách LDPlayer")
        left_layout.addWidget(self.summary)
        splitter.addWidget(left)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(340)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right = QWidget()
        panels = QVBoxLayout(right)
        auto = self.group(panels, "Điều khiển tự động")
        self.run_scope = QComboBox()
        self.run_scope.addItems(['Các tài khoản đã chọn', 'Tất cả tài khoản không bảo vệ'])
        self.run_scope.setAccessibleName('Phạm vi chạy tự động')
        self.run_scope.currentIndexChanged.connect(lambda _: self.render())
        auto.addWidget(self.run_scope)
        scope_note = QLabel('Idle · VIP · BXH · Tiệm · Hội · Thư · Event\nChỉ nhận quà đủ điều kiện; giữ khóa chống nhận lặp.')
        scope_note.setWordWrap(True)
        auto.addWidget(scope_note)
        auto.addWidget(QLabel("Số tài khoản chạy đồng thời"))
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 2)
        self.concurrency.setAccessibleName('Số tài khoản chạy đồng thời')
        self.concurrency.setValue(int(self.store.get("max_concurrency", "2")))
        self.concurrency.valueChanged.connect(lambda value: self.store.set("max_concurrency", str(value)))
        auto.addWidget(self.concurrency)
        concurrency_note = QLabel("Mỗi tài khoản chạy hết kế hoạch rồi mới chuyển tài khoản tiếp theo.")
        concurrency_note.setObjectName("muted")
        concurrency_note.setWordWrap(True)
        auto.addWidget(concurrency_note)
        self.auto_start = self.button(auto, "▶ Bắt đầu tự động (0)", self.start_selected)
        self.auto_start.setObjectName("primary")
        self.auto_stop = self.button(auto, "■ Dừng tự động", self.stop_run)
        self.auto_stop.setObjectName("danger")
        self.auto_pause = self.button(auto, "Tạm dừng", self.pause_run)
        self.retry_failed = self.button(auto, "Thử lại lỗi", self.retry_run)
        for button in (self.auto_stop, self.auto_pause, self.retry_failed):
            button.setEnabled(False)
        status = self.group(panels, "Trạng thái LDPlayer")
        self.ld_status = QLabel("Đang kiểm tra…")
        self.ld_status.setWordWrap(True)
        self.ld_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        status.addWidget(self.ld_status)
        self.button(status, "Kiểm tra lại", self.discover_ld)
        self.button(status, "Chọn thư mục LDPlayer", self.pick_folder)
        self.advanced_toggle = QCheckBox("Công cụ nâng cao (ADB, nhận diện, tác vụ thử)")
        panels.addWidget(self.advanced_toggle)
        self.advanced = QWidget()
        main_panels, panels = panels, QVBoxLayout(self.advanced)
        panels.setContentsMargins(0, 0, 0, 0)
        main_panels.addWidget(self.advanced)
        self.advanced.setVisible(False)
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        self.advanced_toggle.toggled.connect(lambda value: self.table.setColumnHidden(8, not value))
        self.table.setColumnHidden(8, True)
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
        vision = self.group(panels, "Nhận diện màn hình")
        self.vision_status = QLabel("Màn hình hiện tại: Chưa nhận diện\nĐộ tin cậy: —")
        self.vision_status.setWordWrap(True)
        vision.addWidget(self.vision_status)
        self.action_buttons.append(self.button(vision, "Nhận diện màn hình", self.detect_screen))
        self.action_buttons.append(self.button(vision, "Về trang chủ game", self.recover_home))
        tasks = self.group(panels, "Hồ sơ tác vụ")
        self.idle_reward_enabled = QCheckBox("Thưởng treo máy")
        self.idle_reward_enabled.setChecked(self.store.get("task_idle_reward_enabled", "1") == "1")
        self.idle_reward_enabled.toggled.connect(
            lambda value: self.store.set("task_idle_reward_enabled", "1" if value else "0")
        )
        self.idle_reward_enabled.toggled.connect(lambda _: self.target_changed())
        tasks.addWidget(self.idle_reward_enabled)
        self.idle_reward_status = QLabel("Kết quả gần nhất: —")
        self.idle_reward_status.setWordWrap(True)
        tasks.addWidget(self.idle_reward_status)
        self.idle_reward_button = self.button(tasks, "Chạy thử tác vụ", self.run_idle_reward)
        self.action_buttons.append(self.idle_reward_button)
        self.phase6_eligibility = QLabel(
            "Phase 6 chỉ cho phép #2 / 5-Emmmmm; các claim thiếu zero-cost/post-condition "
            "sẽ dừng NOT_IMPLEMENTED."
        )
        self.phase6_eligibility.setWordWrap(True)
        tasks.addWidget(self.phase6_eligibility)
        self.phase6_status = QLabel("Kết quả Phase 6 gần nhất: —")
        self.phase6_status.setWordWrap(True)
        tasks.addWidget(self.phase6_status)
        self.phase6_buttons = []
        self.fixed_reward_buttons = []
        for title, task in (
            ("VIP miễn phí", "vip-reward"),
            ("Quà Tiệm miễn phí", "free-pack"),
            ("Recruit miễn phí", "free-recruit"),
            ("Rương BXH (an toàn)", "ranking-chest"),
        ):
            button = self.button(tasks, title, lambda _, value=task: self.run_phase6_task(value))
            self.phase6_buttons.append(button)
            if task in {"free-pack", "ranking-chest"}:
                self.fixed_reward_buttons.append(button)
            self.action_buttons.append(button)
        self.phase6_sequence_button = self.button(tasks, "Phase 6 theo chuỗi", self.run_phase6_sequence)
        self.phase6_buttons.append(self.phase6_sequence_button)
        self.action_buttons.append(self.phase6_sequence_button)
        self.phase6_shop_survey_button = self.button(
            tasks,
            SHOP_NAVIGATION_LABEL,
            self.run_phase6_shop_navigation,
        )
        self.phase6_buttons.append(self.phase6_shop_survey_button)
        self.action_buttons.append(self.phase6_shop_survey_button)
        self.phase6_shop_broad_survey_button = self.button(
            tasks,
            SHOP_SURVEY_LABEL,
            self.run_phase6_shop_survey,
        )
        self.phase6_buttons.append(self.phase6_shop_broad_survey_button)
        self.action_buttons.append(self.phase6_shop_broad_survey_button)
        self.phase6_vip_survey_button = self.button(
            tasks,
            VIP_SURVEY_LABEL,
            self.run_phase6_vip_survey,
        )
        self.phase6_buttons.append(self.phase6_vip_survey_button)
        self.action_buttons.append(self.phase6_vip_survey_button)
        self.phase6_cancel_button = self.button(tasks, "Hủy Phase 6", self.cancel_phase6)
        self.phase6_cancel_button.setEnabled(False)
        main_panels.addStretch()
        scroll.setWidget(right)
        splitter.addWidget(scroll)
        splitter.setSizes([820, 360])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        log_tools = QHBoxLayout()
        self.run_label = QLabel('Lượt chạy: chưa bắt đầu')
        with self.store.connect() as db:
            latest = db.execute('SELECT id,status FROM runs ORDER BY id DESC LIMIT 1').fetchone()
        if latest:
            self.run_label.setText(f'Lượt gần nhất {latest[0]}: {latest[1]}')
        log_tools.addWidget(self.run_label)
        self.technical_logs = QCheckBox('Chi tiết kỹ thuật')
        log_tools.addWidget(self.technical_logs)
        self.button(log_tools, 'Mở logs', self.open_logs)
        self.button(log_tools, 'Sao chép tóm tắt lượt chạy', self.copy_run_summary)
        self.button(log_tools, 'Xuất gói chẩn đoán', self.export_diagnostics)
        layout.addLayout(log_tools)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(1500)
        self.logs.setMaximumHeight(155)
        layout.addWidget(self.logs)
        self.run_progress.connect(self.update_run_progress)
        self.log_handler = OperationalLogHandler()
        self.technical_logs.toggled.connect(lambda value: setattr(self.log_handler, 'technical', value))
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.flush_logs)
        self.log_timer.start(250)
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
        self.update_dashboard()

    def flush_logs(self):
        messages = self.log_handler.drain()
        if messages:
            self.logs.appendPlainText('\n'.join(messages))
        events = self.log_handler.drain_flow_events()
        for index, flow, state, message in events:
            self.progress.flow_event(index, flow, state, message)
        if events:
            self.sync_run_states()
            self.render()

    def sync_run_states(self):
        for index, account in self.progress.accounts.items():
            self.run_states[index] = account.line()

    def update_dashboard(self):
        """Refresh the summary cards from real state only; unknown values stay unknown."""
        if not hasattr(self, "cards"):
            return
        manager = self.manager
        total = len(self.instances)
        eligible = selected = 0
        if manager:
            for instance in self.instances:
                meta = self.store.metadata(manager.namespace, instance.index)
                eligible += not meta.protected
                selected += meta.selected and not meta.protected
        running = sum(1 for i in self.instances if i.running)
        self.cards["version"].setText(self.version.summary)
        self.cards["version"].setToolTip(f"Commit: {self.version.commit}\nCI run: {self.version.ci_run}")
        self.cards["fleet"].setText(f"{total} tổng · {eligible} khả dụng · {selected} chọn")
        self.cards["fleet"].setToolTip(f"{running} giả lập đang chạy; {total - eligible} được bảo vệ")
        run_id = self.progress.run_id
        counts = dict(accounts=0, finished=0, verified=0)
        if run_id is not None:
            try:
                counts = self.store.run_dashboard(run_id)
            except sqlite3.Error:
                logging.getLogger("top_heroes_auto").debug("Dashboard counts unavailable", exc_info=True)
        busy = self.worker is not None and self.mode == "run"
        self.cards["run"].setText("Chưa bắt đầu" if run_id is None else
                                  f"#{run_id} · {format_elapsed(self.progress.elapsed())}" + ("" if busy else " · đã dừng"))
        self.cards["workers"].setText(f"{self.progress.active_workers()}/{self.concurrency.value()}")
        self.cards["done"].setText(f"{counts['finished']}/{counts['accounts']}" if run_id is not None else "—")
        self.cards["verified"].setText(str(counts["verified"]) if run_id is not None else "—")
        blocked = sum(a.blocked for a in self.progress.accounts.values())
        warnings = []
        if manager is None:
            warnings.append("Chưa phát hiện LDPlayer.")
        if blocked:
            warnings.append(f"{blocked} mục bị chặn trong lượt này; mở Chi tiết kỹ thuật hoặc xuất gói chẩn đoán.")
        self.warning_banner.setText(" ".join(warnings))
        self.warning_banner.setVisible(bool(warnings))

    def export_diagnostics(self):
        try:
            path = export_bundle(self.data_dir, self.progress.run_id)
        except (ValueError, OSError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Không xuất được gói chẩn đoán", str(exc))
            return
        self.logs.appendPlainText(f"Đã xuất gói chẩn đoán (chỉ đọc, không xóa dữ liệu): {path}")
        QMessageBox.information(self, "Gói chẩn đoán", f"Đã tạo:\n{path}")

    def open_logs(self):
        folder = self.data_dir / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))

    def copy_run_summary(self):
        from PySide6.QtWidgets import QApplication

        with self.store.connect() as db:
            run = db.execute('SELECT id,status,started_at,finished_at,max_concurrency FROM runs ORDER BY id DESC LIMIT 1').fetchone()
        if run is None:
            text = 'Chưa có lượt chạy.'
        else:
            run_id, status, start, end, concurrency = run
            report = self.store.get(f'automation-report:{run_id}')
            text = f'Run {run_id}: {status}\nBắt đầu: {start}\nKết thúc: {end}\nWorkers: {concurrency}\nReport: {report}\nLogs: {self.data_dir / "logs"}'
            self.run_label.setText(f'Lượt chạy {run_id}: {status}')
        QApplication.clipboard().setText(text)

    def run_job(self, mode, function):
        if self.worker is not None:
            return
        self.mode = mode
        if mode not in {"run", "phase6"}:
            self.content.setEnabled(False)
        else:
            for button in self.action_buttons:
                button.setEnabled(False)
            self.target.setEnabled(False)
            if mode == "phase6":
                self._set_phase6_busy(True)
                self.phase6_cancel_button.setEnabled(True)
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
        self.auto_stop.setEnabled(False)
        self.auto_pause.setEnabled(False)
        self.auto_pause.setText("Tạm dừng")
        if self.mode == "phase6":
            self._set_phase6_busy(False)
            self.phase6_cancel_button.setEnabled(False)
            self.phase6_cancelled.clear()
        if self.mode == "run":
            self.retry_failed.setEnabled(True)
            self.run_scope.setEnabled(True)
            self.concurrency.setEnabled(True)
        self.statusBar().showMessage("Sẵn sàng")
        if self.mode in {"launch", "quit", "reboot", "idle-reward", "phase6", "run"}:
            QTimer.singleShot(0, self.refresh)
        # Refresh rendered while its worker was still active. Recompute Start
        # eligibility now that it has finished, without changing selections.
        self.render()

    @Slot(str)
    def job_error(self, message):
        self.adb_status.setText("Chưa xác minh / thao tác bị chặn")
        if self.mode == "idle-reward":
            self.idle_reward_status.setText("Kết quả gần nhất: Lỗi")
        if self.mode == "phase6":
            self.phase6_status.setText(f"Phase 6 lỗi: {message}")
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
        elif self.mode == "vision":
            labels = {
                "UNKNOWN": "Không xác định",
                "ANDROID_HOME": "Màn hình Android",
                "GAME_LOADING": "Đang tải game",
                "GAME_HOME": "Trang chủ game",
                "POPUP_GENERIC": "Popup",
                "LOGIN_ASSISTANCE": "Thông báo hỗ trợ Hội",
                "CONNECTION_ERROR": "Lỗi kết nối",
                "UPDATE_NOTICE": "Thông báo cập nhật",
            }
            self.vision_status.setText(
                f"Màn hình hiện tại: {labels.get(result.state.value, result.state.value)}\n"
                f"Độ tin cậy: {result.confidence:.0%}"
            )
            self.logs.appendPlainText(
                f"Nhận diện {result.state.value} · {result.confidence:.3f} · {result.duration_ms:.1f} ms"
            )
        elif self.mode == "recovery":
            recovery, report, started = result
            labels = {
                "SUCCESS": "Đã về trang chủ game",
                "ALREADY_HOME": "Đã ở trang chủ game",
                "UNKNOWN_SCREEN": "Không thể xác định màn hình",
                "LOADING_TIMEOUT": "Game tải quá thời gian",
                "CANCELLED": "Đã hủy",
            }
            self.vision_status.setText(
                f"Trạng thái: {labels.get(recovery.status.value, recovery.status.value)}\n"
                f"Bước: {len(recovery.steps)} · ADB: {recovery.adb_target or '—'}"
            )
            self.logs.appendPlainText(
                f"Recovery {recovery.status.value} · started_by_run={started} · report={report}"
            )
        elif self.mode == "idle-reward":
            task_result, report, started, task_run_id = result
            labels = {
                "SUCCESS": "Thành công",
                "NOT_AVAILABLE": "Chưa thể nhận",
                "CANCELLED": "Đã hủy",
            }
            self.idle_reward_status.setText(
                f"Kết quả gần nhất: {labels.get(task_result.status.value, 'Lỗi')}\n"
                f"Task run #{task_run_id} · ADB: {task_result.adb_target or '—'}"
            )
            self.logs.appendPlainText(
                f"Idle Reward {task_result.status.value} · started_by_run={started} · report={report}"
            )
        elif self.mode == "phase6":
            if isinstance(result, list):
                statuses = ", ".join(f"{item.task}: {item.status}" for item in result)
                self.phase6_status.setText(f"Phase 6 chuỗi: {statuses}")
                self.logs.appendPlainText(f"Phase 6 chuỗi: {statuses}")
            else:
                status = getattr(result, "status", "UNKNOWN")
                task = getattr(result, "task", "phase6")
                report = getattr(result, "report_path", None)
                error = getattr(result, "error", None)
                if task == SHOP_NAVIGATION_TASK:
                    navigation = getattr(result, "navigation", None)
                    navigation_status = getattr(navigation, "status", None)
                    navigation_status = getattr(navigation_status, "value", navigation_status)
                    detail = f"{SHOP_NAVIGATION_LABEL}: {status}"
                    if navigation_status:
                        detail += f" · navigation={navigation_status}"
                elif task == SHOP_SURVEY_TASK:
                    survey = getattr(result, "survey", None)
                    survey_status = getattr(survey, "status", None)
                    survey_status = getattr(survey_status, "value", survey_status)
                    detail = f"{SHOP_SURVEY_LABEL}: {status}"
                    if survey_status:
                        detail += f" · survey={survey_status}"
                    if survey is not None:
                        detail += f" · coverage={'complete' if survey.coverage_complete else 'partial'}"
                        if survey.partial_reasons:
                            detail += f" · gaps={','.join(survey.partial_reasons[:2])}"
                elif task == VIP_SURVEY_TASK:
                    survey = getattr(result, "survey", None)
                    survey_status = getattr(survey, "status", None)
                    survey_status = getattr(survey_status, "value", survey_status)
                    detail = f"{VIP_SURVEY_LABEL}: {status}"
                    if survey_status:
                        detail += f" · survey={survey_status}"
                else:
                    detail = f"Phase 6 {task}: {status}"
                if error:
                    detail += f" · {error}"
                self.phase6_status.setText(detail)
                self.logs.appendPlainText(f"{detail} · report={report}")
        elif self.mode == "packages":
            dialog = QDialog(self)
            dialog.setWindowTitle("Ứng dụng đã cài trên giả lập đã chọn")
            dialog.resize(680, 500)
            box = QVBoxLayout(dialog)
            text = QPlainTextEdit(str(result))
            text.setReadOnly(True)
            box.addWidget(text)
            dialog.exec()
        elif self.mode == "run":
            run_id, rows = result
            counts = {"SUCCESS": 0, "FAILED": 0, "CANCELLED": 0}
            for _, _, status, _, _, _ in rows:
                counts[str(status)] = counts.get(str(status), 0) + 1
            self.logs.appendPlainText(
                f"RUN {run_id}: Thành công {counts['SUCCESS']} · Lỗi {counts['FAILED']} · Đã hủy {counts['CANCELLED']}"
            )
            report = self.store.get(f'automation-report:{run_id}')
            if report:
                self.logs.appendPlainText(f'Báo cáo chi tiết: {report}')
            self.render()
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
                account = self.progress.accounts.get(instance.index)
                android = ("Sẵn sàng" if instance.running and instance.android_started
                           else "Đang khởi động" if instance.running else "Đã tắt")
                values = {
                    1: str(instance.index),
                    2: instance.name,
                    3: "Đang chạy" if instance.running else "Đã dừng",
                    4: (account.detail[:60] if account and account.detail else "—"),
                    5: android,
                    7: self.run_states.get(instance.index, "Chưa chạy"),
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
            previous_index = self.target.findData(previous)
            if previous_index >= 0:
                self.target.setCurrentIndex(previous_index)
        self.target.blockSignals(False)
        self.summary.setText(f"{len(self.instances)} giả lập · {count} được chọn · Giả lập mới luôn bỏ chọn")
        run_count = (sum(not self.store.metadata(self.manager.namespace, i.index).protected for i in self.instances)
                     if self.manager and self.run_scope.currentIndex() == 1 else count)
        self.auto_start.setText(f"Bắt đầu tự động ({run_count})")
        self.auto_start.setEnabled(self.manager is not None and self.worker is None and run_count > 0)
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
        if self.manager and index is not None:
            latest = self.store.latest_task_run(self.manager.namespace, "idle-reward", index)
            if latest:
                labels = {"SUCCESS": "Thành công", "NOT_AVAILABLE": "Chưa thể nhận"}
                self.idle_reward_status.setText(
                    f"Kết quả gần nhất: {labels.get(latest[2], 'Lỗi')} · #{latest[0]}"
                )
            else:
                self.idle_reward_status.setText("Kết quả gần nhất: —")
        for button in self.action_buttons:
            button.setEnabled(instance is not None and not (self.worker is not None and self.mode == "run"))
        self.idle_reward_button.setEnabled(
            instance is not None
            and self.idle_reward_enabled.isChecked()
            and self.worker is None
        )
        self.update_phase6_controls(instance)

    def update_phase6_controls(self, instance):
        """Enable Phase 6 controls only for the explicit authorized target."""

        allowed = False
        reason = "Phase 6 chỉ cho phép #2 / 5-Emmmmm."
        index = self.target.currentData()
        if self.manager and instance and runtime_key((index, instance.name)) == runtime_key(PHASE6_TARGET):
            try:
                metadata = self.store.metadata(self.manager.namespace, index)
                queen = self.store.metadata(self.manager.namespace, 0)
                allowed = bool(metadata.selected and not metadata.protected and queen.protected)
                if not allowed:
                    reason = "Phase 6 cần target selected/not Protected và Queen Protected."
            except (KeyError, ValueError, sqlite3.Error) as exc:
                reason = f"Phase 6 guard chưa xác minh: {exc}"
        elif instance is not None:
            reason = "Phase 6 chỉ cho phép #2 / 5-Emmmmm."
        if allowed:
            reason += " Free Pack vẫn sẽ báo NOT_IMPLEMENTED nếu thiếu zero-cost/post evidence."
        self.phase6_eligibility.setText(reason)
        enabled = allowed and self.worker is None
        for button in self.phase6_buttons:
            button.setEnabled(enabled)
        fixed_allowed = False
        if self.manager and instance:
            metadata = self.store.metadata(self.manager.namespace, index)
            fixed_allowed = metadata.selected and not metadata.protected
        for button in self.fixed_reward_buttons:
            button.setEnabled(fixed_allowed and self.worker is None)
        if fixed_allowed:
            self.phase6_eligibility.setText("BXH/Tiệm: tài khoản đã chọn, không Protected; chỉ nhận quà miễn phí.")

    def _set_phase6_busy(self, busy):
        """Lock mutable UI state while leaving the cooperative cancel button live."""

        for widget in (
            self.search,
            self.filter,
            self.table,
            self.idle_reward_enabled,
            self.concurrency,
            self.auto_start,
        ):
            widget.setEnabled(not busy)

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

    def detect_screen(self):
        index = self.target.currentData()
        if index is None or not self.manager:
            return

        def work():
            target, payload = self.manager.capture_verified(index)
            service = ScreenshotService(lambda serial: payload if serial == target.serial else b"")
            screen = service.take(target)
            return ScreenDetector.from_folder(template_folder()).detect(screen)

        self.run_job("vision", work)

    def recover_home(self):
        index = self.target.currentData()
        if index is None or not self.manager:
            return
        instance = next((item for item in self.instances if item.index == index), None)
        if instance is None:
            return
        self.vision_status.setText("Trạng thái: Đang xử lý\nĐang xử lý: Khôi phục trang chủ game")
        self.run_job(
            "recovery",
            lambda: run_home_recovery(self.manager, self.data_dir, index, instance.name),
        )

    def run_idle_reward(self):
        index = self.target.currentData()
        if index is None or not self.manager or not self.idle_reward_enabled.isChecked():
            return
        instance = next((item for item in self.instances if item.index == index), None)
        if instance is None:
            return
        self.idle_reward_status.setText("Kết quả gần nhất: Đang chạy…")
        self.run_job(
            "idle-reward",
            lambda: run_idle_reward_diagnostic(
                self.manager,
                self.data_dir,
                index,
                instance.name,
            ),
        )

    def _phase6_target(self, fixed=False):
        index = self.target.currentData()
        instance = next((item for item in self.instances if item.index == index), None)
        if not self.manager or instance is None or (not fixed and runtime_key((index, instance.name)) != runtime_key(PHASE6_TARGET)):
            return None
        self.update_phase6_controls(instance)
        try:
            metadata = self.store.metadata(self.manager.namespace, index)
            queen = self.store.metadata(self.manager.namespace, 0)
        except (KeyError, ValueError, sqlite3.Error) as exc:
            self.phase6_eligibility.setText(f"Phase 6 guard chưa xác minh: {exc}")
            return None
        if not metadata.selected or metadata.protected or not queen.protected:
            return None
        return index, instance.name

    def run_phase6_task(self, task):
        fixed = task in {"free-pack", "ranking-chest"}
        target = self._phase6_target(fixed=fixed)
        if target is None or self.worker:
            return
        index, name = target
        self.phase6_cancelled.clear()
        self.phase6_status.setText(f"Phase 6 {task}: đang chạy…")
        runner = run_free_reward_task
        if fixed:
            from top_heroes_auto.app.bxh_shop_acceptance import run_selected_task

            runner = run_selected_task
        self.run_job(
            "phase6",
            lambda: runner(
                self.manager,
                self.data_dir,
                index,
                name,
                task,
                cancelled=self.phase6_cancelled.is_set,
            ),
        )

    def run_phase6_sequence(self):
        target = self._phase6_target()
        if target is None or self.worker:
            return
        index, name = target
        self.phase6_cancelled.clear()
        self.phase6_status.setText("Phase 6 chuỗi: đang chạy…")
        self.run_job(
            "phase6",
            lambda: run_registered_selected(
                self.manager,
                self.data_dir,
                index,
                name,
                cancelled=self.phase6_cancelled.is_set,
            ),
        )

    def run_phase6_shop_navigation(self):
        target = self._phase6_target()
        if target is None or self.worker:
            return
        index, name = target
        self.phase6_cancelled.clear()
        self.phase6_status.setText(f"{SHOP_NAVIGATION_LABEL}: đang chạy…")
        self.run_job(
            "phase6",
            lambda: run_phase6_shop_navigation(
                self.manager,
                self.data_dir,
                index,
                name,
                cancelled=self.phase6_cancelled.is_set,
                promo_recovery_factory=promo_recovery_factory,
            ),
        )

    def run_phase6_shop_survey(self):
        target = self._phase6_target()
        if target is None or self.worker:
            return
        index, name = target
        self.phase6_cancelled.clear()
        self.phase6_status.setText(f"{SHOP_SURVEY_LABEL}: đang chạy…")
        self.run_job(
            "phase6",
            lambda: run_phase6_shop_survey(
                self.manager,
                self.data_dir,
                index,
                name,
                cancelled=self.phase6_cancelled.is_set,
                promo_recovery_factory=promo_recovery_factory,
            ),
        )

    def run_phase6_vip_survey(self):
        target = self._phase6_target()
        if target is None or self.worker:
            return
        index, name = target
        self.phase6_cancelled.clear()
        self.phase6_status.setText(f"{VIP_SURVEY_LABEL}: đang chạy…")
        self.run_job(
            "phase6",
            lambda: run_phase6_vip_survey(
                self.manager,
                self.data_dir,
                index,
                name,
                cancelled=self.phase6_cancelled.is_set,
            ),
        )

    def cancel_phase6(self):
        if self.worker is not None and self.mode == "phase6":
            self.phase6_cancelled.set()
            self.phase6_cancel_button.setEnabled(False)
            self.phase6_status.setText("Phase 6: đang hủy; chờ tác vụ kết thúc an toàn…")

    def _queue_factory(self):
        installation = self.manager.ld.installation
        return Manager(LDPlayer(installation, Process()), self.store, self.data_dir)

    def start_selected(self):
        if not self.manager or self.worker:
            return
        self.run_states = {}
        self.progress = RunProgress()
        self.run_controller = AutomationController(self.store, self._queue_factory, self.run_progress.emit)
        concurrency = self.concurrency.value()
        all_non_protected = self.run_scope.currentIndex() == 1

        def work():
            run = self.run_controller.create(self.manager, concurrency, all_non_protected=all_non_protected)
            self.current_run_id = run.id
            return run.id, self.run_controller.execute(run)

        self.auto_start.setEnabled(False)
        self.auto_stop.setEnabled(True)
        self.auto_pause.setEnabled(True)
        self.run_scope.setEnabled(False)
        self.concurrency.setEnabled(False)
        self.run_job("run", work)

    def stop_run(self):
        if self.run_controller:
            self.run_controller.cancel()
            self.logs.appendPlainText('Đã yêu cầu dừng; đang chờ worker kết thúc an toàn.')
            self.auto_stop.setEnabled(False)
            self.auto_pause.setEnabled(False)

    def pause_run(self):
        if self.run_controller:
            paused = self.auto_pause.text() == "Tạm dừng"
            self.run_controller.pause(paused)
            self.logs.appendPlainText('Đã yêu cầu tạm dừng.' if paused else 'Đã tiếp tục lượt chạy.')
            self.auto_pause.setText("Tiếp tục" if paused else "Tạm dừng")

    def retry_run(self):
        if not self.manager or self.worker or not hasattr(self, "current_run_id"):
            return
        self.run_controller = AutomationController(self.store, self._queue_factory, self.run_progress.emit)
        concurrency = self.concurrency.value()

        def work():
            run = self.run_controller.retry_failed(self.manager, self.current_run_id, concurrency)
            self.current_run_id = run.id
            return run.id, self.run_controller.execute(run)

        self.auto_start.setEnabled(False)
        self.auto_stop.setEnabled(True)
        self.auto_pause.setEnabled(True)
        self.run_scope.setEnabled(False)
        self.concurrency.setEnabled(False)
        self.run_job("run", work)

    @Slot(int, int, object, str)
    def update_run_progress(self, run_id, index, status, detail):
        self.run_label.setText(f'Lượt chạy {run_id}')
        self.progress.begin(run_id)
        labels = {
            AccountStatus.QUEUED: "Đang chờ",
            AccountStatus.STARTING: "Đang khởi động",
            AccountStatus.RUNNING: "Đang chạy",
            AccountStatus.SUCCESS: "Thành công",
            AccountStatus.FAILED: "Lỗi",
            AccountStatus.CANCELLED: "Đã hủy",
        }
        label = labels.get(status, str(status))
        if status in (AccountStatus.RUNNING, AccountStatus.STARTING):
            self.progress.account_started(index)
        elif status in (AccountStatus.SUCCESS, AccountStatus.FAILED, AccountStatus.CANCELLED):
            self.progress.account_finished(index, label, detail)
        else:
            self.progress._account(index).status = label
        self.sync_run_states()
        self.logs.appendPlainText(f"[Run {run_id}] [#{index}] {detail}")
        self.render()
        self.update_dashboard()

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
            "Top Heroes Auto Manager\nTự động nhận quà — tối đa 2 tài khoản đồng thời\n"
            "Phát triển bởi Thang Nguyen\n\nMột giả lập = một tài khoản.\n"
            "Idle, VIP, BXH, Tiệm, Hội, Thư và Event.\n\nDữ liệu: " + str(self.data_dir),
        )

    def closeEvent(self, event: QCloseEvent):
        if self.worker is not None:
            self.statusBar().showMessage("Vui lòng chờ thao tác hiện tại kết thúc trước khi đóng.")
            event.ignore()
            return
        self.store.set("window_geometry", bytes(self.saveGeometry().toBase64()).decode("ascii"))
        logging.getLogger("top_heroes_auto").removeHandler(self.log_handler)
        event.accept()
