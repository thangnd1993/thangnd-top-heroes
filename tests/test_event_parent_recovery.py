from dataclasses import replace
from types import SimpleNamespace

import pytest

from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.automation.dynamic_events import Control, EventFrame
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.models import BoundingBox


def frame(page="event:known", **kwargs):
    return EventFrame(
        "fresh",
        (5, "disk", "explicit", "boot"),
        page,
        "pixels",
        parent=Control("current-back", BoundingBox(20, 1100, 50, 50), ("qualified",), "parent"),
        stable_id="disk",
        **kwargs,
    )


def port(tmp_path, frames):
    p = object.__new__(DynamicEventPort)
    p.folder = tmp_path
    p.entered = "original-event"
    p.current = None
    p.event_title = "title"
    it = iter(frames)
    p.observe = lambda: next(it)
    p.sent = []
    p.navigate = lambda f, c: p.sent.append((f, c))
    p.session = SimpleNamespace(
        recover=lambda: (SimpleNamespace(status=SimpleNamespace(value="SUCCESS")), "report", None)
    )
    return p


def test_current_parent_chain_then_independent_home_verification(tmp_path):
    frames = [frame("event:child"), frame("event:root"), frame("home")]
    p = port(tmp_path, frames)
    assert p.recover_home()["status"] == "SUCCESS"
    assert [f.page for f, _ in p.sent] == ["event:child", "event:root"]
    assert (tmp_path / "parent-recovery.jsonl").is_file()
    assert p.entered is None


@pytest.mark.parametrize(
    "f",
    [
        frame("UNKNOWN"),
        frame(popup=True),
        replace(frame(), parent=None),
        replace(frame(), parent=Control("claim", BoundingBox(20, 30, 40, 50), (), "reward")),
    ],
)
def test_unknown_popup_missing_parent_and_reward_never_receive_recovery_input(tmp_path, f):
    p = port(tmp_path, [f])
    p.recover_home()
    assert p.sent == []


def test_runtime_change_fails_closed_before_next_input(tmp_path):
    p = port(tmp_path, [frame(), replace(frame("event:next"), identity=(5, "disk", "other", "boot"))])
    with pytest.raises(SafetyError, match="identity changed"):
        p.recover_home()
    assert len(p.sent) == 1


def test_repeated_edge_and_overlong_chain_are_bounded(tmp_path):
    p = port(tmp_path, [frame(), frame()])
    p.recover_home()
    assert len(p.sent) == 1
    p = port(tmp_path, [frame("event:" + str(i)) for i in range(6)])
    p.recover_home()
    assert len(p.sent) == 4


def test_unentered_event_does_not_grant_navigation(tmp_path):
    p = port(tmp_path, [])
    p.entered = None
    p.recover_home()
    assert p.sent == []


def test_unexpected_parent_retains_root_for_recovery_and_cannot_mark_exhausted():
    from test_dynamic_events import Port, control
    from test_dynamic_events import frame as observed

    from top_heroes_auto.automation.dynamic_events import DynamicEventExplorer

    event = control("original", "event")
    back = control("back", "parent")
    p = Port(
        [
            observed("home", 0, [event]),
            observed("event:child", 1, [], parent=back),
            observed("event:unexpected-parent", 2, [], parent=back),
            observed("home", 3, []),
        ]
    )
    recovery = []
    p.recover_home = lambda: recovery.append(True) or dict(status="SUCCESS")
    result = DynamicEventExplorer().run(p)
    assert recovery == [True]
    assert result.events["original"]["result"] == "BLOCKED"
    assert any(b["reason"] == "PARENT_NOT_VERIFIED" and b["event"] == "original" for b in result.blocked)
