import json
import os
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import top_heroes_auto.app.phase6_shop_survey_tasks as survey_tasks
from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.phase6_shop_survey_tasks import (
    PHASE6_TARGET,
    SHOP_SURVEY_TASK,
    run_phase6_shop_survey,
)
from top_heroes_auto.automation.free_rewards import RewardScreen
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.phase6_promo_recovery import PromoRecoveryResult, PromoRecoveryStatus
from top_heroes_auto.automation.phase6_shop import (
    ManagerShopSurveyPort,
    Route,
    ShopFrameObservation,
    ShopSurveyEngine,
    ShopSurveyLimits,
    ShopSurveyResult,
    ShopSurveyStatus,
)
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import (
    AnchorEvidence,
    BoundingBox,
    CapturedScreen,
    ScreenDetection,
    ScreenState,
)

RUN10_POPUP = Path(
    os.environ.get(
        "THA_PHASE6_RUN10_POPUP",
        r"C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\tasks\shop-survey\5-Emmmmm\20260921-222627-200207Z\20260921-222737-909688Z-phase6-shop-survey.png",
    )
)
RUN11_POPUP = Path(
    os.environ.get(
        "THA_PHASE6_RUN11_POPUP",
        r"C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\tasks\shop-survey\5-Emmmmm\20260921-233200-702519Z\20260921-233318-733059Z-phase6-shop-survey.png",
    )
)


def _target2(manager, process):
    process.listing = "0,Queen,1,2,0,-1,-1\n2,5-Emmmmm,0,0,0,-1,-1\n"
    manager.refresh()
    manager.protect(0, True)
    manager.select(2, True)


def _recovery(manager, data, *args, **kwargs):
    path = data / "recovery.json"
    path.write_text("{}", encoding="utf-8")
    return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, False


def _survey(*args):
    return ShopSurveyResult(
        status=ShopSurveyStatus.PARTIAL,
        partial_reasons=["coverage_unknown_or_dynamic", "unsupported_tabs"],
    )


def _inventory(*rows):
    return [
        SimpleNamespace(index=index, name=name, running=running, android_started=android_started)
        for index, name, running, android_started in rows
    ]


def _survey_with_six_actions(*args):
    return ShopSurveyResult(
        status=ShopSurveyStatus.PARTIAL,
        visited=[{"page": "game-home"}, {"page": "daily-offer"}, {"page": "daily-pack"}],
        actions=[
            "tap:home-shop-entry",
            "tap:daily-info",
            "tap:popup-close",
            "tap:daily-exit",
            "tap:daily-pack",
            "tap:pack-return",
        ],
        partial_reasons=["unsupported_tabs"],
        promo_recovery=PromoRecoveryResult(
            PromoRecoveryStatus.NOT_PRESENT,
            trigger="initial_home",
            expected_page="game-home",
        ),
    )


def _run_with_inventory(manager, data, before, after, monkeypatch, *, survey=_survey):
    states = iter((before, after))
    monkeypatch.setattr(manager, "list_readonly", lambda: next(states))
    return run_phase6_shop_survey(
        manager,
        data,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=survey,
    )


