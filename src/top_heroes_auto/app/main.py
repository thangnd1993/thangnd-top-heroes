import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from top_heroes_auto.storage.store import Store


def data_directory() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return root / "TopHeroesAutoManager"


def main(argv: list[str] | None = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'shop-reconcile-saved':
        if len(argv) != 2 or not argv[1].isdigit():
            raise ValueError('Saved Shop reconciliation requires one explicit claim ID.')
        from top_heroes_auto.app.bxh_shop_acceptance import progress
        from top_heroes_auto.automation.fixed_reward_reconcile import reconcile_saved_fixed_reward

        result = reconcile_saved_fixed_reward(Store(data_directory()/'config.sqlite3'), int(argv[1]))
        progress(f"Shop saved claim {result['claim_id']}: {result['result']}; no input dispatched.")
        return 0
    if argv and argv[0] in {"bxh-shop-acceptance", "shop-acceptance"}:
        resume = Path(argv[2]) if len(argv) == 3 and argv[1] == '--resume-report' else None
        if not resume and argv[1:] not in (["--random-test"], ["--confirm-non-protected"]):
            raise ValueError("BXH/shop acceptance needs --random-test, --confirm-non-protected or --resume-report PATH.")
        from top_heroes_auto.app.bxh_shop_acceptance import run_acceptance
        from top_heroes_auto.app.diagnostic import _manager

        data = data_directory()
        from top_heroes_auto.vision.fixed_rewards import REWARDS, SHOP_REWARDS

        run_acceptance(_manager(data), data, random_test=argv[1] == "--random-test", resume_report=resume,
                       rewards=SHOP_REWARDS if argv[0] == 'shop-acceptance' else REWARDS)
        return 0
    if argv and argv[0] == "vip-fleet":
        if argv != ["vip-fleet", "--confirm-non-protected"]:
            raise ValueError("VIP fleet requires explicit --confirm-non-protected.")
        from top_heroes_auto.app.diagnostic import _manager
        from top_heroes_auto.app.vip_fleet import run_vip_fleet

        data = data_directory()
        run_vip_fleet(_manager(data), data)
        return 0
    if argv and argv[0] == "vip-acceptance":
        if argv != ["vip-acceptance", "--confirm-index2"]:
            raise ValueError("VIP acceptance requires explicit --confirm-index2; no other target is supported.")
        from top_heroes_auto.app.diagnostic import _manager
        from top_heroes_auto.app.vip_acceptance import run

        data = data_directory()
        run(_manager(data), data)
        return 0
    if argv and argv[0] == "diagnostic":
        from top_heroes_auto.app.diagnostic import main as diagnostic_main

        return diagnostic_main(argv[1:], data_directory())
    if argv and argv[0] == "vision":
        from top_heroes_auto.app.vision_cli import main as vision_main

        return vision_main(argv[1:], data_directory())
    if argv and argv[0] == "recovery":
        from top_heroes_auto.app.recovery_cli import main as recovery_main

        return recovery_main(argv[1:], data_directory())
    if argv and argv[0] == "task":
        from top_heroes_auto.app.task_cli import main as task_main

        return task_main(argv[1:], data_directory())

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from top_heroes_auto.ui.window import Window

    app = QApplication([sys.argv[0], *argv])
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
    if "--smoke-test" in argv:
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
