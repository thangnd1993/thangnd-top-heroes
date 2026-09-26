
import json

import pytest

import top_heroes_auto.app.task_cli as task_cli_module
from top_heroes_auto.app.free_reward_tasks import (
    PHASE6_TARGET,
    run_free_reward_sequence,
    run_free_reward_task,
)
from top_heroes_auto.app.phase6_runtime import _entry_profile
from top_heroes_auto.app.phase6_shop_navigation_tasks import (
    SHOP_NAVIGATION_LABEL,
    SHOP_NAVIGATION_TASK,
    ShopNavigationTaskResult,
)
from top_heroes_auto.app.phase6_shop_survey_tasks import (
    SHOP_SURVEY_TASK,
)
from top_heroes_auto.app.phase6_vip_survey_tasks import (
    VIP_SURVEY_LABEL,
    VIP_SURVEY_TASK,
    VipSurveyTaskResult,
)
from top_heroes_auto.app.task_cli import parser as task_parser
from top_heroes_auto.automation.free_rewards import (
    Cost,
    FreeRewardExplorer,
    RewardEvidence,
    RewardScreen,
)
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.phase6_navigation import NavigationResult, NavigationStatus
from top_heroes_auto.automation.phase6_visual import RewardRule, RewardVisualProfile
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus
from top_heroes_auto.vision.models import (
    AnchorEvidence,
    BoundingBox,
    NormalizedRect,
    ScreenDetection,
    ScreenState,
    VisualAnchor,
)


def _target2(manager, process):
    process.listing = "0,Queen,1,2,0,-1,-1\n2,5-Emmmmm,0,0,0,-1,-1\n"
    manager.refresh()
    manager.protect(0, True)
    manager.select(2, True)
    assert manager.store.metadata(manager.namespace, 0).protected
    assert manager.store.metadata(manager.namespace, 2).selected


def _profile(tmp_path, *, post=True, entry=True, task="vip-reward", page="vip"):
    roles = ["page", "claim", "free", "available"]
    if post:
        roles.append("post")
    if entry:
        roles.append("entry")
    anchors = tuple(
        (
            role,
            VisualAnchor(
                f"{role}-anchor",
                ScreenState.FREE_REWARD_PAGE,
                tmp_path / f"{role}.png",
                NormalizedRect(0, 0, 1, 1),
                0.9,
            ),
        )
        for role in roles
    )
    return RewardVisualProfile(
        task,
        page,
        anchors,
        (RewardRule("vip-daily"),),
    )


def _screen(capture, *, reward=True):
    evidence = tuple(
        AnchorEvidence(
            anchor,
            ScreenState.FREE_REWARD_PAGE,
            0.99,
            0.9,
            True,
            BoundingBox(10 + n * 12, 10, 10, 10),
            BoundingBox(10 + n * 12, 10, 10, 10),
        )
        for n, anchor in enumerate(("claim", "free", "available", "post", "entry"))
    )
    detection = ScreenDetection(ScreenState.FREE_REWARD_PAGE, 0.99, evidence, capture, None, 1.0)
    item = RewardEvidence("vip-daily", "claim", "free", "available", Cost.FREE, False)
    return RewardScreen(
        detection,
        2,
        "5-Emmmmm",
        "emulator-5558",
        "boot-2",
        capture,
        "vip",
        capture,
        rewards=(item,) if reward else (),
        coverage_known=True,
    )


class Port:
    def __init__(self, *screens, home_result=True):
        self.screens = iter(screens)
        self.actions = []
        self.home_result = home_result

    def observe(self):
        return next(self.screens)

    def claim(self, screen, reward, point):
        self.actions.append(("claim", reward.reward_id, point))

    def verify_claim(self, before, after, reward):
        receipts = [item for item in after.detection.evidence if item.anchor_id == "post" and item.matched]
        return bool(receipts)

    def navigate(self, screen, route, point):
        self.actions.append(("navigate", route.id, point))

    def scroll(self, screen, axis):
        self.actions.append(("scroll", axis))

    def return_home(self, screen):
        self.actions.append(("home",))
        return self.home_result


