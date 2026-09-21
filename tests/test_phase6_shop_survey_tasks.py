import json
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.phase6_shop_survey_tasks import (
    PHASE6_TARGET,
    SHOP_SURVEY_TASK,
    run_phase6_shop_survey,
)
from top_heroes_auto.automation.free_rewards import RewardScreen
from top_heroes_auto.automation.guard import SafetyError
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
