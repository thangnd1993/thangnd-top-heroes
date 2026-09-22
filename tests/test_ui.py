import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import top_heroes_auto.ui.window as window_module
from top_heroes_auto.app.phase6_shop_navigation_tasks import (
    SHOP_NAVIGATION_LABEL,
    SHOP_NAVIGATION_TASK,
    ShopNavigationTaskResult,
)
from top_heroes_auto.app.phase6_shop_survey_tasks import (
    SHOP_SURVEY_LABEL,
    SHOP_SURVEY_TASK,
    ShopSurveyTaskResult,
)
from top_heroes_auto.app.phase6_vip_survey_tasks import (
    VIP_SURVEY_LABEL,
    VIP_SURVEY_TASK,
    VipSurveyTaskResult,
)
from top_heroes_auto.automation.phase6_shop import ShopSurveyResult, ShopSurveyStatus
from top_heroes_auto.automation.phase6_shop_navigation import (
    ShopNavigationResult,
    ShopNavigationStatus,
)
from top_heroes_auto.ui.window import Window, Worker


def test_gui_selection_protection_filters_and_close(rig, tmp_path, monkeypatch):
    manager, _, store = rig
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(Window, "discover_ld", lambda self: None)
    window = Window(store, tmp_path)
    window.manager = manager
    window.instances = manager.refresh()
    window.show()
    app.processEvents()
    window.render()
    assert window.table.rowCount() == 2
    assert not window.table.cellWidget(0, 0).isEnabled()
    window.select_visible(True)
    assert not store.metadata(manager.namespace, 0).selected
    window.search.setText("Farm")
    assert window.table.rowCount() == 1
    window.select_visible(False)
    assert window.target.count() == 0
    assert not any(b.isEnabled() for b in window.action_buttons)
    window.close()


