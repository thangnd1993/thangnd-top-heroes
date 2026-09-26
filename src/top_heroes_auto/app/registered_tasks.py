"""UI/legacy CLI result adapter; scheduling remains in the global pipeline."""
from top_heroes_auto.app.automation_fleet import run
from top_heroes_auto.app.flow_registry import production_registry


def run_registered_selected(manager, data, index, name, *, tasks=None, cancelled=lambda: False):
    """UI adapter for one already-selected target; no fleet/selection expansion."""
    from top_heroes_auto.app.free_reward_tasks import Phase6TaskResult

    aliases = {'vip-reward':'vip', 'ranking-chest':'ranking', 'free-pack':'shop'}
    enabled = None
    if tasks is not None:
        plan = production_registry().snapshot()
        requested = {aliases.get(task, task) for task in tasks}
        if requested - {f.id for f in plan}:
            raise ValueError('Sequence requested a flow that is not supported/registered.')
        enabled = {f.id:f.id in requested for f in plan}
    report = run(manager, data, enabled=enabled, targets=[dict(index=index, name=name)],
                 temporary_selection=False, cancelled=cancelled)
    row = report['accounts'][0]
    results = [Phase6TaskResult(flow, detail['result'], error=detail.get('error'),
                cleanup_succeeded=row['cleanup'] in {'SUCCESS', 'NOT_REQUIRED'},
                claim_verified=any(r.get('journal') == 'VERIFIED' for r in detail.get('rewards', {}).values()))
            for flow, detail in row['flows'].items()]
    if row['result'] != 'COMPLETE' and results:
        from dataclasses import replace

        results[-1] = replace(results[-1], status='PARTIAL',
            error=row.get('error') or 'Instance plan, recovery or owned cleanup is incomplete.')
    return results