def test_isolation_report_retains_full_after_and_unrelated_indices(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    _target2(manager, process)
    before = _inventory(
        (0, "Queen", False, False),
        (2, "5-Emmmmm", False, False),
        (4, "4-Other", True, True),
        (9, "9-Other", False, False),
    )
    after = _inventory(
        (0, "Queen", False, False),
        (2, "5-Emmmmm", False, False),
        (4, "4-Other", False, False),
        (9, "9-Other", True, True),
    )

    result = _run_with_inventory(
        manager,
        tmp_path,
        before,
        after,
        monkeypatch,
        survey=_survey_with_six_actions,
    )

    assert result.status == "SAFETY_BLOCKED"
    assert result.survey is not None and len(result.survey.actions) == 6
    assert result.promo_recovery is not None
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["inventory_status"] == "available"
    assert set(report["after_instances"]) == {"0", "2", "4", "9"}
    assert report["observed_changed_indices"] == [4, 9]
    assert report["unrelated_changed_indices"] == [4, 9]
    assert report["isolation_changed_indices"] is None
    assert len(report["survey"]["actions"]) == 6
    assert report["promo_recovery"]["trigger"] == "initial_home"
    assert report["claims"] == []
    assert report["journal_rows"] == 0


def test_final_inventory_read_failure_is_unavailable_not_empty(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    _target2(manager, process)
    before = _inventory((0, "Queen", False, False), (2, "5-Emmmmm", False, False))
    states = iter((before,))

    def read_inventory():
        try:
            return next(states)
        except StopIteration as exc:
            raise SafetyError("list2 unavailable") from exc

    monkeypatch.setattr(manager, "list_readonly", read_inventory)
    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=_survey_with_six_actions,
    )

    assert result.status == "SAFETY_BLOCKED"
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["after_instances"] is None
    assert report["inventory_status"] == "unavailable"
    assert report["observed_changed_indices"] is None
    assert report["unrelated_changed_indices"] is None
    assert report["isolation_changed_indices"] is None
    assert "list2 unavailable" in report["error"]


@pytest.mark.parametrize(
    ("after", "expected"),
    (
        (
            _inventory((0, "Queen", False, False), (2, "5-Emmmmm", False, False)),
            [],
        ),
        (
            _inventory((0, "Queen", False, False), (2, "5-Emmmmm", True, True)),
            [2],
        ),
    ),
)
def test_isolation_report_accepts_unchanged_and_target_only(rig, tmp_path, monkeypatch, after, expected):
    manager, process, store = rig
    _target2(manager, process)
    before = _inventory((0, "Queen", False, False), (2, "5-Emmmmm", False, False))
    result = _run_with_inventory(manager, tmp_path, before, after, monkeypatch)

    assert result.status == ShopSurveyStatus.PARTIAL.value
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["inventory_status"] == "available"
    assert report["observed_changed_indices"] == expected
    assert report["unrelated_changed_indices"] == []
    assert report["isolation_changed_indices"] == expected


@pytest.mark.parametrize(
    ("before", "after"),
    (
        (
            _inventory((0, "Queen", False, False), (2, "5-Emmmmm", False, False)),
            _inventory((0, "Queen", False, False), (2, "5-Emmmmm", False, False), (9, "9-Other", False, False)),
        ),
        (
            _inventory((0, "Queen", False, False), (2, "5-Emmmmm", False, False), (9, "9-Other", False, False)),
            _inventory((0, "Queen", False, False), (2, "5-Emmmmm", False, False)),
        ),
    ),
)
def test_isolation_report_lists_added_and_removed_indices(rig, tmp_path, monkeypatch, before, after):
    manager, process, store = rig
    _target2(manager, process)
    result = _run_with_inventory(manager, tmp_path, before, after, monkeypatch)

    assert result.status == "SAFETY_BLOCKED"
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["observed_changed_indices"] == [9]
    assert report["unrelated_changed_indices"] == [9]
    assert report["after_instances"] is not None


def test_isolation_and_persistence_failure_keep_evidence_without_cleanup_retry(
    rig, tmp_path, monkeypatch
):
    manager, process, store = rig
    _target2(manager, process)
    before = _inventory(
        (0, "Queen", False, False),
        (2, "5-Emmmmm", False, False),
        (4, "4-Other", True, True),
    )
    after = _inventory(
        (0, "Queen", False, False),
        (2, "5-Emmmmm", False, False),
        (4, "4-Other", False, False),
    )
    states = iter((before, after))
    monkeypatch.setattr(manager, "list_readonly", lambda: next(states))
    actions = []

    def failed_cleanup(index, action, **kwargs):
        actions.append((index, action))
        raise OSError("quit uncertain")

    manager.execute = failed_cleanup
    monkeypatch.setattr(
        store,
        "finish_task_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("db down")),
    )

    def owned_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-owned-run14.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, True

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=owned_recovery,
        survey_factory=_survey_with_six_actions,
    )

    assert result.status == "CLEANUP_FAILED"
    assert result.cleanup_attempted is True
    assert result.cleanup_succeeded is False
    assert result.survey is not None and len(result.survey.actions) == 6
    assert result.promo_recovery is not None
    assert actions == [(2, "quit")]
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["result"] == "CLEANUP_FAILED"
    assert report["observed_changed_indices"] == [4]
    assert report["unrelated_changed_indices"] == [4]
    assert len(report["survey"]["actions"]) == 6
    assert report["promo_recovery"]["trigger"] == "initial_home"
    assert report["claims"] == []
    assert report["journal_rows"] == 0


def test_survey_runner_persists_partial_without_claim_or_journal(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=_survey,
    )

    assert result.status == "PARTIAL"
    assert result.survey is not None
    assert result.claims == ()
    assert result.journal_rows == 0
    assert result.report_path and result.report_path.is_file()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["claims"] == []
    assert report["journal_rows"] == 0
    assert report["survey"]["partial_reasons"] == [
        "coverage_unknown_or_dynamic",
        "unsupported_tabs",
    ]
    assert store.latest_task_run(manager.namespace, SHOP_SURVEY_TASK, 2)[2] == "PARTIAL"


def test_survey_runner_rejects_wrong_target_before_persistence(rig, tmp_path):
    manager, process, store = rig
    with pytest.raises(SafetyError, match="#2 / 5-Emmmmm"):
        run_phase6_shop_survey(manager, tmp_path, 7, "Farm-007", survey_factory=_survey)
    assert store.latest_task_run(manager.namespace, SHOP_SURVEY_TASK, 7) is None


