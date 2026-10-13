from dataclasses import replace

import pytest
from test_dynamic_events import Port, control, frame
from test_event_journal import run, setup

from top_heroes_auto.app.event_claim_reconciliation import reconcile_possible
from top_heroes_auto.automation.dynamic_events import DynamicEventExplorer, EventEntryUnstable


def test_changed_art_in_failed_region_is_denied_without_blocking_other_root():
    bad = control("animated-a", "event")
    changed = replace(bad, identity="animated-b")
    other = replace(bad, identity="other", box=replace(bad.box, x=250))
    back = control("back", "parent")

    class P(Port):
        def navigate(self, f, c):
            if c.identity == "animated-a":
                raise EventEntryUnstable("No input")
            assert c.identity != "animated-b"
            super().navigate(f, c)

    p = P(
        [
            frame("home", 0, [bad, other]),
            frame("home", 1, [changed, other]),
            frame("event:other", 2, [], parent=back),
            frame("home", 3, [changed, other]),
        ]
    )
    report = DynamicEventExplorer().run(p)
    assert report.events["animated-b"]["result"] == "BLOCKED"
    assert any(
        b["reason"] == "PRIOR_ROOT_REACQUISITION_FAILED" for b in report.events["animated-b"]["blockers"]
    )
    assert report.events["other"]["result"] == "EXHAUSTED"


@pytest.mark.parametrize(
    "family,marker",
    [
        ("race-task-grid", "qualified-race-task-grid"),
        ("achievement-cards", "qualified-achievement-cards"),
        ("inline-objectives", "qualified-inline-objectives"),
    ],
)
@pytest.mark.parametrize(
    "missing",
    [None, "explicit-claimed-label", "original-green-control-absent", "unique-saved-caption-agreement"],
)
def test_typed_post_state_can_reconcile_without_repeating_action(tmp_path, family, marker, missing):
    store, task, f, r = setup(tmp_path)
    f = replace(f, page="event:current:" + family)
    r = replace(r, evidence=(*r.evidence, marker))
    calls = []
    result = run(store, task, f, r, calls, post=lambda *a: [])
    evidence = {
        marker,
        "unique-saved-caption-agreement",
        "complete-reward-card",
        "explicit-claimed-label",
        "original-green-control-absent",
    }
    if missing:
        evidence.remove(missing)
    observations = [
        dict(
            identity=list(f.identity),
            capture=f"fresh-{i}",
            page=f.page,
            reward=r.identity,
            state="NOT_AVAILABLE",
            independent_evidence=list(evidence),
        )
        for i in range(2)
    ]
    verified = reconcile_possible(store, "install", 13, "disk", observations)
    assert verified == ([] if missing else [result["claim_id"]])
    run(store, store.create_task_run("install", "events", 13, "user name"), f, r, calls)
    assert len(calls) == 1


@pytest.mark.parametrize("uncertain", [False, True])
def test_preinput_navigation_rejection_can_recover_but_uncertain_input_cannot(uncertain):
    from top_heroes_auto.automation.dynamic_events import EventNavigationRejected

    first = control("first", "event")
    second = replace(first, identity="second", box=replace(first.box, x=250))
    scroll = control("scroll", "scroll")
    back = control("back", "parent")

    class P(Port):
        def navigate(self, f, c):
            if c.kind == "scroll":
                if uncertain:
                    raise OSError("Transport uncertain")
                raise EventNavigationRejected("No input")
            super().navigate(f, c)

    p = P(
        [
            frame("home", 0, [first, second]),
            frame("event:first", 1, [scroll], parent=back),
            frame("home", 2, [first, second]),
            frame("event:second", 3, [], parent=back),
            frame("home", 4, []),
        ]
    )
    recovered = []
    p.recover_home = lambda: recovered.append(True) or dict(status="SUCCESS")
    result = DynamicEventExplorer().run(p)
    assert recovered == ([] if uncertain else [True])
    assert result.events["first"]["result"] == "BLOCKED"
    if not uncertain:
        assert result.events["second"]["result"] == "EXHAUSTED"