def recovery(manager, data, *args, **kwargs):
    path = data / "recovery.json"
    path.write_text("{}", encoding="utf-8")
    return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, False


def test_runner_journals_before_dispatch_and_reports_verified_claim(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    profile = _profile(tmp_path)
    port = Port(_screen("before"), _screen("after", reward=False))
    result = run_free_reward_task(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        "vip-reward",
        profiles={"vip-reward": profile},
        port_factory=lambda *args: port,
        entry_navigator=lambda *args: NavigationResult(NavigationStatus.SUCCESS),
        recovery_runner=recovery,
    )
    assert result.status == "SUCCESS"
    assert result.claim_verified
    assert result.report_path and result.report_path.is_file()
    receipts = store.reward_claims(manager.namespace, 2)
    assert receipts[0]["status"] == "VERIFIED"
    assert port.actions[0][0] == "claim"
    assert store.latest_task_run(manager.namespace, "vip-reward", 2)[2] == "SUCCESS"


def test_vip_popup_only_result_stays_reserved_and_blocks_retry(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    profile = _profile(tmp_path)
    port = Port(_screen("before"), _screen("after", reward=False))
    port.verify_claim = lambda *_args: False

    first = run_free_reward_task(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        "vip-reward",
        profiles={"vip-reward": profile},
        port_factory=lambda *args: port,
        entry_navigator=lambda *args: NavigationResult(NavigationStatus.SUCCESS),
        recovery_runner=recovery,
    )

    assert first.status == "ACTION_DISPATCHED_UNVERIFIED"
    assert port.actions == [("claim", "vip-daily", (15, 15))]
    receipts = store.reward_claims(manager.namespace, 2)
    assert len(receipts) == 1 and receipts[0]["status"] == "RESERVED"

    retry = run_free_reward_task(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        "vip-reward",
        profiles={"vip-reward": profile},
        port_factory=lambda *args: pytest.fail("reserved VIP claim must not rebuild the port"),
        entry_navigator=lambda *args: pytest.fail("reserved VIP claim must not navigate"),
        recovery_runner=lambda *args, **kwargs: pytest.fail("reserved VIP claim must not recover"),
    )
    assert retry.status == "ALREADY_ATTEMPTED"
    assert len(port.actions) == 1


def test_missing_postcondition_blocks_before_recovery_or_port(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    calls = []

    def fail_recovery(*args, **kwargs):
        calls.append("recovery")
        raise AssertionError("recovery must not run without postcondition evidence")

    result = run_free_reward_task(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        "vip-reward",
        profiles={"vip-reward": _profile(tmp_path, post=False)},
        port_factory=lambda *args: calls.append("port"),
        entry_navigator=lambda *args: NavigationResult(NavigationStatus.SUCCESS),
        recovery_runner=fail_recovery,
    )
    assert result.status == "NOT_IMPLEMENTED"
    assert "post-claim anchor" in result.error
    assert not calls
    assert store.latest_task_run(manager.namespace, "vip-reward", 2)[2] == "NOT_IMPLEMENTED"
    assert result.report_path and result.report_path.is_file()


@pytest.mark.parametrize("task", ("free-recruit", "ranking-chest"))
def test_packaged_missing_postcondition_finishes_not_implemented_before_dispatch(
    rig, tmp_path, task
):
    manager, process, store = rig
    _target2(manager, process)
    calls = []

    def fail_recovery(*args, **kwargs):
        calls.append("recovery")
        raise AssertionError("packaged missing postcondition must stop before recovery")

    result = run_free_reward_task(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        task,
        port_factory=lambda *args: calls.append("port"),
        entry_navigator=lambda *args: calls.append("entry"),
        recovery_runner=fail_recovery,
    )

    assert result.status == "NOT_IMPLEMENTED"
    assert result.task_run_id is not None
    assert "postcondition anchor" in result.error
    assert calls == []
    assert store.latest_task_run(manager.namespace, task, 2)[2] == "NOT_IMPLEMENTED"
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["task_run_id"] == result.task_run_id
    assert report["profile_available"] is False
    assert report["postcondition_available"] is False
    assert report["result"] == "NOT_IMPLEMENTED"
    assert "postcondition anchor" in report["error"]


def test_sequence_packaged_missing_postcondition_stops_before_recovery_or_dispatch(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    calls = []

    def fail_recovery(*args, **kwargs):
        calls.append("recovery")
        raise AssertionError("sequence must stop before recovery")

    results = run_free_reward_sequence(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        ("free-recruit", "ranking-chest"),
        recovery_runner=fail_recovery,
        port_factory=lambda *args: calls.append("port"),
        entry_navigator=lambda *args: calls.append("entry"),
    )

    assert len(results) == 1
    assert results[0].status == "NOT_IMPLEMENTED"
    assert results[0].task_run_id is not None
    assert calls == []
    assert store.latest_task_run(manager.namespace, "free-recruit", 2)[2] == "NOT_IMPLEMENTED"
    report = json.loads(results[0].report_path.read_text(encoding="utf-8"))
    assert report["profile_available"] is False
    assert report["postcondition_available"] is False
    assert report["result"] == "NOT_IMPLEMENTED"


def test_free_pack_default_path_remains_blocked_before_recovery(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    calls = []

    result = run_free_reward_task(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        "free-pack",
        recovery_runner=lambda *args, **kwargs: calls.append("recovery"),
        port_factory=lambda *args: calls.append("port"),
        entry_navigator=lambda *args: calls.append("entry"),
    )

    assert result.status == "NOT_IMPLEMENTED"
    assert calls == []
    assert store.latest_task_run(manager.namespace, "free-pack", 2)[2] == "NOT_IMPLEMENTED"
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["profile_available"] is False
    assert report["postcondition_available"] is False
    assert report["result"] == "NOT_IMPLEMENTED"


def test_default_cli_path_reports_not_implemented_without_entry_navigation(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    result = run_free_reward_task(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        "vip-reward",
        profiles={"vip-reward": _profile(tmp_path)},
        recovery_runner=lambda *args, **kwargs: pytest.fail("entry must be wired before recovery"),
    )
    assert result.status == "NOT_IMPLEMENTED"
    assert "entry navigation" in result.error
    assert store.latest_task_run(manager.namespace, "vip-reward", 2)[2] == "NOT_IMPLEMENTED"


def test_runner_rechecks_cancellation_after_home_recovery_before_entry(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    profile = _profile(tmp_path)
    cancelled = False
    entry_calls = []

    def recovery_after_home(*args, **kwargs):
        nonlocal cancelled
        cancelled = True
        path = tmp_path / "recovery-cancelled.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, False

    def entry(*args):
        entry_calls.append(args)
        return NavigationResult(NavigationStatus.SUCCESS)

    result = run_free_reward_task(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        "vip-reward",
        profiles={"vip-reward": profile},
        port_factory=lambda *args: pytest.fail("cancelled task must not build reward port"),
        entry_navigator=entry,
        recovery_runner=recovery_after_home,
        cancelled=lambda: cancelled,
    )
    assert result.status == "CANCELLED"
    assert entry_calls == []
    assert store.latest_task_run(manager.namespace, "vip-reward", 2)[2] == "CANCELLED"


def test_packaged_routes_compose_only_from_independent_current_frame_anchors(tmp_path):
    vip = _profile(tmp_path, task="vip-reward", page="vip")
    recruit = _profile(tmp_path, task="free-recruit", page="recruit")
    assert _entry_profile("vip-reward", vip).first_destination is vip.anchor_map["page"]
    recruit_route = _entry_profile("free-recruit", recruit)
    assert recruit_route.first_destination.id == "tavern-selected-name"
    assert recruit_route.second_destination is not None
    assert recruit_route.second_destination is recruit.anchor_map["page"]


def test_cli_parser_exposes_claim_free_partial_shop_survey():
    args = task_parser().parse_args([SHOP_SURVEY_TASK, "--index", "2", "--name", "5-Emmmmm"])
    assert args.command == SHOP_SURVEY_TASK
    assert args.index == 2
    assert args.name == "5-Emmmmm"


def test_malformed_profile_still_finishes_task_run_and_report(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    _target2(manager, process)
    bad = tmp_path / "profiles"
    bad.mkdir()
    (bad / "broken.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr("top_heroes_auto.app.free_reward_tasks.phase6_profile_folder", lambda task: bad)
    result = run_free_reward_task(manager, tmp_path, *PHASE6_TARGET, "vip-reward")
    assert result.status == "SAFETY_BLOCKED"
    assert result.report_path and result.report_path.is_file()
    assert store.latest_task_run(manager.namespace, "vip-reward", 2)[2] == "SAFETY_BLOCKED"


def test_wrong_target_is_rejected_before_task_persistence(rig, tmp_path):
    manager, process, store = rig
    with pytest.raises(SafetyError, match="#2 / 5-Emmmmm"):
        run_free_reward_task(manager, tmp_path, 7, "Farm-007", "vip-reward")
    assert store.latest_task_run(manager.namespace, "vip-reward", 7) is None


def test_sequence_cleans_only_an_instance_it_started(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    profile = _profile(tmp_path)
    profiles = {"vip-reward": profile, "free-recruit": profile}
    recovery_results = iter((True, False, False))

    def owned_recovery(*args, **kwargs):
        path = tmp_path / f"recovery-{next(owned_recovery.counter)}.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, next(recovery_results)

    owned_recovery.counter = iter((1, 2, 3))
    ports = iter((Port(_screen("v1"), _screen("v2", reward=False)), Port(_screen("r1"), _screen("r2", reward=False))))
    actions = []
    manager.execute = lambda index, action, **kwargs: actions.append((index, action))
    results = run_free_reward_sequence(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        ("vip-reward", "free-recruit"),
        profiles=profiles,
        port_factory=lambda *args: next(ports),
        entry_navigator=lambda *args: NavigationResult(NavigationStatus.SUCCESS),
        recovery_runner=owned_recovery,
    )
    assert [item.status for item in results] == ["SUCCESS", "SUCCESS"]
    assert actions == [(2, "quit")]


def test_explorer_failed_home_recovery_is_not_success():
    port = Port(_screen("before"), _screen("after", reward=False), home_result=False)
    result = FreeRewardExplorer().run(port, 2, "5-Emmmmm")
    assert result.claimed == ["vip-daily"]
    assert result.recovery_succeeded is False
    assert result.status == "CLEANUP_FAILED"


def test_sequence_failed_between_task_home_is_persisted(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    profile = _profile(tmp_path)
    calls = []

    def recovery_with_failed_between_home(*args, **kwargs):
        calls.append("recovery")
        path = tmp_path / f"recovery-{len(calls)}.json"
        path.write_text("{}", encoding="utf-8")
        if len(calls) == 1:
            return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, False
        return RecoveryResult(RecoveryStatus.UNKNOWN_SCREEN), path, False

    results = run_free_reward_sequence(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        ("vip-reward", "free-recruit"),
        profiles={"vip-reward": profile, "free-recruit": profile},
        port_factory=lambda *args: Port(_screen("before"), _screen("after", reward=False)),
        entry_navigator=lambda *args: NavigationResult(NavigationStatus.SUCCESS),
        recovery_runner=recovery_with_failed_between_home,
    )
    assert calls == ["recovery", "recovery"]
    assert len(results) == 1
    assert results[0].status == "HOME_RECOVERY_FAILED"
    assert store.latest_task_run(manager.namespace, "vip-reward", 2)[2] == "HOME_RECOVERY_FAILED"
    report = __import__("json").loads(results[0].report_path.read_text(encoding="utf-8"))
    assert report["result"] == "HOME_RECOVERY_FAILED"
    assert report["between_task_home_recovery"]["status"] == "UNKNOWN_SCREEN"
    assert report["sequence_isolation_changed_indices"] == []


def test_sequence_cleanup_failure_is_persisted(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    profile = _profile(tmp_path)

    def owned_recovery(*args, **kwargs):
        path = tmp_path / "recovery-owned.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, True

    def fail_quit(*args, **kwargs):
        raise OSError("quit transport unavailable")

    manager.execute = fail_quit
    results = run_free_reward_sequence(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        ("vip-reward",),
        profiles={"vip-reward": profile},
        port_factory=lambda *args: Port(_screen("before"), _screen("after", reward=False)),
        entry_navigator=lambda *args: NavigationResult(NavigationStatus.SUCCESS),
        recovery_runner=owned_recovery,
    )
    assert results[0].status == "CLEANUP_FAILED"
    assert "quit transport unavailable" in results[0].error
    assert store.latest_task_run(manager.namespace, "vip-reward", 2)[2] == "CLEANUP_FAILED"
    report = __import__("json").loads(results[0].report_path.read_text(encoding="utf-8"))
    assert report["sequence_cleanup_requested"] is True
    assert report["sequence_cleanup_succeeded"] is False
    assert report["result"] == "CLEANUP_FAILED"


def test_sequence_task_persistence_failure_cleans_owned_instance(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    profile = _profile(tmp_path)

    def owned_recovery(*args, **kwargs):
        path = tmp_path / "recovery-owned-persistence.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, True

    original_finish = store.finish_task_run
    finish_calls = []

    def fail_first_finish(*args, **kwargs):
        if not finish_calls:
            finish_calls.append("failed")
            raise OSError("task report persistence unavailable")
        return original_finish(*args, **kwargs)

    store.finish_task_run = fail_first_finish
    actions = []
    manager.execute = lambda index, action, **kwargs: actions.append((index, action))
    results = run_free_reward_sequence(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        ("vip-reward",),
        profiles={"vip-reward": profile},
        port_factory=lambda *args: Port(_screen("before"), _screen("after", reward=False)),
        entry_navigator=lambda *args: NavigationResult(NavigationStatus.SUCCESS),
        recovery_runner=owned_recovery,
    )
    assert results[0].status == "PERSISTENCE_FAILED"
    assert "task report persistence unavailable" in results[0].error
    assert results[0].task_run_id is not None
    assert results[0].report_path and results[0].report_path.is_file()
    assert results[0].started_by_run is True
    assert results[0].cleanup_attempted is True
    assert results[0].cleanup_succeeded is True
    assert actions == [(2, "quit")]
    report = __import__("json").loads(results[0].report_path.read_text(encoding="utf-8"))
    assert report["result"] == "PERSISTENCE_FAILED"
    assert report["cleanup_attempted"] is True
    assert report["cleanup_succeeded"] is True


def test_sequence_task_persistence_and_cleanup_failure_do_not_retry_quit(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    profile = _profile(tmp_path)

    def owned_recovery(*args, **kwargs):
        path = tmp_path / "recovery-owned-double-failure.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, True

    original_finish = store.finish_task_run
    finish_calls = []

    def fail_first_finish(*args, **kwargs):
        if not finish_calls:
            finish_calls.append("failed")
            raise OSError("task row unavailable")
        return original_finish(*args, **kwargs)

    store.finish_task_run = fail_first_finish
    quit_calls = []

    def fail_quit(index, action, **kwargs):
        quit_calls.append((index, action))
        raise OSError("quit dispatch uncertain")

    manager.execute = fail_quit
    results = run_free_reward_sequence(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        ("vip-reward",),
        profiles={"vip-reward": profile},
        port_factory=lambda *args: Port(_screen("before"), _screen("after", reward=False)),
        entry_navigator=lambda *args: NavigationResult(NavigationStatus.SUCCESS),
        recovery_runner=owned_recovery,
    )
    result = results[0]
    assert result.status == "CLEANUP_FAILED"
    assert "task row unavailable" in result.error
    assert "quit dispatch uncertain" in result.error
    assert result.task_run_id is not None
    assert result.report_path and result.report_path.is_file()
    assert result.started_by_run is True
    assert result.cleanup_attempted is True
    assert result.cleanup_succeeded is False
    assert quit_calls == [(2, "quit")]
    assert store.latest_task_run(manager.namespace, "vip-reward", 2)[2] == "CLEANUP_FAILED"
    report = __import__("json").loads(result.report_path.read_text(encoding="utf-8"))
    assert report["result"] == "CLEANUP_FAILED"
    assert report["cleanup_attempted"] is True
    assert report["cleanup_succeeded"] is False


def test_sequence_duplicate_tasks_still_require_between_task_home(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    profile = _profile(tmp_path)
    calls = []

    def recovery_with_duplicate_boundary(*args, **kwargs):
        calls.append("recovery")
        path = tmp_path / f"recovery-duplicate-{len(calls)}.json"
        path.write_text("{}", encoding="utf-8")
        status = RecoveryStatus.ALREADY_HOME if len(calls) == 1 else RecoveryStatus.UNKNOWN_SCREEN
        return RecoveryResult(status), path, False

    results = run_free_reward_sequence(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        ("vip-reward", "vip-reward"),
        profiles={"vip-reward": profile},
        port_factory=lambda *args: Port(_screen("before"), _screen("after", reward=False)),
        entry_navigator=lambda *args: NavigationResult(NavigationStatus.SUCCESS),
        recovery_runner=recovery_with_duplicate_boundary,
    )
    assert calls == ["recovery", "recovery"]
    assert len(results) == 1
    assert results[0].status == "HOME_RECOVERY_FAILED"


def test_cli_parser_exposes_phase6_tasks_and_sequence():
    args = task_parser().parse_args(["vip-reward", "--index", "2", "--name", "5-Emmmmm"])
    assert args.command == "vip-reward"
    args = task_parser().parse_args(["free-rewards", "--index", "2", "--name", "5-Emmmmm"])
    assert args.tasks is None  # Enabled supported registry supplies the plan; Recruit is deferred.
    args = task_parser().parse_args(
        [SHOP_NAVIGATION_TASK, "--index", "2", "--name", "5-Emmmmm"]
    )
    assert args.command == SHOP_NAVIGATION_TASK
    args = task_parser().parse_args([VIP_SURVEY_TASK, "--index", "2", "--name", "5-Emmmmm"])
    assert args.command == VIP_SURVEY_TASK


def test_cli_shop_navigation_dispatches_only_navigation_runner(rig, tmp_path, monkeypatch, capsys):
    manager, _, _ = rig
    calls = []

    def fake_manager(data):
        return manager

    def fake_survey(*args, **kwargs):
        calls.append((args, kwargs))
        return ShopNavigationTaskResult(SHOP_NAVIGATION_TASK, "SUCCESS")

    monkeypatch.setattr(task_cli_module, "_manager", fake_manager)
    monkeypatch.setattr(task_cli_module, "run_phase6_shop_navigation", fake_survey)
    code = task_cli_module.main(
        [SHOP_NAVIGATION_TASK, "--index", "2", "--name", "5-Emmmmm"],
        tmp_path,
    )

    assert code == 0
    assert calls[0][0][0] is manager
    assert calls[0][0][2:] == (2, "5-Emmmmm")
    assert calls[0][1]["promo_recovery_factory"] is task_cli_module.promo_recovery_factory
    output = json.loads(capsys.readouterr().out)
    assert output["task"] == SHOP_NAVIGATION_TASK
    assert output["label"] == SHOP_NAVIGATION_LABEL
    assert output["scope"].startswith("navigation-only")


def test_cli_vip_survey_dispatches_observation_runner(rig, tmp_path, monkeypatch, capsys):
    manager, _, _ = rig
    calls = []

    def fake_manager(data):
        return manager

    def fake_survey(*args, **kwargs):
        calls.append((args, kwargs))
        return VipSurveyTaskResult(VIP_SURVEY_TASK, "SUCCESS")

    monkeypatch.setattr(task_cli_module, "_manager", fake_manager)
    monkeypatch.setattr(task_cli_module, "run_phase6_vip_survey", fake_survey)
    code = task_cli_module.main(
        [VIP_SURVEY_TASK, "--index", "2", "--name", "5-Emmmmm"],
        tmp_path,
    )

    assert code == 0
    assert calls[0][0][0] is manager
    assert calls[0][0][2:] == (2, "5-Emmmmm")
    output = json.loads(capsys.readouterr().out)
    assert output["task"] == VIP_SURVEY_TASK
    assert output["label"] == VIP_SURVEY_LABEL
    assert output["receipt_available"] is False
    assert output["journal_rows"] == 0