def test_survey_runner_requires_home_and_does_not_build_survey_on_recovery_failure(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    calls = []

    def failed_recovery(manager, data, *args, **kwargs):
        calls.append("recovery")
        path = data / "recovery-failed.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.UNKNOWN_SCREEN), path, False

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=failed_recovery,
        survey_factory=lambda *args: calls.append("survey"),
    )
    assert result.status == "UNKNOWN_SCREEN"
    assert calls == ["recovery"]
    assert store.latest_task_run(manager.namespace, SHOP_SURVEY_TASK, 2)[2] == "UNKNOWN_SCREEN"


def test_survey_runner_cleans_only_owned_instance(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    actions = []
    manager.execute = lambda index, action, **kwargs: actions.append((index, action))

    def owned_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-owned.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, True

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=owned_recovery,
        survey_factory=_survey,
    )
    assert result.status == "PARTIAL"
    assert result.started_by_run is True
    assert result.cleanup_attempted is True
    assert result.cleanup_succeeded is True
    assert actions == [(2, "quit")]


def test_stopped_target_timeout_uses_one_same_boot_promo_recovery(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    actions = []
    manager.execute = lambda index, action, **kwargs: actions.append((index, action, kwargs))
    promo_calls = []

    def timeout_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-timeout.json"
        path.write_text("{}", encoding="utf-8")
        return (
            RecoveryResult(
                RecoveryStatus.LOADING_TIMEOUT,
                adb_target="emulator-5558",
                boot_id="boot-2",
            ),
            path,
            True,
        )

    def promo(*args, **kwargs):
        promo_calls.append(kwargs)
        assert kwargs["expected_transport"] == ("emulator-5558", "boot-2")
        return PromoRecoveryResult(PromoRecoveryStatus.SUCCESS, attempted=True, actions=["keyevent:4"])

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=timeout_recovery,
        promo_recovery_factory=promo,
        survey_factory=_survey,
    )
    assert result.status == "PARTIAL"
    assert len(promo_calls) == 1
    assert result.promo_recovery is not None
    assert [(index, action) for index, action, _ in actions] == [(2, "quit")]


def test_uncertain_promo_back_is_terminal_and_owned_cleanup_is_not_retried(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    actions = []
    manager.execute = lambda index, action, **kwargs: actions.append((index, action))

    def timeout_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-uncertain.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.LOADING_TIMEOUT, adb_target="emulator-5558", boot_id="boot-2"), path, True

    promo_calls = []

    def promo(*args, **kwargs):
        promo_calls.append(kwargs)
        return PromoRecoveryResult(
            PromoRecoveryStatus.ACTION_RESULT_UNCERTAIN,
            attempted=True,
            actions=["keyevent:4"],
            error="transport uncertain",
        )

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=timeout_recovery,
        promo_recovery_factory=promo,
        survey_factory=lambda *args: pytest.fail("uncertain promo must not survey"),
    )
    assert result.status == PromoRecoveryStatus.ACTION_RESULT_UNCERTAIN.value
    assert len(promo_calls) == 1
    assert actions == [(2, "quit")]


def test_timeout_without_boot_identity_does_not_call_promo_fallback(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    actions = []
    manager.execute = lambda index, action, **kwargs: actions.append((index, action))
    promo_calls = []

    def timeout_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-no-boot.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.LOADING_TIMEOUT, adb_target="emulator-5558"), path, True

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=timeout_recovery,
        promo_recovery_factory=lambda *args, **kwargs: promo_calls.append(kwargs),
        survey_factory=lambda *args: pytest.fail("missing boot must not survey"),
    )
    assert result.status == RecoveryStatus.LOADING_TIMEOUT.value
    assert promo_calls == []
    assert actions == [(2, "quit")]


def test_report_persistence_and_owned_cleanup_failure_are_returned(tmp_path, rig, monkeypatch):
    manager, process, store = rig
    _target2(manager, process)
    actions = []

    def fail_quit(index, action, **kwargs):
        actions.append((index, action))
        raise OSError("quit uncertain")

    manager.execute = fail_quit
    monkeypatch.setattr(store, "finish_task_run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("db down")))

    def owned_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-persist-failure.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, True

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=owned_recovery,
        survey_factory=_survey,
    )
    assert result.status == "CLEANUP_FAILED"
    assert "db down" in result.error
    assert "quit uncertain" in result.error


