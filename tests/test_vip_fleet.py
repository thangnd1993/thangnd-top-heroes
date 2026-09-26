from types import SimpleNamespace

import pytest

from top_heroes_auto.app import vip_fleet
from top_heroes_auto.automation.free_rewards import ClaimOutcome, Cost, RewardEvidence, RewardScreen
from top_heroes_auto.automation.phase6_navigation import NavigationResult, NavigationStatus
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus
from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox, ScreenDetection, ScreenState


def prepare(rig):
    manager, process, store = rig
    process.listing = "\n".join(f"{i},{name},0,0,0,-1,-1" for i, name in
                                {**vip_fleet.PROTECTED, 2: "5-Emmmmm", 9: "Pooh5", 12: "New protected"}.items())
    manager.refresh()
    for i in (*vip_fleet.PROTECTED, 12):
        manager.protect(i, True)
    return manager, store


def frame(capture, name="Pooh5"):
    evidence = tuple(AnchorEvidence(a, ScreenState.FREE_REWARD_PAGE, .99, .9, True,
                                    BoundingBox(10, 10, 20, 20), BoundingBox(10, 10, 20, 20))
                     for a in ("claim", "free", "available"))
    return RewardScreen(ScreenDetection(ScreenState.FREE_REWARD_PAGE, .99, evidence, capture, None, 1),
                        9, name, "emulator-5572", "boot-test", capture, "vip", capture,
                        rewards=(RewardEvidence("vip-daily", "claim", "free", "available", Cost.FREE, False),))


@pytest.mark.parametrize("outcome", [ClaimOutcome.CLAIMED, ClaimOutcome.UNKNOWN])
@pytest.mark.parametrize("locked_upper", [False, True, "error"])
def test_one_shot_journal_and_selection_restore_for_non_index2(rig, tmp_path, monkeypatch, outcome, locked_upper):
    manager, store = prepare(rig)
    captures = iter((frame("before"), frame("after")))
    calls = []

    def claim(*args, before_input):
        assert store.reward_claims(manager.namespace, 9)[0]["dispatch_state"] == "NOT_DISPATCHED"
        before_input()
        assert store.reward_claims(manager.namespace, 9)[0]["dispatch_state"] == "POSSIBLE"
        calls.append("claim")

    port = SimpleNamespace(set_entry_geometry=lambda _: None, observe=lambda: next(captures),
                           validate_claim=lambda *a: None, geometry_report={"safe": True}, claim=claim,
                           classify_claim=lambda *a: outcome, return_home=lambda *a: True,
                           dismiss_receipts=lambda screen: screen, overlay_events=[])
    monkeypatch.setattr(vip_fleet, "_load_profile_details", lambda _: (object(), None))
    monkeypatch.setattr(vip_fleet, "run_home_recovery", lambda *a, **k:
                        (RecoveryResult(RecoveryStatus.ALREADY_HOME), tmp_path / "recovery.json", False))
    monkeypatch.setattr(vip_fleet, "entry_navigator_factory", lambda *a:
                        NavigationResult(NavigationStatus.SUCCESS))
    monkeypatch.setattr(vip_fleet, "reward_port_factory", lambda *a: port)
    if locked_upper:
        from top_heroes_auto.app import vip_gift

        def upper(*args):
            args[-1].update(result="ALREADY_ATTEMPTED", claim_dispatched=False, journal_state="RESERVED")
            if locked_upper == "error":
                raise OSError("Upper-gift independent evidence failure; green requires its own fresh evidence.")
        monkeypatch.setattr(vip_gift, "run_upper_gift", upper)
    row = vip_fleet.run_vip_account(manager, tmp_path, 9, "Pooh5", tmp_path, include_upper_gift=locked_upper)
    assert calls == ["claim"]
    assert row["selection_restored"] and not store.metadata(manager.namespace, 9).selected
    assert row["journal_state"] == ("VERIFIED" if outcome == ClaimOutcome.CLAIMED else "RESERVED")
    expected = "SUCCESS" if outcome == ClaimOutcome.CLAIMED else "ACTION_DISPATCHED_UNVERIFIED"
    assert row["final_result"] == ("PARTIAL_UPPER_GIFT_UNVERIFIED" if locked_upper else expected)
    if locked_upper:
        assert row["daily_result"] == expected
    retry = vip_fleet.run_vip_account(manager, tmp_path, 9, "Pooh5", tmp_path)
    assert retry["final_result"] in {"ALREADY_VERIFIED", "ALREADY_ATTEMPTED"}
    assert calls == ["claim"]


def test_live_protected_exclusion_and_failure_continues_sequentially(rig, tmp_path):
    manager, _ = prepare(rig)
    calls = []

    def account_runner(manager, data, index, name, folder):
        calls.append(index)
        if index == 2:
            raise OSError("per-account failure")
        return dict(index=index, name=name, final_result="NOT_AVAILABLE")

    report = vip_fleet.run_vip_fleet(manager, tmp_path, account_runner=account_runner)
    assert calls == [2, 9]
    assert report["max_concurrency"] == 1
    assert [r["final_result"] for r in report["accounts"]] == ["FAILED", "NOT_AVAILABLE"]


def test_protected_target_never_selected_or_recovered(rig, tmp_path, monkeypatch):
    manager, _ = prepare(rig)
    monkeypatch.setattr(vip_fleet, "run_home_recovery", lambda *a, **k: pytest.fail("Protected recovery"))
    manager.select = lambda *a: pytest.fail("Protected selection")
    row = vip_fleet.run_vip_account(manager, tmp_path, 12, "New protected", tmp_path)
    assert row["final_result"] == "SKIPPED_PROTECTED"
    assert row["claim_dispatched"] is False
