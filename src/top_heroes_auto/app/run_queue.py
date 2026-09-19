"""Phase 2 bounded, target-isolated lifecycle queue."""

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError, create_snapshot
from top_heroes_auto.storage.store import AccountStatus, RunStatus, Store


@dataclass(frozen=True)
class QueueRun:
    id: int
    snapshot: RunSnapshot
    max_concurrency: int


class RunController:
    """Runs lifecycle-only work; each worker owns a separate Manager instance."""

    def __init__(self, store: Store, manager_factory: Callable[[], Manager], progress: Callable = lambda *_: None):
        self.store, self.manager_factory, self.progress = store, manager_factory, progress
        self.cancelled = threading.Event()
        self.paused = threading.Event()

    def create(self, manager: Manager, max_concurrency: int) -> QueueRun:
        current = manager.refresh()
        snapshot = create_snapshot(self.store, manager.namespace, current)
        run_id = self.store.create_run(manager.namespace, snapshot.members, max_concurrency)
        return QueueRun(run_id, RunSnapshot(snapshot.namespace, snapshot.members, True), max_concurrency)

    def create_members(self, manager: Manager, members: tuple[tuple[int, str], ...], max_concurrency: int) -> QueueRun:
        """Create an exact diagnostic snapshot without editing other selections."""
        current = {(item.index, item.name) for item in manager.refresh()}
        safe = tuple(
            member
            for member in members
            if member in current
            and self.store.metadata(manager.namespace, member[0]).selected
            and not self.store.metadata(manager.namespace, member[0]).protected
        )
        if safe != members:
            raise SafetyError("Diagnostic target không còn selected, bị bảo vệ hoặc đổi identity.")
        run_id = self.store.create_run(manager.namespace, safe, max_concurrency)
        return QueueRun(run_id, RunSnapshot(manager.namespace, safe, True), max_concurrency)

    def retry_failed(self, manager: Manager, prior_run_id: int, max_concurrency: int) -> QueueRun:
        candidates = self.store.retry_members(prior_run_id)
        current = manager.refresh()
        live = {(item.index, item.name) for item in current}
        members = tuple(
            member
            for member in candidates
            if member in live and not self.store.metadata(manager.namespace, member[0]).protected
            and self.store.metadata(manager.namespace, member[0]).selected
        )
        run_id = self.store.create_run(manager.namespace, members, max_concurrency)
        return QueueRun(run_id, RunSnapshot(manager.namespace, members, True), max_concurrency)

    def cancel(self):
        self.cancelled.set()

    def pause(self, value: bool):
        (self.paused.set if value else self.paused.clear)()

    def _wait_unpaused(self) -> bool:
        while self.paused.is_set() and not self.cancelled.wait(0.1):
            pass
        return not self.cancelled.is_set()

    def _account(self, run: QueueRun, index: int, name: str):
        manager = self.manager_factory()
        started_by_run = False
        try:
            if self.cancelled.is_set():
                self.store.set_account_status(run.id, index, AccountStatus.CANCELLED)
                return AccountStatus.CANCELLED
            self.store.set_account_status(run.id, index, AccountStatus.STARTING)
            self.progress(run.id, index, AccountStatus.STARTING, "Đang kiểm tra lifecycle")
            instance = manager.query(index)
            if instance.name != name:
                raise SafetyError("Identity mismatch trong run snapshot.")
            started_by_run = not instance.running
            if started_by_run:
                manager.execute(index, "launch", snapshot=run.snapshot)
            self.store.set_account_status(run.id, index, AccountStatus.RUNNING, started_by_run=started_by_run)
            self.progress(run.id, index, AccountStatus.RUNNING, "Kết nối ADB")
            manager.execute(index, "verify", snapshot=run.snapshot)
            if self.cancelled.is_set():
                raise SafetyError("Run đã được hủy.")
            manager.execute(index, "harmless", snapshot=run.snapshot)
            self.store.set_account_status(run.id, index, AccountStatus.SUCCESS, started_by_run=started_by_run)
            self.progress(run.id, index, AccountStatus.SUCCESS, "Hoàn tất")
            return AccountStatus.SUCCESS
        except (RuntimeError, ValueError) as exc:
            status = AccountStatus.CANCELLED if self.cancelled.is_set() else AccountStatus.FAILED
            self.store.set_account_status(run.id, index, status, str(exc), started_by_run)
            self.progress(run.id, index, status, str(exc))
            return status
        finally:
            # Never stop manually-opened instances. Target-specific cleanup only.
            if started_by_run:
                try:
                    manager.execute(index, "quit", snapshot=run.snapshot)
                except RuntimeError:
                    logging.getLogger("top_heroes_auto").exception("Run target cleanup failed")

    def execute(self, run: QueueRun):
        self.store.set_run_status(run.id, RunStatus.RUNNING)
        futures: dict[Future, tuple[int, str]] = {}
        iterator = iter(run.snapshot.members)
        with ThreadPoolExecutor(max_workers=run.max_concurrency, thread_name_prefix=f"run-{run.id}") as pool:
            while not self.cancelled.is_set() and self._wait_unpaused() and len(futures) < run.max_concurrency:
                try:
                    index, name = next(iterator)
                except StopIteration:
                    break
                futures[pool.submit(self._account, run, index, name)] = (index, name)
            while futures:
                done = next(as_completed(futures))
                futures.pop(done)
                if not self.cancelled.is_set() and self._wait_unpaused():
                    try:
                        index, name = next(iterator)
                        futures[pool.submit(self._account, run, index, name)] = (index, name)
                    except StopIteration:
                        pass
        # Entries that were never dispatched become cancelled, never silently skipped.
        for index, name in iterator:
            self.store.set_account_status(run.id, index, AccountStatus.CANCELLED)
            self.progress(run.id, index, AccountStatus.CANCELLED, "Chưa bắt đầu")
        status = RunStatus.CANCELLED if self.cancelled.is_set() else RunStatus.SUCCESS
        self.store.finish_run(run.id, status)
        return self.store.run_accounts(run.id)
