from top_heroes_auto.app.run_queue import RunController


def test_exact_diagnostic_snapshot_does_not_include_other_selected_instance(rig):
    manager, _, store = rig
    controller = RunController(store, lambda: manager)
    run = controller.create_members(manager, ((7, "Farm-007"),), 1)
    assert run.snapshot.members == ((7, "Farm-007"),)
