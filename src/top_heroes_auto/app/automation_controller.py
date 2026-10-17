"""Normal app Start uses the same complete registry pipeline as acceptance."""
import threading

from top_heroes_auto.app.automation_fleet import run as run_fleet
from top_heroes_auto.app.automation_ownership import exclusive_automation
from top_heroes_auto.app.run_queue import QueueRun, RunController
from top_heroes_auto.automation.guard import SafetyError, bound_snapshot
from top_heroes_auto.storage.store import AccountStatus, RunStatus


class AutomationController(RunController):
    def __init__(self, store, manager_factory, progress=lambda *_: None):
        super().__init__(store, manager_factory, progress)
        self.account_cancellations = {}
        self.report = None

    def create(self, manager, max_concurrency, *, all_non_protected=False):
        if type(max_concurrency) is not int or max_concurrency not in (1, 2):
            raise SafetyError('Chỉ cho phép một hoặc hai tài khoản đồng thời.')
        current = manager.refresh()
        members = tuple((i.index, i.name) for i in current
                        if not manager.store.metadata(manager.namespace, i.index).protected
                        and (all_non_protected or manager.store.metadata(manager.namespace, i.index).selected))
        snapshot = bound_snapshot(self.store, manager.namespace, members, True)
        run_id = self.store.create_run(manager.namespace, members, max_concurrency)
        self.store.set(f'automation-temporary-selection:{run_id}', str(int(all_non_protected)))
        return QueueRun(run_id, snapshot, max_concurrency)

    def retry_failed(self, manager, prior_run_id, max_concurrency):
        if type(max_concurrency) is not int or max_concurrency not in (1, 2):
            raise SafetyError('Chỉ cho phép một hoặc hai tài khoản đồng thời.')
        # Exact original disk identities; never turn Retry into a fresh fleet.
        temporary = self.store.get(f'automation-temporary-selection:{prior_run_id}', '0') == '1'
        live = {i.index: i for i in manager.refresh()}
        members = []
        for index, _ in self.store.retry_members(prior_run_id):
            meta = self.store.metadata(manager.namespace, index)
            if index not in live or meta.protected or (not temporary and not meta.selected):
                continue
            self.store.require_identity(manager.namespace, index, self.store.run_identity(prior_run_id, index))
            members.append((index, live[index].name))
        snapshot = bound_snapshot(self.store, manager.namespace, tuple(members), True)
        run_id = self.store.create_run(manager.namespace, snapshot.members, max_concurrency)
        self.store.set(f'automation-temporary-selection:{run_id}', str(int(temporary)))
        return QueueRun(run_id, snapshot, max_concurrency)

    def cancel_account(self, index):
        event = self.account_cancellations.get(index)
        if event is not None:
            event.set()

    def execute(self, run):
        return self._execute_owned(self.manager_factory(), run)

    @staticmethod
    @exclusive_automation
    def _dispatch(manager, data, *, controller, run):
        store = controller.store
        store.set_run_status(run.id, RunStatus.RUNNING)
        identities = dict(run.snapshot.identities)
        targets = [dict(index=i, name=n, persistent_identity=identities[i]) for i, n in run.snapshot.members]
        controller.account_cancellations = {i: threading.Event() for i, _ in run.snapshot.members}

        def cancelled(index):
            event = controller.account_cancellations[index]
            return lambda: event.is_set() or not controller._wait_unpaused()

        def started(target):
            i = target['index']
            store.set_account_status(run.id, i, AccountStatus.RUNNING)
            controller.progress(run.id, i, AccountStatus.RUNNING, 'Đang chạy toàn bộ kế hoạch nhận quà')

        def finished(row):
            i = row['index']
            status = (AccountStatus.CANCELLED if controller.cancelled.is_set()
                      or controller.account_cancellations[i].is_set() else
                      AccountStatus.SUCCESS if row['result'] == 'COMPLETE' else AccountStatus.FAILED)
            error = row.get('error') or ('Còn phần bị chặn; xem báo cáo.' if status == AccountStatus.FAILED else '')
            store.set_account_status(run.id, i, status, error, row.get('session', {}).get('started_by_run', False))
            controller.progress(run.id, i, status, error or 'Hoàn tất kế hoạch')

        try:
            controller.report = run_fleet(manager, data, targets=targets, max_concurrency=run.max_concurrency,
                manager_factory=controller.manager_factory,
                temporary_selection=store.get(f'automation-temporary-selection:{run.id}', '0') == '1',
                account_started=started, account_finished=finished, cancellation_factory=cancelled,
                run_id=run.id, origin='normal-ui-start',
                report_created=lambda path: store.set(f'automation-report:{run.id}', path))
            store.set(f'automation-report:{run.id}', controller.report['report_path'])
        except BaseException:
            for i, _, status, *_ in store.run_accounts(run.id):
                if status in {AccountStatus.QUEUED, AccountStatus.RUNNING, AccountStatus.STARTING}:
                    store.set_account_status(run.id, i, AccountStatus.FAILED, 'Run interrupted; preserve action journals.')
            store.finish_run(run.id, RunStatus.FAILED)
            raise
        status = (RunStatus.CANCELLED if controller.cancelled.is_set() else
                  RunStatus.SUCCESS if controller.report['result'] == 'PASS' else RunStatus.FAILED)
        store.finish_run(run.id, status)
        return store.run_accounts(run.id)

    def _execute_owned(self, manager, run):
        from top_heroes_auto.app.log_context import run_id

        token = run_id.set(run.id)
        try:
            return self._dispatch(manager, manager.data_dir, controller=self, run=run)
        finally:
            run_id.reset(token)