def test_production_survey_factory_receives_successful_recovery_identity(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    _target2(manager, process)
    received = {}

    def factory(manager, snapshot, index, name, folder, cancelled, **kwargs):
        received.update(kwargs)
        return _survey()

    def recovered(manager, data, *args, **kwargs):
        path = data / "recovery-identity.json"
        path.write_text("{}", encoding="utf-8")
        return (
            RecoveryResult(
                RecoveryStatus.ALREADY_HOME,
                adb_target="emulator-5558",
                boot_id="run11-boot",
            ),
            path,
            False,
        )

    monkeypatch.setattr(survey_tasks, "shop_survey_factory", factory)
    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=recovered,
        promo_recovery_factory=lambda *args, **kwargs: PromoRecoveryResult(
            PromoRecoveryStatus.NOT_PRESENT
        ),
    )

    assert result.status == ShopSurveyStatus.PARTIAL.value
    assert received["initial_promo_identity"] == ("emulator-5558", "run11-boot")
    assert received["initial_promo_anchor"] is not None
    assert received["pending_promo_anchor"] is not None
    assert received["promo_budget_available"] is True


def test_production_survey_factory_missing_recovery_identity_fails_closed(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    _target2(manager, process)
    calls = []

    def factory(*args, **kwargs):
        calls.append(kwargs)
        return _survey()

    monkeypatch.setattr(survey_tasks, "shop_survey_factory", factory)
    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        promo_recovery_factory=lambda *args, **kwargs: PromoRecoveryResult(
            PromoRecoveryStatus.NOT_PRESENT
        ),
    )

    assert result.status == PromoRecoveryStatus.IDENTITY_MISMATCH.value
    assert calls == []
    assert result.promo_recovery is not None
    assert result.promo_recovery.trigger == "initial_home"
    assert result.promo_recovery.attempted is False


def _run10_survey_factory(
    manager,
    snapshot,
    index,
    name,
    folder,
    cancelled,
    *,
    budget=True,
    boot_change=False,
    back_error=None,
    after_page="daily-offer",
    persistent_popup=False,
    duplicate_popup=False,
    cancel_state=None,
    popup_boot_change=False,
):
    promo_anchor = load_anchors(Path(__file__).resolve().parents[1] / "assets" / "tasks" / "phase6" / "promo")[0]
    target = Target(2, "5-Emmmmm", "emulator-5558", "boot-2")
    page_state = {"game-home": ScreenState.GAME_HOME, "daily-offer": ScreenState.FREE_REWARD_PAGE}

    class Registry:
        def __init__(self):
            self.calls = 0

        def observe(self, captured):
            self.calls += 1
            if persistent_popup and self.calls >= 2:
                raise SafetyError("Current frame has no uniquely verified shop page.")
            page = "game-home" if self.calls == 1 else after_page
            state = page_state[page]
            evidence = AnchorEvidence(
                f"{page}-page",
                state,
                0.99,
                0.9,
                True,
                BoundingBox(10, 10, 20, 20),
                BoundingBox(10, 10, 20, 20),
            )
            entry = AnchorEvidence(
                "home-shop-entry",
                state,
                0.99,
                0.9,
                True,
                BoundingBox(30, 30, 20, 20),
                BoundingBox(30, 30, 20, 20),
            )
            routes = (
                (Route("home-shop-entry", "home-shop-entry", "daily-offer", "submenu"),)
                if page == "game-home"
                else ()
            )
            detection = ScreenDetection(
                state,
                0.99,
                (evidence, entry) if page == "game-home" else (evidence,),
                captured.timestamp,
                captured.source_image,
                0.0,
            )
            screen = RewardScreen(
                detection=detection,
                index=captured.index,
                name=captured.name,
                adb_target=captured.serial,
                boot_id=captured.boot_id,
                capture_id=str(captured.source_image),
                page=page,
                fingerprint=page,
                routes=routes,
                coverage_known=False,
            )
            return ShopFrameObservation(
                captured,
                screen,
                {"page": evidence, "home-shop-entry": entry} if page == "game-home" else {"page": evidence},
            )

    template = cv2.imread(str(promo_anchor.template), cv2.IMREAD_COLOR)
    assert template is not None
    promo_image = np.full((720, 1280, 3), 70, dtype=np.uint8)
    height, width = template.shape[:2]
    promo_image[350 : 350 + height, 1090 : 1090 + width] = template
    if duplicate_popup:
        promo_image[280 : 280 + height, 960 : 960 + width] = template
        promo_image[260 : 260 + height, 1160 : 1160 + width] = template
    plain_image = np.full((720, 1280, 3), 70, dtype=np.uint8)
    plain_image[0:200, 0:200] = 150
    encoded = []
    frames = (plain_image, promo_image, *((promo_image,) * 3 if persistent_popup else (plain_image,)))
    for image in frames:
        ok, payload = cv2.imencode(".png", image)
        assert ok
        encoded.append(payload.tobytes())

    class FakeManager:
        def __init__(self):
            self.frames = iter(encoded)
            self.actions = []
            self.capture_count = 0

        def capture_verified(self, _index, _snapshot):
            self.capture_count += 1
            if cancel_state is not None and self.capture_count >= 2:
                cancel_state["promo_seen"] = True
            current = target
            if popup_boot_change and self.capture_count == 2:
                current = Target(2, "5-Emmmmm", "emulator-5558", "boot-new")
            elif boot_change and self.capture_count >= 3:
                current = Target(2, "5-Emmmmm", "emulator-5558", "boot-new")
            return current, next(self.frames)

        def execute(self, index, action, **kwargs):
            self.actions.append((index, action, kwargs))
            if back_error and action == "keyevent":
                raise back_error

    fake = FakeManager()
    port = ManagerShopSurveyPort(
        fake,
        snapshot,
        index,
        name,
        Registry(),
        folder,
        pending_promo_anchor=promo_anchor,
        promo_budget_available=budget,
        promo_observations=3,
        promo_wait_seconds=0,
    )
    survey = ShopSurveyEngine(ShopSurveyLimits(max_steps=4, max_depth=2, max_seconds=10)).run(
        port,
        index,
        name,
        cancelled,
    )
    return survey, fake


