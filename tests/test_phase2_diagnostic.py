import pytest

from top_heroes_auto.app.diagnostic import _members
from top_heroes_auto.app.run_queue import RunController


def test_exact_diagnostic_snapshot_does_not_include_other_selected_instance(rig):
    manager, _, store = rig
    controller = RunController(store, lambda: manager)
    run = controller.create_members(manager, ((7, "Farm-007"),), 1)
    assert run.snapshot.members == ((7, "Farm-007"),)


def test_exact_two_member_diagnostic_snapshot_is_ordered_and_immutable(rig):
    manager, _, store = rig
    manager.select(8, True)
    controller = RunController(store, lambda: manager)

    run = controller.create_members(manager, ((7, "Farm-007"), (8, "Farm-008")), 2)

    assert run.snapshot.members == ((7, "Farm-007"), (8, "Farm-008"))
    assert run.snapshot.immutable is True
    assert run.max_concurrency == 2


def test_member_parser_rejects_ambiguous_or_duplicate_targets():
    assert _members(["7:Farm-007", "8:Farm-008"]) == ((7, "Farm-007"), (8, "Farm-008"))
    with pytest.raises(Exception, match="dạng INDEX:NAME"):
        _members(["7"])
    with pytest.raises(Exception, match="trùng lặp"):
        _members(["7:Farm-007", "7:Farm-007"])
