"""Guild and Mail feature adapters for the permanent instance-first registry."""
import json

from top_heroes_auto.app.flow_registry import COMPLETE, REGISTRY, Flow
from top_heroes_auto.app.guild_mail_port import GuildMailPort
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.guild_mail_claims import process, relic_cycle
from top_heroes_auto.automation.recovery import RecoveryStatus
from top_heroes_auto.vision.guild_mail import GUILD_REWARDS, MAIL_REWARDS


def run(session, folder, rewards, *, port_factory=GuildMailPort):
    folder.mkdir(parents=True,exist_ok=True)
    report = dict(index=session.index,name=session.name,rewards={},return_home='NOT_STARTED',
                  excluded_sections=['guild-trial-hall','purchases','mail-delete'],
                  unqualified_sections=['guild-war','guild-shop','guild-treasure','guild-help'])
    path = folder/'feature-report.json'

    def persist():
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

    store, namespace = session.manager.store, session.manager.namespace
    task = store.create_task_run(namespace,folder.name,session.index,session.name)
    report['task_run_id'] = task
    port = None
    try:
        recovery, recovery_path, _ = session.recover()
        report.update(recovery=recovery.status.value,recovery_report=str(recovery_path),adb=recovery.adb_target)
        if recovery.status not in {RecoveryStatus.SUCCESS,RecoveryStatus.ALREADY_HOME}:
            raise ValueError('No verified Home before Guild/Mail.')
        port = port_factory(session,folder)
        for reward in rewards:
            outcome = dict(result='NOT_STARTED',journal='NONE',claim_dispatched=False,claim_count=0)
            report['rewards'][reward] = outcome
            try:
                session.check()
                port.open_reward(reward)
                process(port,store,namespace,task,reward,session.target['persistent_identity'],outcome,persist)
            except Exception as exc:  # noqa: BLE001 - later independent rewards still receive safe evaluation
                if outcome['result'] in {'NOT_STARTED','RESERVED','AVAILABLE'}:
                    outcome['result'] = 'BLOCKED'
                outcome['error'] = f'{type(exc).__name__}: {exc}'
            persist()
    except Exception as exc:  # noqa: BLE001 - lifecycle remains owned by the enclosing session
        report['error'] = str(exc)
    finally:
        for reward in rewards:
            report['rewards'].setdefault(reward,dict(result='BLOCKED',journal='NONE',claim_dispatched=False))
        if port is not None:
            try:
                port.home()
                report['return_home'] = 'SUCCESS'
            except Exception as exc:  # noqa: BLE001 - recovery never downgrades a verified claim
                report['return_home'] = 'FAILED'
                report['recovery_error'] = str(exc)
            report.update(entries=port.entries,popup_dismissals=port.dismissals)
        report['result'] = 'SUCCESS' if all(r['result'] in COMPLETE for r in report['rewards'].values()) else 'BLOCKED'
        store.finish_task_run(task,report['result'],report_path=str(path))
        persist()
    return report


def relic_completed(session,rewards):
    """A proven current-period Relic must not need another feature visit."""
    store,namespace = session.manager.store,session.manager.namespace
    if store.metadata(namespace,session.index).protected:
        raise SafetyError('Protected journal cannot authorize a flow.')
    if 'guild-relic' not in rewards:
        return {}
    rows = [r for r in store.reward_claims(namespace,session.index) if r['reward_id'] == 'guild-relic']
    if any(r['status'] != 'VERIFIED' for r in rows):
        return {}
    current = [r for r in rows if r['cycle_key'] == relic_cycle()]
    if (len(current) != 1 or current[0]['instance_name'] != session.name or
            json.loads(current[0]['before_evidence']).get('persistent_identity') != session.target['persistent_identity']):
        return {}
    return {'guild-relic':dict(result='ALREADY_VERIFIED',journal='VERIFIED',claim_id=current[0]['id'],
                              completion_source='current_period_journal',claim_dispatched=False)}


REGISTRY.register(Flow('guild',GUILD_REWARDS,run,completed=relic_completed))
REGISTRY.register(Flow('mail',MAIL_REWARDS,run))
