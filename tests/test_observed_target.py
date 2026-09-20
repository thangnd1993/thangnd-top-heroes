from dataclasses import replace

import pytest

from top_heroes_auto.automation.guard import RunSnapshot, SafetyError


@pytest.mark.parametrize("changes", [
    {"index": 2}, {"name": "other"}, {"serial": "emulator-9999"},
    {"boot_id": "bb068632-fc3e-4090-a8d7-ae8d9fe353f5"},
])
def test_input_rejects_identity_different_from_screenshot(rig, changes):
    manager, process, _ = rig
    target, _ = manager.capture_verified(7)
    process.calls.clear()
    with pytest.raises(SafetyError, match="screenshot"):
        manager.execute(7, "tap", values=(100, 100), observed_target=replace(target, **changes))
    assert not any("input" in call for call in process.calls)


def test_visual_input_respects_live_selection_even_with_snapshot(rig):
    manager, process, _ = rig
    target, _ = manager.capture_verified(7)
    snapshot = RunSnapshot(manager.namespace, ((7, target.name),), True)
    manager.select(7, False)
    process.calls.clear()
    with pytest.raises(SafetyError):
        manager.execute(7, "tap", values=(100, 100), snapshot=snapshot, observed_target=target)
    assert not any("input" in call for call in process.calls)


def test_visual_input_uses_exact_verified_observed_target(rig):
    manager, process, _ = rig
    target, _ = manager.capture_verified(7)
    process.calls.clear()
    manager.execute(7, "tap", values=(100, 100), observed_target=target)
    inputs = [call for call in process.calls if "input" in call]
    assert len(inputs) == 1
    assert inputs[0][1:3] == ["-s", target.serial]


def test_screenshot_identity_cannot_authorize_lifecycle(rig):
    manager, process, _ = rig
    target, _ = manager.capture_verified(7)
    process.calls.clear()
    with pytest.raises(SafetyError):
        manager.execute(7, "reboot", observed_target=target)
    assert not process.calls