def _run11_initial_case(
    tmp_path,
    *,
    first_popup=True,
    after_popup=False,
    after_page="game-home",
    identity=("emulator-5558", "boot-2"),
    actual_boot="boot-2",
    budget=True,
    duplicate_popup=False,
    back_error=None,
    cancelled=lambda: False,
    wrong_target=False,
    after_boot_change=False,
    run_engine=False,
    route_after_home=False,
):
    promo_anchor = load_anchors(Path(__file__).resolve().parents[1] / "assets" / "tasks" / "phase6" / "promo")[0]
    target = Target(
        2,
        "revoked" if wrong_target else "5-Emmmmm",
        "emulator-5558",
        actual_boot,
    )
    template = cv2.imread(str(promo_anchor.template), cv2.IMREAD_COLOR)
    assert template is not None

    def image(popup, duplicate=False):
        frame = np.full((720, 1280, 3), 70, dtype=np.uint8)
        frame[0:200, 0:200] = 150
        if popup:
            height, width = template.shape[:2]
            frame[350 : 350 + height, 1090 : 1090 + width] = template
            if duplicate:
                frame[280 : 280 + height, 960 : 960 + width] = template
                frame[260 : 260 + height, 1160 : 1160 + width] = template
        return frame

    frames = [image(first_popup, duplicate_popup), image(after_popup)]
    if run_engine:
        frames.append(image(False))
    encoded = []
    for frame in frames:
        ok, payload = cv2.imencode(".png", frame)
        assert ok
        encoded.append(payload.tobytes())

    class Registry:
        def __init__(self):
            self.calls = 0

        def observe(self, captured):
            self.calls += 1
            if first_popup:
                page = after_page if self.calls == 1 or not run_engine else "daily-offer"
            else:
                page = "game-home" if self.calls == 1 else ("daily-offer" if run_engine else "game-home")
            state = ScreenState.GAME_HOME if page == "game-home" else ScreenState.FREE_REWARD_PAGE
            evidence = AnchorEvidence(
                f"{page}-page",
                state,
                0.99,
                0.9,
                True,
                BoundingBox(10, 10, 20, 20),
                BoundingBox(10, 10, 20, 20),
            )
            entry = AnchorEvidence(
                "home-shop-entry",
                state,
                0.99,
                0.9,
                True,
                BoundingBox(30, 30, 20, 20),
                BoundingBox(30, 30, 20, 20),
            )
            routes = (
                (Route("home-shop-entry", "home-shop-entry", "daily-offer", "submenu"),)
                if route_after_home and page == "game-home"
                else ()
            )
            detection = ScreenDetection(
                state,
                0.99,
                (evidence, entry) if routes else (evidence,),
                captured.timestamp,
                captured.source_image,
                0.0,
            )
            screen = RewardScreen(
                detection=detection,
                index=captured.index,
                name=captured.name,
                adb_target=captured.serial,
                boot_id=captured.boot_id,
                capture_id=str(captured.source_image or captured.timestamp),
                page=page,
                fingerprint=page,
                routes=routes,
                coverage_known=False,
            )
            return ShopFrameObservation(
                captured,
                screen,
                {"page": evidence, "home-shop-entry": entry} if routes else {"page": evidence},
            )

    class FakeManager:
        def __init__(self):
            self.frames = iter(encoded)
            self.actions = []
            self.capture_count = 0

        def capture_verified(self, _index, _snapshot):
            self.capture_count += 1
            current = target
            if wrong_target:
                current = Target(2, "revoked", "emulator-5558", actual_boot)
            elif self.capture_count == 2 and after_boot_change:
                current = Target(2, "5-Emmmmm", "emulator-5558", "boot-new")
            return current, next(self.frames)

        def execute(self, index, action, **kwargs):
            self.actions.append((index, action, kwargs))
            if back_error is not None and action == "keyevent":
                raise back_error

    manager = FakeManager()
    snapshot = RunSnapshot("ns", ((2, "5-Emmmmm"),), True)
    port = ManagerShopSurveyPort(
        manager,
        snapshot,
        2,
        "5-Emmmmm",
        Registry(),
        tmp_path,
        pending_promo_anchor=promo_anchor,
        initial_promo_anchor=promo_anchor,
        initial_promo_identity=identity,
        promo_budget_available=budget,
        promo_observations=1,
        promo_wait_seconds=0,
    )
    port.arm_initial_promo(cancelled)
    observation = None
    error = None
    try:
        if run_engine:
            observation = ShopSurveyEngine(
                ShopSurveyLimits(max_steps=3, max_depth=2, max_seconds=10)
            ).run(port, 2, "5-Emmmmm", cancelled)
        else:
            observation = port.observe()
    except Exception as exc:  # noqa: BLE001 - assertions inspect the fail-closed result
        error = exc
    return observation, port.take_promo_recovery(), manager, error


