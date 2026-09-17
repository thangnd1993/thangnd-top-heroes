import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from top_heroes_auto.storage.store import Store


def data_directory() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return root / "TopHeroesAutoManager"


def main():
    from top_heroes_auto.ui.window import Window

    app = QApplication(sys.argv)
    app.setApplicationName("Top Heroes Auto Manager")
    app.setOrganizationName("Thang Nguyen")
    data = data_directory()
    (data / "logs").mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        data / "logs" / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger("top_heroes_auto").setLevel(logging.DEBUG)
    logging.getLogger("top_heroes_auto").addHandler(handler)
    window = Window(Store(data / "config.sqlite3"), data)
    window.show()
    if "--smoke-test" in sys.argv:
        # Exercise the packaged GUI event loop and exit cleanly; a crash dialog must
        # not be mistaken for a healthy process simply because it stays alive.
        def finish_smoke():
            if window.worker is not None:
                QTimer.singleShot(100, finish_smoke)
                return
            window.close()
            app.quit()

        QTimer.singleShot(1500, finish_smoke)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
