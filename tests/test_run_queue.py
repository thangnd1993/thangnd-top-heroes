import threading
import time

from top_heroes_auto.app.run_queue import RunController
from top_heroes_auto.ldplayer.client import Instance
from top_heroes_auto.storage.store import AccountStatus, RunStatus


def test_snapshot_is_immutable_after_checkbox_changes(rig):
    manager, _, store = rig
    controller = RunController(store, lambda: manager)
    run = controller.create(manager, 1)
    manager.select(7, False)

    rows = controller.execute(run)

    assert rows[0][0:3] == (7, "Farm-007", AccountStatus.SUCCESS)
    assert rows[0][5] == 0  # already-running instance is not owned by the run


def test_cancelled_run_never_starts_queued_account(rig):
    manager, _, store = rig
    controller = RunController(store, lambda: manager)
    run = controller.create(manager, 1)
    controller.cancel()

    rows = controller.execute(run)

    assert rows[0][2] == AccountStatus.CANCELLED


def test_retry_failed_rechecks_live_protection(rig):
    manager, process, store = rig
    controller = RunController(store, lambda: manager)
    process.devices_output = "List of devices attached\n"
    manager.ADB_RESOLVE_TIMEOUT = 0
    prior = controller.create(manager, 1)
    controller.execute(prior)
    assert store.run_accounts(prior.id)[0][2] == AccountStatus.FAILED

    manager.protect(7, True)
    try:
        controller.retry_failed(manager, prior.id, 1)
    except ValueError as exc:
        assert "Không có giả lập" in str(exc)
    else:
        raise AssertionError("Protected failed account must not be retried")


def test_store_marks_unfinished_runs_interrupted(tmp_path):
    from top_heroes_auto.storage.store import Store

    path = tmp_path / "history.sqlite3"
    store = Store(path)
    run_id = store.create_run("ns", ((7, "Farm-007"),), 1)
    store.set_run_status(run_id, RunStatus.RUNNING)
    reopened = Store(path)
    with reopened.connect() as db:
        status = db.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()[0]
    assert status == RunStatus.INTERRUPTED


class StubManager:
    namespace = "queue-test"

    def __init__(self, store, instances, active, failing=()):
        self.store, self.instances, self.active, self.failing = store, tuple(instances), active, set(failing)
        self.actions = []

    def refresh(self):
        self.store.merge(self.namespace, self.instances)
        return self.instances

    def query(self, index):
        return next(item for item in self.instances if item.index == index)

    def execute(self, index, action, **_):
        self.actions.append((index, action))
        if action == "verify" and index in self.failing:
            raise RuntimeError(f"ADB timeout #{index}")
        with self.active:
            self.active.count += 1
            self.active.peak = max(self.active.peak, self.active.count)
        time.sleep(0.01)
        with self.active:
            self.active.count -= 1
        return "ok"


class Counter:
    def __init__(self):
        self.count = self.peak = 0

    def __enter__(self):
        self.lock.acquire()

    def __exit__(self, *_):
        self.lock.release()

    lock = threading.Lock()


def test_concurrency_is_bounded_and_failure_isolated(tmp_path):
    from top_heroes_auto.storage.store import Store

    store, active = Store(tmp_path / "queue.sqlite3"), Counter()
    instances = tuple(Instance(i, f"Clone-{i}", False, 0, 0) for i in (7, 8, 9))
    seed = StubManager(store, instances, active)
    seed.refresh()
    for item in instances:
        store.select(seed.namespace, item.index, True)
    controller = RunController(store, lambda: StubManager(store, instances, active, failing=(8,)))
    run = controller.create(seed, 2)

    rows = controller.execute(run)

    assert active.peak <= 2
    assert {row[2] for row in rows} == {AccountStatus.SUCCESS, AccountStatus.FAILED}
    assert sum(row[2] == AccountStatus.SUCCESS for row in rows) == 2


def test_run_owned_stopped_instance_is_cleaned_up(rig):
    manager, process, store = rig
    process.listing = "0,Main-Thang,1,2,1,101,102\n7,Farm-007,0,0,0,-1,-1\n"
    controller = RunController(store, lambda: manager)
    run = controller.create(manager, 1)

    controller.execute(run)

    assert (7, "launch") in [(int(call[3]), call[1]) for call in process.calls if call[1] == "launch"]
    assert not manager.query(7).running