def test_initial_promo_closes_once_and_requires_same_boot_home(tmp_path):
    observation, promo, manager, error = _run11_initial_case(tmp_path)

    assert error is None
    assert observation is not None and observation.screen.page == "game-home"
    assert promo is not None
    assert promo.status == PromoRecoveryStatus.SUCCESS
    assert promo.trigger == "initial_home"
    assert promo.expected_page == "game-home"
    assert promo.attempted is True
    assert len([action for _, action, _ in manager.actions if action == "keyevent"]) == 1
    assert promo.before["boot_id"] == "boot-2"
    assert promo.after["boot_id"] == "boot-2"


def test_initial_engine_normal_home_authorizes_one_shop_tap(tmp_path):
    survey, promo, manager, error = _run11_initial_case(
        tmp_path,
        first_popup=False,
        run_engine=True,
        route_after_home=True,
    )

    assert error is None
    assert survey.status == ShopSurveyStatus.PARTIAL
    assert survey.promo_recovery is not None
    assert survey.promo_recovery.status == PromoRecoveryStatus.NOT_PRESENT
    assert [action for _, action, _ in manager.actions] == ["tap"]


def test_initial_engine_fullscreen_promo_authorizes_one_shop_tap_after_home(tmp_path):
    survey, promo, manager, error = _run11_initial_case(
        tmp_path,
        run_engine=True,
        route_after_home=True,
    )

    assert error is None
    assert survey.status == ShopSurveyStatus.PARTIAL
    assert survey.promo_recovery is not None
    assert survey.promo_recovery.status == PromoRecoveryStatus.SUCCESS
    assert [action for _, action, _ in manager.actions] == ["keyevent", "tap"]


def test_initial_engine_failure_or_cancellation_never_taps_shop(tmp_path):
    def cancelled():
        return True

    survey, promo, manager, error = _run11_initial_case(
        tmp_path,
        run_engine=True,
        route_after_home=True,
        cancelled=cancelled,
    )
    assert error is None
    assert survey.status == ShopSurveyStatus.CANCELLED
    assert survey.promo_recovery is None
    assert manager.actions == []

    survey, promo, manager, error = _run11_initial_case(
        tmp_path,
        run_engine=True,
        route_after_home=True,
        back_error=OSError("Back uncertain"),
    )
    assert error is None
    assert survey.status == ShopSurveyStatus.ACTION_RESULT_UNCERTAIN
    assert survey.promo_recovery is not None
    assert survey.promo_recovery.status == PromoRecoveryStatus.ACTION_RESULT_UNCERTAIN
    assert [action for _, action, _ in manager.actions] == ["keyevent"]


def test_initial_promo_missing_or_mismatched_recovery_identity_sends_no_back(tmp_path):
    for identity in (None, ("emulator-5558", "boot-old")):
        observation, promo, manager, error = _run11_initial_case(tmp_path, identity=identity)

        assert observation is None
        assert isinstance(error, SafetyError)
        assert promo is not None
        assert promo.status == PromoRecoveryStatus.IDENTITY_MISMATCH
        assert promo.attempted is False
        assert manager.actions == []


def test_initial_promo_budget_duplicate_and_revoked_target_fail_closed(tmp_path):
    cases = (
        {"budget": False},
        {"duplicate_popup": True},
        {"wrong_target": True},
    )
    for options in cases:
        observation, promo, manager, error = _run11_initial_case(tmp_path, **options)

        assert observation is None
        assert error is not None
        assert manager.actions == []
        if options.get("wrong_target"):
            assert promo is None
        else:
            assert promo is not None
            assert promo.status == PromoRecoveryStatus.BLOCKED


