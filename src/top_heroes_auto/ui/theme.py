STYLE = """
QMainWindow, QWidget { background: #101a2b; color: #e4ecfa; font-family: 'Segoe UI'; font-size: 13px; }
QFrame#sidebar { background: #0b1322; border-right: 1px solid #23344f; }
QLabel#brand { font-size: 21px; font-weight: 700; color: #73b7ff; }
QLabel#heading { font-size: 25px; font-weight: 700; }
QLabel#muted { color: #92a5c1; }
QGroupBox { border: 1px solid #2a3d5b; border-radius: 9px; margin-top: 16px; padding: 14px 10px 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #a8cfff; }
QPushButton { background: #233a58; border: 1px solid #355171; border-radius: 6px; padding: 8px 12px; }
QPushButton:hover { background: #30527b; }
QPushButton:disabled { color: #72829a; background: #1a2638; border-color: #26374e; }
QPushButton#primary { background: #176bd1; border-color: #378df4; font-weight: 700; padding: 11px 12px; }
QPushButton#primary:hover { background: #2380ee; }
QPushButton#primary:disabled { background: #17304f; border-color: #26374e; color: #72829a; }
QPushButton#danger { background: #8a2530; border-color: #c9505c; font-weight: 700; padding: 11px 12px; }
QPushButton#danger:hover { background: #a42f3c; }
QPushButton#danger:disabled { background: #2a1f27; border-color: #3a2a33; color: #72829a; }
QFrame#card { background: #14233a; border: 1px solid #2a3d5b; border-radius: 9px; }
QLabel#cardTitle { color: #92a5c1; font-size: 11px; }
QLabel#cardValue { color: #e4ecfa; font-size: 14px; font-weight: 700; }
QLabel#warning { background: #3a2c12; border: 1px solid #8a6a1f; border-radius: 6px; color: #ffd98a; padding: 7px 10px; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit { background: #0b1424; border: 1px solid #2b4160; border-radius: 5px; padding: 6px; }
QTableWidget { background: #121e31; alternate-background-color: #17253b; border: 1px solid #293c58; gridline-color: #23344f; }
QHeaderView::section { background: #1d304a; color: #afc6e6; border: none; padding: 9px; }
QTableWidget::item { padding: 5px; }
QTableWidget::item:selected { background: #23476d; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #4a6a95; border-radius: 4px; background: #0b1424; }
QCheckBox::indicator:checked { background: #176bd1; border-color: #5aa2ff; }
QCheckBox::indicator:disabled { background: #1a2638; border-color: #2c3d57; }
QTableWidget QPushButton { padding: 3px 10px; }
QStatusBar { background: #0b1322; color: #94b1d5; }
QScrollArea { border: none; }
"""