def test_phase6_shop_survey_button_uses_navigation_runner_and_scope(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(Window, "discover_ld", lambda self: None)
    window = Window(store, tmp_path)
    window.manager = manager
    window.instances = manager.refresh()

    process.listing = "0,Queen,0,0,0,-1,-1\n2,5-Emmmmm,0,0,0,-1,-1\n"
    manager.refresh()
    manager.protect(0, True)
    manager.select(2, True)
    window.instances = manager.list_readonly()
    window.render()

    assert window.phase6_shop_survey_button.text() == SHOP_NAVIGATION_LABEL
    assert window.phase6_shop_survey_button.isEnabled()
    calls = []

    def fake_survey(*args, **kwargs):
        calls.append((args, kwargs))
        assert callable(kwargs["cancelled"])
        assert kwargs["cancelled"]() is False
        return ShopNavigationTaskResult(
            SHOP_NAVIGATION_TASK,
            ShopNavigationStatus.SUCCESS.value,
            navigation=ShopNavigationResult(ShopNavigationStatus.SUCCESS),
        )

    def fake_run_job(mode, function):
        calls.append(mode)
        window.mode = mode
        window.job_result(function())

    monkeypatch.setattr(window_module, "run_phase6_shop_navigation", fake_survey)
    monkeypatch.setattr(window, "run_job", fake_run_job)
    window.run_phase6_shop_navigation()

    assert calls[0] == "phase6"
    assert calls[1][0][0] is manager
    assert calls[1][0][2:] == (2, "5-Emmmmm")
    assert calls[1][1]["promo_recovery_factory"] is window_module.promo_recovery_factory
    assert SHOP_NAVIGATION_LABEL in window.phase6_status.text()
    assert "navigation=SUCCESS" in window.phase6_status.text()
    window.close()
    assert store.get("window_geometry")


def test_phase6_controls_require_exact_target_and_use_worker_cancellation(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(Window, "discover_ld", lambda self: None)
    window = Window(store, tmp_path)
    window.manager = manager
    window.instances = manager.refresh()
    window.render()
    assert all(not button.isEnabled() for button in window.phase6_buttons)

    process.listing = "0,Queen,0,0,0,-1,-1\n2,5-Emmmmm,0,0,0,-1,-1\n"
    manager.refresh()
    manager.protect(0, True)
    manager.select(2, True)
    assert store.metadata(manager.namespace, 2).selected
    assert not store.metadata(manager.namespace, 2).protected
    window.instances = manager.list_readonly()
    assert [(item.index, item.name) for item in window.instances] == [(0, "Queen"), (2, "5-Emmmmm")]
    window.render()
    assert window.target.currentData() == 2
    assert all(button.isEnabled() for button in window.phase6_buttons)
    assert any(button.text() == "Rương BXH (an toàn)" for button in window.phase6_buttons)

    calls = []

    def fake_task(*args, **kwargs):
        calls.append((args, kwargs))
        assert callable(kwargs["cancelled"])
        assert kwargs["cancelled"]() is False
        return "NOT_IMPLEMENTED"

    def fake_run_job(mode, function):
        calls.append(mode)
        function()

    monkeypatch.setattr(window_module, "run_free_reward_task", fake_task)
    monkeypatch.setattr(window, "run_job", fake_run_job)
    window.run_phase6_task("free-pack")
    assert calls[0] == "phase6"
    assert calls[1][0][4] == "free-pack"
    window.run_phase6_task("ranking-chest")
    assert calls[2] == "phase6"
    assert calls[3][0][4] == "ranking-chest"

    window.worker = object()
    window.mode = "phase6"
    window.cancel_phase6()
    assert window.phase6_cancelled.is_set()
    window.phase6_status.setText("Phase 6 free-pack: NOT_IMPLEMENTED")
    window.refresh = lambda: None
    window.worker = Worker(lambda: None, window)
    window.mode = "phase6"
    window.job_finished()
    window.render()
    assert window.phase6_status.text() == "Phase 6 free-pack: NOT_IMPLEMENTED"
    window.worker = None
    window.close()


def test_partial_shop_survey_button_is_separate_and_reports_coverage(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(Window, "discover_ld", lambda self: None)
    window = Window(store, tmp_path)
    window.manager = manager
    window.instances = manager.refresh()
    process.listing = "0,Queen,0,0,0,-1,-1\n2,5-Emmmmm,0,0,0,-1,-1\n"
    manager.refresh()
    manager.protect(0, True)
    manager.select(2, True)
    window.instances = manager.list_readonly()
    window.render()

    assert window.phase6_shop_broad_survey_button.text() == SHOP_SURVEY_LABEL
    assert window.phase6_shop_broad_survey_button.isEnabled()
    calls = []

    def fake_survey(*args, **kwargs):
        calls.append((args, kwargs))
        return ShopSurveyTaskResult(
            SHOP_SURVEY_TASK,
            ShopSurveyStatus.PARTIAL.value,
            survey=ShopSurveyResult(
                status=ShopSurveyStatus.PARTIAL,
                partial_reasons=["unsupported_tabs"],
            ),
        )

    def fake_run_job(mode, function):
        window.mode = mode
        function_result = function()
        window.job_result(function_result)

    monkeypatch.setattr(window_module, "run_phase6_shop_survey", fake_survey)
    monkeypatch.setattr(window, "run_job", fake_run_job)
    window.run_phase6_shop_survey()

    assert calls[0][0][0] is manager
    assert calls[0][0][2:] == (2, "5-Emmmmm")
    assert calls[0][1]["promo_recovery_factory"] is window_module.promo_recovery_factory
    assert SHOP_SURVEY_LABEL in window.phase6_status.text()
    assert "survey=PARTIAL" in window.phase6_status.text()
    assert "coverage=partial" in window.phase6_status.text()
    assert "unsupported_tabs" in window.phase6_status.text()
    window.close()


def test_vip_survey_button_is_observation_only_and_cancelable(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(Window, "discover_ld", lambda self: None)
    window = Window(store, tmp_path)
    window.manager = manager
    window.instances = manager.refresh()
    process.listing = "0,Queen,0,0,0,-1,-1\n2,5-Emmmmm,0,0,0,-1,-1\n"
    manager.refresh()
    manager.protect(0, True)
    manager.select(2, True)
    window.instances = manager.list_readonly()
    window.render()

    assert window.phase6_vip_survey_button.text() == VIP_SURVEY_LABEL
    assert window.phase6_vip_survey_button.isEnabled()
    calls = []

    def fake_survey(*args, **kwargs):
        calls.append((args, kwargs))
        assert callable(kwargs["cancelled"])
        assert kwargs["cancelled"]() is False
        return VipSurveyTaskResult(VIP_SURVEY_TASK, "SUCCESS")

    def fake_run_job(mode, function):
        window.mode = mode
        window.job_result(function())

    monkeypatch.setattr(window_module, "run_phase6_vip_survey", fake_survey)
    monkeypatch.setattr(window, "run_job", fake_run_job)
    window.run_phase6_vip_survey()

    assert calls[0][0][0] is manager
    assert calls[0][0][2:] == (2, "5-Emmmmm")
    assert VIP_SURVEY_LABEL in window.phase6_status.text()
    assert "SUCCESS" in window.phase6_status.text()
    window.close()