def test_initial_promo_cancellation_uncertain_back_and_boot_change_never_retry(tmp_path):
    def cancelled():
        return True
    _, promo, manager, error = _run11_initial_case(tmp_path, cancelled=cancelled)
    assert isinstance(error, SafetyError)
    assert promo.status == PromoRecoveryStatus.CANCELLED
    assert manager.actions == []

    _, promo, manager, error = _run11_initial_case(tmp_path, back_error=OSError("Back uncertain"))
    assert isinstance(error, OSError)
    assert promo.status == PromoRecoveryStatus.ACTION_RESULT_UNCERTAIN
    assert len(manager.actions) == 1
    assert manager.actions[0][1] == "keyevent"

    _, promo, manager, error = _run11_initial_case(
        tmp_path,
        after_boot_change=True,
    )
    assert isinstance(error, SafetyError)
    assert promo.status == PromoRecoveryStatus.IDENTITY_MISMATCH
    assert len(manager.actions) == 1


def test_initial_promo_rejects_persistent_or_unexpected_destination_without_retry(tmp_path):
    for options, expected in (
        ({"after_popup": True}, PromoRecoveryStatus.TIMEOUT),
        ({"after_page": "daily-offer"}, PromoRecoveryStatus.BLOCKED),
    ):
        _, promo, manager, error = _run11_initial_case(tmp_path, **options)

        assert isinstance(error, SafetyError)
        assert promo.status == expected
        assert len(manager.actions) == 1
        assert manager.actions[0][1] == "keyevent"
        assert promo.after is not None
        assert len(promo.captures) == 2


def test_initial_promo_no_popup_is_consumed_and_not_reactivated(tmp_path):
    observation, promo, manager, error = _run11_initial_case(tmp_path, first_popup=False)

    assert error is None
    assert observation is not None and observation.screen.page == "game-home"
    assert promo is not None and promo.status == PromoRecoveryStatus.NOT_PRESENT
    assert manager.actions == []


def test_task_path_closes_late_promo_once_and_requires_daily_destination(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    holder = {}

    def survey_factory(manager, snapshot, index, name, folder, cancelled):
        survey, fake = _run10_survey_factory(manager, snapshot, index, name, folder, cancelled)
        holder["fake"] = fake
        return survey

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=survey_factory,
    )

    assert result.status == ShopSurveyStatus.PARTIAL.value, result.error
    assert result.survey.promo_recovery.status == PromoRecoveryStatus.DESTINATION_SUCCESS
    assert result.survey.promo_recovery.attempted
    assert result.survey.promo_recovery.captures
    assert [action for _, action, _ in holder["fake"].actions] == ["tap", "keyevent"]
    assert result.report_path and '"promo_recovery"' in result.report_path.read_text(encoding="utf-8")
    assert result.claims == ()
    assert result.journal_rows == 0


def test_pending_promo_budget_consumed_means_no_back_retry(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    holder = {}

    def survey_factory(manager, snapshot, index, name, folder, cancelled):
        survey, fake = _run10_survey_factory(
            manager, snapshot, index, name, folder, cancelled, budget=False
        )
        holder["fake"] = fake
        return survey

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=survey_factory,
    )
    assert result.status == ShopSurveyStatus.SAFETY_BLOCKED.value
    assert [action for _, action, _ in holder["fake"].actions] == ["tap"]


def test_pending_promo_uncertain_back_is_terminal_and_persisted(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    holder = {}

    def survey_factory(manager, snapshot, index, name, folder, cancelled):
        survey, fake = _run10_survey_factory(
            manager,
            snapshot,
            index,
            name,
            folder,
            cancelled,
            back_error=OSError("Back uncertain"),
        )
        holder["fake"] = fake
        return survey

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=survey_factory,
    )
    assert result.status == ShopSurveyStatus.ACTION_RESULT_UNCERTAIN.value
    assert result.survey.promo_recovery.attempted
    assert len([action for _, action, _ in holder["fake"].actions if action == "keyevent"]) == 1


def test_pending_promo_boot_change_after_back_fails_identity_without_retry(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    holder = {}

    def survey_factory(manager, snapshot, index, name, folder, cancelled):
        survey, fake = _run10_survey_factory(
            manager, snapshot, index, name, folder, cancelled, boot_change=True
        )
        holder["fake"] = fake
        return survey

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=survey_factory,
    )
    assert result.status == ShopSurveyStatus.IDENTITY_MISMATCH.value
    assert [action for _, action, _ in holder["fake"].actions] == ["tap", "keyevent"]


def test_pending_promo_boot_change_on_popup_sends_no_back(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    holder = {}

    def survey_factory(manager, snapshot, index, name, folder, cancelled):
        survey, fake = _run10_survey_factory(
            manager,
            snapshot,
            index,
            name,
            folder,
            cancelled,
            popup_boot_change=True,
        )
        holder["fake"] = fake
        return survey

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=survey_factory,
    )
    assert result.status == ShopSurveyStatus.IDENTITY_MISMATCH.value
    assert [action for _, action, _ in holder["fake"].actions] == ["tap"]


