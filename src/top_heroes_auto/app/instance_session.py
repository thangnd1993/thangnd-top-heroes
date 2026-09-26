"""Single lifecycle/selection owner for an extensible per-instance execution plan."""
from top_heroes_auto.app.bxh_shop_acceptance import persistent_identity
from top_heroes_auto.app.diagnostic import _instance
from top_heroes_auto.app.recovery_cli import RecoveryFailure, run_home_recovery
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.recovery import RecoveryStatus


class InstanceSession:
    def __init__(self, manager, data, target, folder, *, identity_reader=persistent_identity,
                 temporary_selection=True, cancelled=lambda: False, recovery_runner=run_home_recovery):
        self.manager, self.data, self.target, self.folder = manager, data, target, folder
        self.index, self.name = target['index'], target['name']
        self.identity_reader, self.cancelled = identity_reader, cancelled
        self.temporary_selection, self.recovery_runner = temporary_selection, recovery_runner
        self.snapshot = RunSnapshot(manager.namespace, ((self.index, self.name),), True)
        self.selected_before = None
        self.changed_selection = self.started = self.cleanup_attempted = self.closed = False
        self.initial = None
        self.used_initial = False
        self.report = dict(cleanup='NOT_REQUIRED', selection_restored=False, recoveries=[],
                           started_by_run=False, return_home='NOT_STARTED')

    def check(self, *, selected=True, running=True):
        live = _instance(self.manager, self.index, self.name)
        meta = self.manager.store.metadata(self.manager.namespace, self.index)
        if meta.protected or (selected and not meta.selected):
            raise SafetyError('Session target must remain selected and not Protected.')
        if self.identity_reader(self.manager, self.index) != self.target['persistent_identity']:
            raise SafetyError('Persistent session identity changed.')
        if running and not live.running:
            raise SafetyError('Session target stopped; no restart between flows.')
        if self.cancelled() and selected and running:
            raise SafetyError('Run cancelled.')
        return live

    def start(self):
        if self.initial is not None:
            raise SafetyError('Session start may only run once.')
        self.check(selected=False, running=False)
        self.selected_before = self.manager.store.metadata(self.manager.namespace, self.index).selected
        if not self.selected_before:
            if not self.temporary_selection:
                raise SafetyError('Normal application requires explicit selected target.')
            self.manager.select(self.index, True)
            self.changed_selection = True
        try:
            self.initial = self.recovery_runner(self.manager, self.data, self.index, self.name,
                cleanup_owned=False, cancelled=self.cancelled)
            result, path, self.started = self.initial
            if result.ownership_uncertain:
                self.report['cleanup'] = 'OWNERSHIP_UNKNOWN'
                self.report['ownership_uncertain'] = True
            self.report['recoveries'].append(dict(status=result.status.value, report=str(path)))
        except RecoveryFailure as exc:
            self.started, self.cleanup_attempted = exc.started_by_run, exc.cleanup_attempted
            self.report['cleanup'] = 'SUCCESS' if exc.cleanup_succeeded else 'FAILED' if exc.cleanup_attempted else 'NOT_REQUIRED'
            raise
        finally:
            self.report['started_by_run'] = self.started

    def recover(self):
        """Navigation only after first start. A stopped target cannot be relaunched."""
        self.check()
        if self.initial is None:
            raise SafetyError('Instance session was not started.')
        if self.initial[0].status not in {RecoveryStatus.SUCCESS, RecoveryStatus.ALREADY_HOME}:
            raise SafetyError(f'Initial recovery blocked: {self.initial[0].status.value}')
        if not self.used_initial:
            self.used_initial = True
            result, path, _ = self.initial
        else:
            result, path, started = self.recovery_runner(self.manager, self.data, self.index, self.name,
                cleanup_owned=False, allow_start=False, cancelled=self.cancelled)
            if started:
                raise SafetyError('Navigation-only recovery acquired lifecycle ownership.')
            self.report['recoveries'].append(dict(status=result.status.value, report=str(path)))
        return result, path, False  # Only this session owns lifecycle cleanup.

    def close(self):
        if self.closed:
            return self.report
        self.closed = True
        if self.started and not self.cleanup_attempted:
            self.cleanup_attempted = True
            try:
                # Cancellation stops new gameplay, but permits owned cleanup.
                self.check(selected=True, running=False)
                self.manager.execute(self.index, 'quit', snapshot=self.snapshot)
                self.report['cleanup'] = 'SUCCESS'
            except Exception as exc:  # noqa: BLE001 - never retry cleanup/override protection
                self.report['cleanup'] = f'FAILED: {exc}'
        try:
            if self.changed_selection:
                self.check(selected=False, running=False)
                self.manager.select(self.index, self.selected_before)
            self.report['selection_restored'] = (
                self.manager.store.metadata(self.manager.namespace, self.index).selected == self.selected_before)
        except Exception as exc:  # noqa: BLE001 - identity/protection may revoke restoration
            self.report['selection_error'] = str(exc)
        return self.report