def test_pending_promo_back_to_home_is_not_accepted_as_daily(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    holder = {}

    def survey_factory(manager, snapshot, index, name, folder, cancelled):
        survey, fake = _run10_survey_factory(
            manager, snapshot, index, name, folder, cancelled, after_page="game-home"
        )
        holder["fake"] = fake
        return survey

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=survey_factory,
    )
    assert result.status == ShopSurveyStatus.SAFETY_BLOCKED.value
    assert result.survey.promo_recovery.status == PromoRecoveryStatus.DESTINATION_UNVERIFIED
    assert [action for _, action, _ in holder["fake"].actions] == ["tap", "keyevent"]


def test_pending_promo_persistent_popup_never_retries_back(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    holder = {}

    def survey_factory(manager, snapshot, index, name, folder, cancelled):
        survey, fake = _run10_survey_factory(
            manager, snapshot, index, name, folder, cancelled, persistent_popup=True
        )
        holder["fake"] = fake
        return survey

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=survey_factory,
    )
    assert result.status == ShopSurveyStatus.TIMEOUT.value
    assert result.survey.promo_recovery.status == PromoRecoveryStatus.TIMEOUT
    assert [action for _, action, _ in holder["fake"].actions] == ["tap", "keyevent"]
    assert len(result.survey.promo_recovery.captures) == 4


def test_pending_promo_duplicate_title_fails_before_back(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    holder = {}

    def survey_factory(manager, snapshot, index, name, folder, cancelled):
        survey, fake = _run10_survey_factory(
            manager, snapshot, index, name, folder, cancelled, duplicate_popup=True
        )
        holder["fake"] = fake
        return survey

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=survey_factory,
    )
    assert result.status == ShopSurveyStatus.SAFETY_BLOCKED.value
    assert result.survey.promo_recovery.status == PromoRecoveryStatus.BLOCKED
    assert [action for _, action, _ in holder["fake"].actions] == ["tap"]


def test_pending_promo_cancelled_before_back_sends_no_keyevent(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    holder = {}
    cancel_state = {"promo_seen": False}

    def cancelled():
        return cancel_state["promo_seen"]

    def survey_factory(manager, snapshot, index, name, folder, cancelled):
        survey, fake = _run10_survey_factory(
            manager,
            snapshot,
            index,
            name,
            folder,
            cancelled,
            cancel_state=cancel_state,
        )
        holder["fake"] = fake
        return survey

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=survey_factory,
        cancelled=cancelled,
    )
    assert result.status == ShopSurveyStatus.CANCELLED.value
    assert result.survey and result.survey.promo_recovery
    assert result.survey.promo_recovery.status == PromoRecoveryStatus.CANCELLED
    assert [action for _, action, _ in holder["fake"].actions] == ["tap"]


@pytest.mark.skipif(not RUN10_POPUP.is_file(), reason="saved run10 popup is not available")
def test_saved_run10_popup_has_unique_known_title_match():
    image = cv2.imread(str(RUN10_POPUP), cv2.IMREAD_COLOR)
    assert image is not None
    target = Target(2, "5-Emmmmm", "emulator-5558", "538776d2-082b-441c-a4f7-4b603a65fad3")
    captured = CapturedScreen(
        target.index,
        target.name,
        target.serial,
        target.boot_id,
        image,
        image,
        (1280, 720),
        (1280, 720),
        (1.0, 1.0),
        source_image=RUN10_POPUP,
    )
    anchor = load_anchors(Path(__file__).resolve().parents[1] / "assets" / "tasks" / "phase6" / "promo")[0]
    evidence = unique_current_anchor(captured, anchor)
    assert evidence.matched
    assert evidence.score >= 0.99


@pytest.mark.skipif(not RUN11_POPUP.is_file(), reason="saved run11 popup is not available")
def test_saved_run11_popup_has_unique_known_title_match():
    image = cv2.imread(str(RUN11_POPUP), cv2.IMREAD_COLOR)
    assert image is not None
    target = Target(2, "5-Emmmmm", "emulator-5558", "18939681-40ca-4b0e-9b99-53f939bec0ae")
    captured = CapturedScreen(
        target.index,
        target.name,
        target.serial,
        target.boot_id,
        image,
        image,
        (1280, 720),
        (1280, 720),
        (1.0, 1.0),
        source_image=RUN11_POPUP,
    )
    anchor = load_anchors(Path(__file__).resolve().parents[1] / "assets" / "tasks" / "phase6" / "promo")[0]
    evidence = unique_current_anchor(captured, anchor)
    assert evidence.matched
    assert evidence.score >= 0.99
